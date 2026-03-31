import logging
import shutil
from pathlib import Path
from types import SimpleNamespace
from app.config import settings

logger = logging.getLogger(__name__)


def seconds_to_srt_time(seconds: float) -> str:
    """Convert float seconds to SRT timestamp format: HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds % 1) * 1000))
    if millis >= 1000:
        millis = 0
        secs += 1
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def segments_to_srt(segments) -> str:
    """Convert faster-whisper segments to SRT format string."""
    lines = []
    for i, segment in enumerate(segments, start=1):
        start = seconds_to_srt_time(segment.start)
        end = seconds_to_srt_time(segment.end)
        text = segment.text.strip()
        lines.append(f"{i}\n{start} --> {end}\n{text}\n")
    return "\n".join(lines)


def _split_audio_chunks(audio_path: str, chunk_seconds: int, job_id: str) -> list[tuple[str, float]]:
    """
    Split audio into fixed-duration chunks using ffmpeg.
    Returns list of (chunk_wav_path, start_offset_seconds) in order.
    """
    import ffmpeg

    job_dir = Path(settings.storage_path) / job_id
    chunks_dir = job_dir / "chunks"
    chunks_dir.mkdir(exist_ok=True)

    try:
        probe = ffmpeg.probe(audio_path)
        total_duration = float(probe["format"]["duration"])
    except Exception as e:
        raise RuntimeError(f"Could not probe audio duration: {e}") from e

    chunks: list[tuple[str, float]] = []
    offset = 0.0
    idx = 0

    while offset < total_duration:
        chunk_path = str(chunks_dir / f"chunk_{idx:03d}.wav")
        try:
            (
                ffmpeg
                .input(audio_path, ss=offset, t=chunk_seconds)
                .output(chunk_path, ac=1, ar=16000, acodec="pcm_s16le")
                .overwrite_output()
                .run(quiet=True)
            )
        except ffmpeg.Error as e:
            stderr = e.stderr.decode() if e.stderr else "unknown"
            raise RuntimeError(f"FFmpeg chunk split failed at offset {offset}s: {stderr}") from e

        chunks.append((chunk_path, offset))
        offset += chunk_seconds
        idx += 1

    logger.info(f"[{job_id}] Split audio into {len(chunks)} chunks of {chunk_seconds}s each")
    return chunks


def _transcribe_chunk(model, chunk_path: str, offset: float, beam_size: int) -> list:
    """
    Transcribe a single audio chunk on a shared model instance.
    Returns segments as SimpleNamespace objects with timestamps offset-adjusted.
    CTranslate2 (faster-whisper backend) is thread-safe: multiple threads can call
    transcribe() concurrently on the same WhisperModel instance.
    """
    segments, _ = model.transcribe(
        chunk_path,
        word_timestamps=True,
        beam_size=beam_size,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )
    result = []
    for seg in segments:
        result.append(SimpleNamespace(
            start=seg.start + offset,
            end=seg.end + offset,
            text=seg.text,
        ))
    return result


def transcribe(audio_path: str, job_id: str) -> str:
    """
    Transcribe audio to SRT using faster-whisper with two performance optimisations:
      1. VAD pre-filter  — skips silence segments before feeding to Whisper (~1.4x free speedup)
      2. Audio chunking  — splits long audio into asr_chunk_minutes pieces, processed
                           sequentially with one shared model instance.

    Note: GPU parallelism (concurrent threads on the same CTranslate2 model) was removed
    because concurrent CUDA operations on one model instance can cause a fatal process crash
    that bypasses Python exception handling entirely.
    VAD alone removes 70-90% of audio per chunk, making sequential processing fast enough.
    """
    import torch
    from faster_whisper import WhisperModel

    job_dir = Path(settings.storage_path) / job_id
    srt_path = str(job_dir / "source.srt")
    chunks_dir = job_dir / "chunks"

    device = settings.whisper_device
    compute_type = settings.whisper_compute_type

    if device == "cuda" and not torch.cuda.is_available():
        logger.warning(f"[{job_id}] CUDA not available, falling back to CPU")
        device = "cpu"
        compute_type = "int8"

    logger.info(
        f"[{job_id}] Loading Whisper model={settings.whisper_model_size} "
        f"device={device} compute_type={compute_type} "
        f"beam_size={settings.whisper_beam_size}"
    )

    model = WhisperModel(
        settings.whisper_model_size,
        device=device,
        compute_type=compute_type,
    )

    all_segments: list = []

    try:
        chunk_seconds = settings.asr_chunk_minutes * 60
        chunks = _split_audio_chunks(audio_path, chunk_seconds, job_id)

        for idx, (chunk_path, offset) in enumerate(chunks):
            logger.info(f"[{job_id}] Chunk {idx + 1}/{len(chunks)} (offset={offset:.0f}s)")
            segs = _transcribe_chunk(model, chunk_path, offset, settings.whisper_beam_size)
            all_segments.extend(segs)
            logger.info(f"[{job_id}] Chunk {idx + 1} done: {len(segs)} segments")

    finally:
        # Only delete the CTranslate2 model object — do NOT call torch.cuda.empty_cache()
        # here. CTranslate2 manages its own CUDA allocator separately from PyTorch.
        # Calling torch.cuda.empty_cache() immediately after CTranslate2's destructor
        # runs causes a CUDA context conflict that produces a fatal C-level crash,
        # bypassing all Python exception handling and killing the worker process.
        # The worker's _free_gpu() already handles PyTorch cache cleanup after the task.
        import gc
        del model
        gc.collect()
        logger.info(f"[{job_id}] Whisper model unloaded")
        if chunks_dir.exists():
            shutil.rmtree(chunks_dir, ignore_errors=True)

    logger.info(f"[{job_id}] Transcription complete: {len(all_segments)} segments total")

    srt_content = segments_to_srt(all_segments)
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(srt_content)

    logger.info(f"[{job_id}] SRT written: {srt_path}")
    return srt_path

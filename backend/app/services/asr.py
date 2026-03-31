import logging
import shutil
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    Transcribe audio to SRT using faster-whisper with three performance optimisations:
      1. VAD pre-filter  — skips silence segments before feeding to Whisper
      2. Audio chunking  — splits long audio into asr_chunk_minutes pieces
      3. Parallel workers — ThreadPoolExecutor processes chunks concurrently
         (CTranslate2 releases the GIL during inference; one model, N threads)
    """
    import torch
    from faster_whisper import WhisperModel

    job_dir = Path(settings.storage_path) / job_id
    srt_path = str(job_dir / "source.srt")

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

    chunks_dir = Path(settings.storage_path) / job_id / "chunks"

    try:
        chunk_seconds = settings.asr_chunk_minutes * 60
        chunks = _split_audio_chunks(audio_path, chunk_seconds, job_id)

        if len(chunks) == 1:
            # Short video: transcribe directly, no threading overhead
            logger.info(f"[{job_id}] Single chunk — transcribing directly with VAD")
            all_segments = _transcribe_chunk(
                model, audio_path, 0.0, settings.whisper_beam_size
            )
        else:
            logger.info(
                f"[{job_id}] Transcribing {len(chunks)} chunks "
                f"with {settings.asr_workers} parallel workers"
            )
            chunk_results: list[list | None] = [None] * len(chunks)

            def _process(args: tuple[int, str, float]) -> tuple[int, list]:
                idx, path, offset = args
                logger.debug(f"[{job_id}] Worker transcribing chunk {idx} (offset={offset:.1f}s)")
                segs = _transcribe_chunk(model, path, offset, settings.whisper_beam_size)
                logger.debug(f"[{job_id}] Chunk {idx} done: {len(segs)} segments")
                return idx, segs

            with ThreadPoolExecutor(max_workers=settings.asr_workers) as pool:
                futures = {
                    pool.submit(_process, (i, cp, off)): i
                    for i, (cp, off) in enumerate(chunks)
                }
                for future in as_completed(futures):
                    idx, segs = future.result()
                    chunk_results[idx] = segs

            # Merge chunks in order
            all_segments = []
            for segs in chunk_results:
                if segs:
                    all_segments.extend(segs)

        logger.info(f"[{job_id}] Transcription complete: {len(all_segments)} segments total")

    finally:
        del model
        torch.cuda.empty_cache()
        logger.info(f"[{job_id}] Whisper model unloaded")
        if chunks_dir.exists():
            shutil.rmtree(chunks_dir, ignore_errors=True)

    srt_content = segments_to_srt(all_segments)
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(srt_content)

    logger.info(f"[{job_id}] SRT written: {srt_path}")
    return srt_path

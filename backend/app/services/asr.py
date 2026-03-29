import logging
from pathlib import Path
from app.config import settings

logger = logging.getLogger(__name__)


def seconds_to_srt_time(seconds: float) -> str:
    """Convert float seconds to SRT timestamp format: HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds % 1) * 1000))
    # Handle rounding up to 1000ms
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


def transcribe(audio_path: str, job_id: str) -> str:
    """Transcribe audio to SRT using faster-whisper. Loads and unloads model per call."""
    import torch
    from faster_whisper import WhisperModel

    job_dir = Path(settings.storage_path) / job_id
    srt_path = str(job_dir / "source.srt")

    # Determine device and compute type
    device = settings.whisper_device
    compute_type = settings.whisper_compute_type

    # Fallback to CPU if CUDA is not available
    if device == "cuda" and not torch.cuda.is_available():
        logger.warning(f"[{job_id}] CUDA not available, falling back to CPU")
        device = "cpu"
        compute_type = "int8"

    logger.info(
        f"[{job_id}] Loading Whisper model={settings.whisper_model_size} "
        f"device={device} compute_type={compute_type}"
    )

    model = WhisperModel(
        settings.whisper_model_size,
        device=device,
        compute_type=compute_type,
    )

    try:
        logger.info(f"[{job_id}] Transcribing: {audio_path}")
        segments, info = model.transcribe(
            audio_path,
            word_timestamps=True,
            beam_size=5,
        )
        # Materialize segments (generator) into a list before unloading model
        segments_list = list(segments)
        logger.info(
            f"[{job_id}] Transcription complete: {len(segments_list)} segments, "
            f"language={info.language} (confidence={info.language_probability:.2f})"
        )
    finally:
        # Always unload model to free VRAM
        del model
        torch.cuda.empty_cache()
        logger.info(f"[{job_id}] Whisper model unloaded")

    srt_content = segments_to_srt(segments_list)
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(srt_content)

    logger.info(f"[{job_id}] SRT written: {srt_path}")
    return srt_path

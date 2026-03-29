import logging
from pathlib import Path
import ffmpeg
from app.config import settings

logger = logging.getLogger(__name__)


def extract_audio(job_id: str) -> str:
    """Extract audio from input video to 16kHz mono WAV using FFmpeg."""
    job_dir = Path(settings.storage_path) / job_id
    input_path = str(job_dir / "input.mp4")
    output_path = str(job_dir / "audio.wav")

    logger.info(f"[{job_id}] Extracting audio from {input_path}")
    try:
        (
            ffmpeg
            .input(input_path)
            .output(output_path, ac=1, ar=16000, acodec="pcm_s16le")
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as e:
        stderr = e.stderr.decode() if e.stderr else "unknown error"
        raise RuntimeError(f"FFmpeg audio extraction failed: {stderr}") from e

    logger.info(f"[{job_id}] Audio extracted: {output_path}")
    return output_path


def mux_video(job_id: str, dubbed_audio_path: str, srt_path: str) -> str:
    """Replace video audio track with dubbed audio. SRT exported as sidecar file."""
    job_dir = Path(settings.storage_path) / job_id
    input_video = str(job_dir / "input.mp4")
    output_video = str(job_dir / "output.mp4")

    logger.info(f"[{job_id}] Muxing video: {input_video} + {dubbed_audio_path}")
    try:
        video_stream = ffmpeg.input(input_video).video
        audio_stream = ffmpeg.input(dubbed_audio_path).audio

        (
            ffmpeg
            .output(
                video_stream,
                audio_stream,
                output_video,
                vcodec="copy",
                acodec="aac",
                audio_bitrate="192k",
            )
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as e:
        stderr = e.stderr.decode() if e.stderr else "unknown error"
        raise RuntimeError(f"FFmpeg mux failed: {stderr}") from e

    logger.info(f"[{job_id}] Mux complete: {output_video}")
    return output_video


def get_video_duration(path: str) -> float:
    """Get duration of a video/audio file in seconds using ffprobe."""
    try:
        probe = ffmpeg.probe(path)
        duration = float(probe["format"]["duration"])
        return duration
    except (ffmpeg.Error, KeyError, ValueError) as e:
        raise RuntimeError(f"Could not determine duration of {path}: {e}") from e

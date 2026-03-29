# Stub — implemented in Task 8
import logging

logger = logging.getLogger(__name__)


def extract_audio(job_id: str) -> str:
    """Extract audio from input video to WAV using FFmpeg."""
    raise NotImplementedError("FFmpeg extract_audio not yet implemented")


def mux_video(job_id: str, dubbed_audio_path: str, srt_path: str) -> str:
    """Replace video audio track with dubbed audio using FFmpeg."""
    raise NotImplementedError("FFmpeg mux_video not yet implemented")


def get_video_duration(path: str) -> float:
    """Get video/audio duration in seconds using ffprobe."""
    raise NotImplementedError("get_video_duration not yet implemented")

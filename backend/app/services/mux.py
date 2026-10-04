import logging
import re
from pathlib import Path
import ffmpeg
from app.config import settings

logger = logging.getLogger(__name__)


def srt_to_vtt(srt_path: str) -> str:
    """Convert an SRT file to WebVTT format for browser <track> playback."""
    vtt_path = srt_path.replace(".srt", ".vtt")
    with open(srt_path, encoding="utf-8") as f:
        content = f.read()
    # Replace SRT comma-millisecond separator with VTT period
    vtt_content = "WEBVTT\n\n" + re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", content)
    with open(vtt_path, "w", encoding="utf-8") as f:
        f.write(vtt_content)
    return vtt_path


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


def mux_video(
    job_id: str,
    dubbed_audio_path: str,
    source_srt_path: str,
    translated_srt_path: str,
) -> tuple[str, str, str]:
    """
    Replace video audio with dubbed audio and embed both subtitle tracks.
    Returns (output_video_path, source_vtt_path, translated_vtt_path).
    """
    job_dir = Path(settings.storage_path) / job_id
    input_video = str(job_dir / "input.mp4")
    output_video = str(job_dir / "output.mp4")

    # Convert both SRTs to WebVTT for browser playback
    source_vtt = srt_to_vtt(source_srt_path)
    translated_vtt = srt_to_vtt(translated_srt_path)

    logger.info(f"[{job_id}] Muxing video with dual subtitle tracks")
    try:
        video_stream = ffmpeg.input(input_video).video
        audio_stream = ffmpeg.input(dubbed_audio_path).audio
        sub_orig = ffmpeg.input(source_srt_path)
        sub_trans = ffmpeg.input(translated_srt_path)

        (
            ffmpeg
            .output(
                video_stream,
                audio_stream,
                sub_orig,
                sub_trans,
                output_video,
                vcodec="copy",
                acodec="aac",
                audio_bitrate="192k",
                **{"c:s": "mov_text",
                   "metadata:s:s:0": "title=Original",
                   "metadata:s:s:1": "title=Translation"},
            )
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as e:
        stderr = e.stderr.decode() if e.stderr else "unknown error"
        raise RuntimeError(f"FFmpeg mux failed: {stderr}") from e

    logger.info(f"[{job_id}] Mux complete: {output_video}")
    return output_video, source_vtt, translated_vtt



def _srt_to_sec(time_str: str) -> float:
    """HH:MM:SS,mmm -> seconds as float."""
    time_str = time_str.replace(",", ".")
    h, m, rest = time_str.split(":")
    return int(h) * 3600 + int(m) * 60 + float(rest)


def create_bilingual_download(
    job_id: str,
    source_srt_path: str,
    translated_srt_path: str,
) -> str:
    """
    Produce a download-ready MP4 with both subtitle tracks burned in using
    FFmpeg's 'subtitles' filter (libass). This replaces the old per-segment
    drawtext approach which evaluated 1000+ conditions on every frame of a
    2-hour video, taking ~5 minutes. libass processes the SRT natively and
    runs in seconds regardless of segment count.

    Layout: translated (Chinese/target) at bottom in yellow, source (English)
    above it in white, both with a semi-transparent black outline.
    """
    import subprocess
    import shutil

    job_dir = Path(settings.storage_path) / job_id
    output_video = str(job_dir / "output.mp4")
    dl_path = str(job_dir / "bilingual_with_subs.mp4")

    # Clean up leftover drawtext_tmp from any previous runs
    old_tmp = job_dir / "drawtext_tmp"
    if old_tmp.exists():
        shutil.rmtree(old_tmp, ignore_errors=True)

    probe = ffmpeg.probe(output_video)
    vs = next(s for s in probe["streams"] if s["codec_type"] == "video")
    height = int(vs["height"])

    cn_size = max(int(height * 0.040), 20)
    en_size = max(int(height * 0.028), 14)
    cn_margin = max(int(height * 0.020), 10)
    en_margin = cn_margin + cn_size + 8

    # ASS colour format: &HAABBGGRR  (AA=00 → fully opaque)
    # Yellow #FDE047 → R=FD G=E0 B=47 → &H0047E0FD
    cn_colour = "&H0047E0FD"
    en_colour = "&H00FFFFFF"

    # ASS force_style — Alignment=2 = bottom-centre
    cn_style = (
        f"FontName=Microsoft YaHei,FontSize={cn_size},"
        f"PrimaryColour={cn_colour},OutlineColour=&H99000000,"
        f"BorderStyle=1,Outline=1,Shadow=0,"
        f"Alignment=2,MarginV={cn_margin}"
    )
    en_style = (
        f"FontName=Microsoft YaHei,FontSize={en_size},"
        f"PrimaryColour={en_colour},OutlineColour=&H99000000,"
        f"BorderStyle=1,Outline=1,Shadow=0,"
        f"Alignment=2,MarginV={en_margin}"
    )

    # FFmpeg subtitles filter uses forward slashes; colon in Windows drive
    # letter must be escaped as \: inside the filter option string.
    def _ff_path(p: str) -> str:
        return p.replace("\\", "/").replace(":", "\\:")

    vf = (
        f"subtitles='{_ff_path(translated_srt_path)}':force_style='{cn_style}',"
        f"subtitles='{_ff_path(source_srt_path)}':force_style='{en_style}'"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", output_video,
        "-vf", vf,
        "-vcodec", "libx264", "-crf", "18", "-preset", "fast",
        "-acodec", "copy",
        dl_path,
    ]
    logger.info(f"[{job_id}] Burning bilingual subtitles via libass ({height}p)")
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg bilingual burn failed: {result.stderr.decode(errors='replace')}"
        ) from None

    logger.info(f"[{job_id}] Bilingual download ready: {dl_path}")
    return dl_path


def export_mp3(job_id: str, dubbed_audio_path: str) -> str:
    """Convert dubbed WAV to MP3 for audio-only export."""
    job_dir = Path(settings.storage_path) / job_id
    output_path = str(job_dir / "output.mp3")

    logger.info(f"[{job_id}] Exporting MP3 from {dubbed_audio_path}")
    try:
        (
            ffmpeg
            .input(dubbed_audio_path)
            .output(output_path, acodec="libmp3lame", audio_bitrate="192k")
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as e:
        stderr = e.stderr.decode() if e.stderr else "unknown error"
        raise RuntimeError(f"FFmpeg MP3 export failed: {stderr}") from e

    logger.info(f"[{job_id}] MP3 export complete: {output_path}")
    return output_path


def get_video_duration(path: str) -> float:
    """Get duration of a video/audio file in seconds using ffprobe."""
    try:
        probe = ffmpeg.probe(path)
        duration = float(probe["format"]["duration"])
        return duration
    except (ffmpeg.Error, KeyError, ValueError) as e:
        raise RuntimeError(f"Could not determine duration of {path}: {e}") from e

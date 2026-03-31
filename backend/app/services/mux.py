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
    Produce a single download-ready MP4 with both subtitle tracks burned in
    using FFmpeg drawtext filter — matching the player overlay style
    (yellow Chinese bottom, white English above, semi-transparent black box).
    """
    import subprocess
    from app.services.translate import parse_srt

    job_dir = Path(settings.storage_path) / job_id
    output_video = str(job_dir / "output.mp4")
    dl_path = str(job_dir / "bilingual_with_subs.mp4")

    # Get actual video dimensions for font size scaling
    probe = ffmpeg.probe(output_video)
    vs = next(s for s in probe["streams"] if s["codec_type"] == "video")
    height = int(vs["height"])

    cn_size = max(int(height * 0.040), 20)
    en_size = max(int(height * 0.028), 14)
    cn_margin = max(int(height * 0.020), 10)
    box_pad = max(int(cn_size * 0.25), 4)

    # Font: Microsoft YaHei (supports CJK + Latin)
    font = "C\\\\:/Windows/Fonts/msyh.ttc"

    # Build one drawtext chain: translated (Chinese/target) at bottom, source (English) above
    with open(translated_srt_path, encoding="utf-8") as f:
        cn_segs = parse_srt(f.read())
    with open(source_srt_path, encoding="utf-8") as f:
        en_segs = parse_srt(f.read())

    # Write each segment's text to a temp file so drawtext can read it
    # (avoids shell quoting nightmares with special characters)
    tmp_dir = job_dir / "drawtext_tmp"
    tmp_dir.mkdir(exist_ok=True)

    filter_parts: list[str] = []

    for i, seg in enumerate(cn_segs):
        txt_file = tmp_dir / f"cn_{i}.txt"
        txt_file.write_text(seg.text.replace("\n", " "), encoding="utf-8")
        s = _srt_to_sec(seg.start)
        e = _srt_to_sec(seg.end)
        filter_parts.append(
            f"drawtext=fontfile={font}:textfile=drawtext_tmp/cn_{i}.txt"
            f":fontcolor=0xFDE047:fontsize={cn_size}"
            f":box=1:boxcolor=black@0.65:boxborderw={box_pad}"
            f":x=(w-text_w)/2:y=h-{cn_margin}-text_h"
            f":enable='between(t,{s:.3f},{e:.3f})'"
        )

    for i, seg in enumerate(en_segs):
        txt_file = tmp_dir / f"en_{i}.txt"
        txt_file.write_text(seg.text.replace("\n", " "), encoding="utf-8")
        s = _srt_to_sec(seg.start)
        e = _srt_to_sec(seg.end)
        filter_parts.append(
            f"drawtext=fontfile={font}:textfile=drawtext_tmp/en_{i}.txt"
            f":fontcolor=white:fontsize={en_size}"
            f":box=1:boxcolor=black@0.65:boxborderw={box_pad}"
            f":x=(w-text_w)/2:y=h-{cn_margin}-{cn_size}-8-text_h"
            f":enable='between(t,{s:.3f},{e:.3f})'"
        )

    vf = ",".join(filter_parts)

    # Write the filter to a file to avoid Windows' 32,767-char command line limit.
    # With 500+ subtitle segments the -vf string easily exceeds this limit.
    filter_script = job_dir / "vf_script.txt"
    filter_script.write_text(vf, encoding="utf-8")

    cmd = [
        "ffmpeg", "-y",
        "-i", "output.mp4",
        "-filter_script:v", str(filter_script),
        "-vcodec", "libx264", "-crf", "18", "-preset", "fast",
        "-acodec", "copy",
        "bilingual_with_subs.mp4",
    ]
    logger.info(f"[{job_id}] Burning bilingual drawtext subtitles ({height}p)")
    result = subprocess.run(cmd, cwd=str(job_dir), capture_output=True)
    filter_script.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg bilingual burn failed: {result.stderr.decode(errors='replace')}"
        ) from None

    logger.info(f"[{job_id}] Bilingual download ready: {dl_path}")
    return dl_path


def get_video_duration(path: str) -> float:
    """Get duration of a video/audio file in seconds using ffprobe."""
    try:
        probe = ffmpeg.probe(path)
        duration = float(probe["format"]["duration"])
        return duration
    except (ffmpeg.Error, KeyError, ValueError) as e:
        raise RuntimeError(f"Could not determine duration of {path}: {e}") from e

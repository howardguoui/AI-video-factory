import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


def download_video(job_id: str, url: str) -> str:
    """
    Download a video from YouTube, Bilibili, or any yt-dlp supported URL.
    Saves to {job_dir}/input.mp4 and returns that path.
    """
    import yt_dlp

    job_dir = Path(settings.storage_path) / job_id
    output_path = str(job_dir / "input.mp4")

    logger.info(f"[{job_id}] Downloading video: {url}")
    ydl_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": output_path,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    if not Path(output_path).exists():
        raise RuntimeError(f"yt-dlp completed but output file not found: {output_path}")

    logger.info(f"[{job_id}] Video downloaded: {output_path}")
    return output_path


def extract_webpage_text(job_id: str, url: str) -> str:
    """
    Fetch a webpage and extract its main readable text content using trafilatura.
    Saves to {job_dir}/source.txt and returns that path.
    """
    import trafilatura

    job_dir = Path(settings.storage_path) / job_id
    output_path = str(job_dir / "source.txt")

    logger.info(f"[{job_id}] Fetching webpage: {url}")
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        raise RuntimeError(f"Failed to fetch URL: {url}")

    text = trafilatura.extract(
        downloaded,
        include_comments=False,
        include_tables=True,
        favor_precision=True,
    )
    if not text or not text.strip():
        raise RuntimeError(f"No extractable text content found at: {url}")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text.strip())

    logger.info(f"[{job_id}] Webpage text extracted: {len(text)} chars → {output_path}")
    return output_path

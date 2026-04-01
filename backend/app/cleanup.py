"""
Startup cleanup — wipes all job folders under storage/ on server start.
Only .gitkeep is preserved. This ensures a clean slate on every restart.
"""
import logging
import shutil
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


def wipe_storage_on_startup() -> int:
    """
    Delete every subdirectory under storage/ except .gitkeep.
    Returns the number of directories removed.
    """
    storage = Path(settings.storage_path)
    if not storage.exists():
        return 0

    removed = 0
    for entry in storage.iterdir():
        if entry.name == ".gitkeep":
            continue
        if entry.is_dir():
            shutil.rmtree(entry, ignore_errors=True)
            removed += 1
            logger.info(f"Startup: removed job folder {entry.name}")
        elif entry.is_file():
            entry.unlink(missing_ok=True)
            removed += 1

    if removed:
        logger.info(f"Startup cleanup: removed {removed} item(s) from storage/")
    return removed


def cleanup_completed_jobs() -> int:
    """
    On-demand cleanup: delete intermediate temp files for done/failed jobs only.
    Used by DELETE /api/jobs/cleanup (does not wipe everything).
    """
    from app.state import get_all_job_ids, get_job_data

    _TEMP_NAMES = {"audio.wav", "audio.mp3", "ref.wav", "ref_scan.wav", "dubbed.wav"}
    storage = Path(settings.storage_path)
    if not storage.exists():
        return 0

    cleaned = 0
    for job_id in get_all_job_ids():
        data = get_job_data(job_id)
        if not data or data.get("status") not in ("done", "failed"):
            continue
        job_dir = storage / job_id
        if not job_dir.exists():
            continue
        for name in _TEMP_NAMES:
            p = job_dir / name
            if p.exists():
                p.unlink()
        for p in job_dir.glob("clip_*.wav"):
            p.unlink()
        cleaned += 1

    return cleaned

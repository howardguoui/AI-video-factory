import os
import logging
from uuid import uuid4
from pathlib import Path
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import settings
from app.state import job_store, update_status
from app.models.job import JobResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/jobs", status_code=202)
async def create_job(
    file: UploadFile | None = File(default=None),
    youtube_url: str | None = Form(default=None),
    target_lang: str = Form(default="zh"),
):
    if file is None and not youtube_url:
        raise HTTPException(status_code=400, detail="Either file or youtube_url must be provided")

    job_id = str(uuid4())
    job_dir = Path(settings.storage_path) / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    input_path = None
    if file:
        input_path = str(job_dir / "input.mp4")
        content = await file.read()
        with open(input_path, "wb") as f:
            f.write(content)
        logger.info(f"[{job_id}] Saved upload: {input_path} ({len(content)} bytes)")

    job_store[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "step": 0,
        "target_lang": target_lang,
        "input_path": input_path,
        "youtube_url": youtube_url,
        "output_path": None,
        "error": None,
    }

    # Import here to avoid circular import at module load
    from app.worker import process_video
    process_video.delay(job_id, target_lang)
    logger.info(f"[{job_id}] Job queued (lang={target_lang})")

    return {"job_id": job_id, "status": "queued"}


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return JobResponse(**job)


@router.get("/files/{job_id}/{filename}")
async def get_file(job_id: str, filename: str):
    # Security: prevent path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path = Path(settings.storage_path) / job_id / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(str(file_path))

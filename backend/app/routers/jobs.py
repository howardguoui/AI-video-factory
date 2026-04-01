import json as json_lib
import logging
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import settings
from app.models.job import JobResponse
from app.state import get_all_job_ids, get_job_data, set_job

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/jobs", status_code=202)
async def create_job(
    file: UploadFile | None = File(default=None),
    youtube_url: str | None = Form(default=None),
    target_lang: str = Form(default="zh"),
    pipeline_mode: str = Form(default="dubbing"),
    tts_engine: str = Form(default="qwen3"),
    llm_model: str | None = Form(default=None),
):
    if file is None and not youtube_url:
        raise HTTPException(status_code=400, detail="Either file or youtube_url must be provided")

    job_id = str(uuid4())
    job_dir = Path(settings.storage_path) / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    input_path = None
    label = youtube_url or ""
    if file:
        input_path = str(job_dir / "input.mp4")
        content = await file.read()
        with open(input_path, "wb") as f:
            f.write(content)
        label = file.filename or "uploaded file"
        logger.info(f"[{job_id}] Saved upload: {input_path} ({len(content)} bytes)")

    resolved_model = llm_model or settings.translation_model

    set_job(job_id, {
        "job_id": job_id,
        "status": "queued",
        "step": 0,
        "step_progress": 0.0,
        "step_detail": None,
        "target_lang": target_lang,
        "pipeline_mode": pipeline_mode,
        "tts_engine": tts_engine,
        "llm_model": resolved_model,
        "label": label,
        "input_path": input_path,
        "youtube_url": youtube_url,
        "output_path": None,
        "error": None,
    })

    from app.worker import process_video
    process_video.delay(job_id, target_lang, pipeline_mode, tts_engine, resolved_model)
    logger.info(
        f"[{job_id}] Job queued "
        f"(lang={target_lang}, mode={pipeline_mode}, tts={tts_engine}, llm={resolved_model})"
    )

    return {"job_id": job_id, "status": "queued", "label": label}


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    job = get_job_data(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    valid_fields = JobResponse.model_fields.keys()
    return JobResponse(**{k: v for k, v in job.items() if k in valid_fields})


@router.delete("/jobs/cleanup", status_code=200)
async def cleanup_jobs():
    """Delete intermediate temp files for all completed/failed jobs."""
    try:
        from app.cleanup import cleanup_completed_jobs
        cleaned = cleanup_completed_jobs()
        return {"status": "ok", "cleaned": cleaned}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/files/{job_id}/{filename}")
async def get_file(job_id: str, filename: str):
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    file_path = Path(settings.storage_path) / job_id / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(file_path))


@router.get("/ollama/models")
async def get_ollama_models():
    """List models currently available in local Ollama installation."""
    base = settings.ollama_base_url.rstrip("/").replace("/v1", "")
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=3) as resp:
            data = json_lib.loads(resp.read())
        models = [m.get("name", "") for m in data.get("models", [])]
        return {"models": [m for m in models if m], "default": settings.translation_model}
    except Exception as e:
        return {"models": [], "default": settings.translation_model, "error": str(e)}

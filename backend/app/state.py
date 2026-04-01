import json
import redis as redis_lib
from app.config import settings

_redis = redis_lib.from_url(settings.redis_url, decode_responses=True)
JOB_TTL = 60 * 60 * 24  # 24 hours


def _key(job_id: str) -> str:
    return f"job:{job_id}"


def set_job(job_id: str, data: dict) -> None:
    _redis.setex(_key(job_id), JOB_TTL, json.dumps(data))


def get_job_data(job_id: str) -> dict | None:
    raw = _redis.get(_key(job_id))
    return json.loads(raw) if raw else None


def get_all_job_ids() -> list[str]:
    """Return all job IDs currently stored in Redis."""
    keys = _redis.keys("job:*")
    return [k.replace("job:", "") for k in keys]


def update_status(
    job_id: str,
    status: str | None,
    step: int | None = None,
    step_progress: float | None = None,
    step_detail: str | None = None,
    output_path: str | None = None,
    error: str | None = None,
    source_vtt: str | None = None,
    translated_vtt: str | None = None,
    bilingual_download: str | None = None,
) -> None:
    data = get_job_data(job_id) or {}
    if status is not None:
        data["status"] = status
    if step is not None:
        data["step"] = step
    if step_progress is not None:
        data["step_progress"] = step_progress
    if step_detail is not None:
        data["step_detail"] = step_detail
    if output_path is not None:
        data["output_path"] = output_path
    if error is not None:
        data["error"] = error
    if source_vtt is not None:
        data["source_vtt"] = source_vtt
    if translated_vtt is not None:
        data["translated_vtt"] = translated_vtt
    if bilingual_download is not None:
        data["bilingual_download"] = bilingual_download
    set_job(job_id, data)

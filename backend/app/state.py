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


def update_status(
    job_id: str,
    status: str,
    step: int | None = None,
    output_path: str | None = None,
    error: str | None = None,
    source_vtt: str | None = None,
    translated_vtt: str | None = None,
    bilingual_download: str | None = None,
) -> None:
    data = get_job_data(job_id) or {}
    data["status"] = status
    if step is not None:
        data["step"] = step
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

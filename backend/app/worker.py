# Stub — pipeline wired in Task 4
from celery import Celery
from app.config import settings

celery_app = Celery(
    "video_translate",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]


@celery_app.task(name="process_video")
def process_video(job_id: str, target_lang: str) -> dict:
    """Main pipeline task — stub, implemented in Task 4."""
    return {"job_id": job_id, "status": "stub"}

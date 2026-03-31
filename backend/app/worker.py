import json
import logging
import time
from contextlib import contextmanager

from celery import Celery
from celery.exceptions import SoftTimeLimitExceeded
from celery.signals import worker_shutdown

from app.config import settings
from app.state import update_status, get_job_data

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Celery app
# ---------------------------------------------------------------------------

celery_app = Celery(
    "video_translate",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]

# Re-queue the task if the worker process is killed mid-run (CUDA crash, OOM, SIGKILL).
# The message stays in Redis until the task is explicitly acknowledged on completion.
celery_app.conf.task_acks_late = True
celery_app.conf.task_reject_on_worker_lost = True

# Soft limit raises SoftTimeLimitExceeded inside the task (catchable).
# Hard limit sends SIGKILL after an additional grace period.
celery_app.conf.task_soft_time_limit = 7200   # 2 hours
celery_app.conf.task_time_limit = 7500        # 2h5m hard kill


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_update_status(job_id: str, status: str, **kwargs) -> None:
    """
    Wrapper around update_status that never raises.
    A Redis failure here should not mask the real pipeline error.
    """
    try:
        update_status(job_id, status, **kwargs)
    except Exception as e:
        logger.error(f"[{job_id}] Status update to '{status}' failed (Redis?): {e}")


@contextmanager
def _step(job_id: str, name: str):
    """
    Context manager for a single pipeline step.
    - Logs start, elapsed time, and success/failure
    - Re-raises exceptions wrapped with the step name so the UI shows
      exactly which step failed (e.g. "Step 'transcribe' failed after 42s: ...")
    """
    t0 = time.monotonic()
    logger.info(f"[{job_id}] ▶ {name}")
    try:
        yield
    except SoftTimeLimitExceeded:
        raise  # propagate to outer handler unchanged
    except Exception as exc:
        elapsed = time.monotonic() - t0
        raise RuntimeError(f"Step '{name}' failed after {elapsed:.1f}s: {exc}") from exc
    else:
        elapsed = time.monotonic() - t0
        logger.info(f"[{job_id}] ✓ {name} ({elapsed:.1f}s)")


def _free_gpu() -> None:
    """Best-effort VRAM release — safe to call even when CUDA is unavailable."""
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
    except Exception:
        pass


def _is_cuda_oom(msg: str) -> bool:
    return any(kw in msg for kw in ("CUDA out of memory", "OutOfMemoryError", "out of memory"))


def _is_transient(msg: str) -> bool:
    return any(kw in msg for kw in (
        "ConnectionError", "TimeoutError", "redis", "ECONNREFUSED",
        "Connection refused", "BrokenPipeError",
    ))


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------

@celery_app.task(
    name="process_video",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def process_video(self, job_id: str, target_lang: str, pipeline_mode: str = "dubbing") -> dict:
    from app.services.mux import extract_audio, mux_video, create_bilingual_download
    from app.services.asr import transcribe
    from app.services.translate import translate_srt
    from app.services.tts import synthesize_tts

    attempt = self.request.retries + 1
    logger.info(
        f"[{job_id}] Pipeline started "
        f"(lang={target_lang}, mode={pipeline_mode}, attempt={attempt}/{self.max_retries + 1})"
    )

    try:
        _safe_update_status(job_id, "extracting_audio", step=1)
        with _step(job_id, "extract_audio"):
            audio_path = extract_audio(job_id)

        _safe_update_status(job_id, "transcribing", step=2)
        with _step(job_id, "transcribe"):
            srt_path = transcribe(audio_path, job_id)

        _safe_update_status(job_id, "translating", step=3)
        with _step(job_id, "translate"):
            translated_srt_path = translate_srt(srt_path, target_lang)

        if pipeline_mode == "subtitles_only":
            _safe_update_status(job_id, "muxing", step=4)
            with _step(job_id, "mux_video"):
                output_video_path, source_vtt, translated_vtt = mux_video(
                    job_id, audio_path, srt_path, translated_srt_path
                )

            _safe_update_status(job_id, "rendering_downloads", step=5)
            with _step(job_id, "bilingual_download"):
                bilingual_dl = create_bilingual_download(job_id, srt_path, translated_srt_path)

            _safe_update_status(
                job_id, "done", step=6,
                output_path=output_video_path,
                source_vtt=source_vtt,
                translated_vtt=translated_vtt,
                bilingual_download=bilingual_dl,
            )

        else:
            _safe_update_status(job_id, "synthesizing", step=4)
            with _step(job_id, "synthesize_tts"):
                dubbed_audio_path = synthesize_tts(
                    translated_srt_path, audio_path, job_id,
                    target_lang, source_srt_path=srt_path,
                )

            _safe_update_status(job_id, "muxing", step=5)
            with _step(job_id, "mux_video"):
                output_video_path, source_vtt, translated_vtt = mux_video(
                    job_id, dubbed_audio_path, srt_path, translated_srt_path
                )

            _safe_update_status(job_id, "rendering_downloads", step=6)
            with _step(job_id, "bilingual_download"):
                bilingual_dl = create_bilingual_download(job_id, srt_path, translated_srt_path)

            _safe_update_status(
                job_id, "done", step=7,
                output_path=output_video_path,
                source_vtt=source_vtt,
                translated_vtt=translated_vtt,
                bilingual_download=bilingual_dl,
            )

        logger.info(f"[{job_id}] Pipeline complete")
        return {"job_id": job_id, "status": "done", "output_path": output_video_path}

    except SoftTimeLimitExceeded:
        limit = celery_app.conf.task_soft_time_limit
        msg = f"Job exceeded the {limit}s time limit and was cancelled"
        logger.error(f"[{job_id}] {msg}")
        _free_gpu()
        _safe_update_status(job_id, "failed", error=msg)
        raise  # don't retry — if it timed out once it will again

    except Exception as exc:
        _free_gpu()
        error_msg = str(exc)

        # CUDA out of memory — not transient, don't retry
        if _is_cuda_oom(error_msg):
            user_msg = (
                "GPU ran out of memory. Try reducing asr_chunk_minutes "
                "or switching to a smaller Whisper model."
            )
            logger.error(f"[{job_id}] CUDA OOM: {error_msg}")
            _safe_update_status(job_id, "failed", error=user_msg)
            raise

        # Transient infrastructure error (Redis, network) — retry
        if _is_transient(error_msg) and attempt <= self.max_retries:
            logger.warning(
                f"[{job_id}] Transient error on attempt {attempt}, "
                f"retrying in {self.default_retry_delay}s: {exc}"
            )
            _safe_update_status(
                job_id, "retrying",
                error=f"Attempt {attempt} failed, retrying: {error_msg}",
            )
            raise self.retry(exc=exc)

        # All other errors — mark failed, log full traceback
        logger.exception(f"[{job_id}] Pipeline failed: {exc}")
        _safe_update_status(job_id, "failed", error=error_msg)
        raise


# ---------------------------------------------------------------------------
# Worker lifecycle
# ---------------------------------------------------------------------------

@worker_shutdown.connect
def on_worker_shutdown(sender, **kwargs):
    """
    On clean worker shutdown (Ctrl+C / SIGTERM), find any jobs still marked
    as in-progress and set them to failed so the UI doesn't spin forever.
    This covers graceful shutdowns; hard kills (SIGKILL) are handled by
    task_acks_late + task_reject_on_worker_lost (re-queued automatically).
    """
    in_progress = {
        "extracting_audio", "transcribing", "translating",
        "synthesizing", "muxing", "rendering_downloads", "retrying",
    }
    try:
        import redis as redis_lib
        r = redis_lib.from_url(settings.redis_url, decode_responses=True)
        for key in r.scan_iter("job:*"):
            try:
                raw = r.get(key)
                if not raw:
                    continue
                data = json.loads(raw)
                if data.get("status") in in_progress:
                    data["status"] = "failed"
                    data["error"] = "Worker shut down while this job was running"
                    r.setex(key, 60 * 60 * 24, json.dumps(data))
                    logger.warning(f"Marked stuck job '{key}' as failed on worker shutdown")
            except Exception:
                pass
    except Exception as e:
        logger.error(f"on_worker_shutdown cleanup error: {e}")

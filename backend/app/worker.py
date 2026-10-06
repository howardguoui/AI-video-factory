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


# Soft limit raises SoftTimeLimitExceeded inside the task (catchable).
# Hard limit sends SIGKILL after an additional grace period.
celery_app.conf.task_soft_time_limit = 7200   # 2 hours
celery_app.conf.task_time_limit = 7500        # 2h5m hard kill

# One GPU job at a time, and a job is only acknowledged once it finishes, so a
# worker killed mid-job (SIGKILL, power loss) leaves it in the queue to re-run.
celery_app.conf.task_acks_late = True
celery_app.conf.task_reject_on_worker_lost = True
celery_app.conf.worker_prefetch_multiplier = 1
# Redis re-delivers an unacknowledged task after visibility_timeout; keep it
# above the hard time limit or a long job would start a second time.
celery_app.conf.broker_transport_options = {"visibility_timeout": 3 * 3600}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_update_status(job_id: str, status: str | None, **kwargs) -> None:
    """
    Wrapper around update_status that never raises.
    A Redis failure here should not mask the real pipeline error.
    """
    try:
        update_status(job_id, status, **kwargs)
    except Exception as e:
        logger.error(f"[{job_id}] Status update to '{status}' failed (Redis?): {e}")


def _make_progress_cb(job_id: str):
    """Return a progress callback that writes step_progress + step_detail to Redis."""
    def cb(progress: float, detail: str) -> None:
        _safe_update_status(job_id, None, step_progress=min(progress, 1.0), step_detail=detail)
    return cb


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
def process_video(
    self,
    job_id: str,
    target_lang: str,
    pipeline_mode: str = "dubbing",
    tts_engine: str = "qwen3",
    llm_model: str | None = None,
) -> dict:
    from app.services.mux import extract_audio, mux_video, create_bilingual_download, export_mp3, srt_to_vtt
    from app.services.asr import transcribe
    from app.services.translate import translate_srt, translate_text
    from app.services.tts import synthesize_tts
    from app.services.download import download_video, extract_webpage_text

    attempt = self.request.retries + 1
    progress_cb = _make_progress_cb(job_id)
    logger.info(
        f"[{job_id}] Pipeline started "
        f"(lang={target_lang}, mode={pipeline_mode}, tts={tts_engine}, "
        f"llm={llm_model}, attempt={attempt}/{self.max_retries + 1})"
    )

    try:
        job_data = get_job_data(job_id) or {}
        source_url = job_data.get("source_url")

        # ---- WEBPAGE PIPELINE ------------------------------------------------
        if pipeline_mode == "webpage":
            _safe_update_status(job_id, "downloading", step=1, step_progress=0.0, step_detail="Fetching webpage content...")
            with _step(job_id, "extract_webpage"):
                source_txt = extract_webpage_text(job_id, source_url)

            _safe_update_status(job_id, "translating", step=2, step_progress=0.0, step_detail="Starting translation...")
            with _step(job_id, "translate_text"):
                translated_txt = translate_text(
                    source_txt, target_lang,
                    llm_model=llm_model,
                    progress_callback=progress_cb,
                )

            _safe_update_status(job_id, "done", step=3, step_progress=1.0, step_detail=None, output_path=translated_txt)
            logger.info(f"[{job_id}] Pipeline complete")
            return {"job_id": job_id, "status": "done", "output_path": translated_txt}

        # ---- VIDEO PIPELINE --------------------------------------------------

        # Optional first step: download from URL (YouTube, Bilibili, etc.)
        if source_url:
            _safe_update_status(job_id, "downloading", step=1, step_progress=0.0, step_detail="Downloading video...")
            with _step(job_id, "download_video"):
                download_video(job_id, source_url)

        _safe_update_status(job_id, "extracting_audio", step=1, step_progress=0.0, step_detail="Extracting audio track")
        with _step(job_id, "extract_audio"):
            audio_path = extract_audio(job_id)

        _safe_update_status(job_id, "transcribing", step=2, step_progress=0.0, step_detail="Loading Whisper model...")
        with _step(job_id, "transcribe"):
            srt_path = transcribe(audio_path, job_id)
        _safe_update_status(job_id, None, step_progress=1.0, step_detail="Transcription complete")

        _safe_update_status(job_id, "translating", step=3, step_progress=0.0, step_detail="Starting translation...")
        with _step(job_id, "translate"):
            translated_srt_path = translate_srt(
                srt_path, target_lang,
                llm_model=llm_model,
                progress_callback=progress_cb,
            )

        if pipeline_mode == "subtitles_only":
            _safe_update_status(job_id, "muxing", step=4, step_progress=0.0, step_detail="Combining video and subtitles")
            with _step(job_id, "mux_video"):
                output_video_path, source_vtt, translated_vtt = mux_video(
                    job_id, audio_path, srt_path, translated_srt_path
                )

            _safe_update_status(job_id, "rendering_downloads", step=5, step_progress=0.0, step_detail="Rendering bilingual download")
            with _step(job_id, "bilingual_download"):
                bilingual_dl = create_bilingual_download(job_id, srt_path, translated_srt_path)

            _safe_update_status(
                job_id, "done", step=6,
                step_progress=1.0, step_detail=None,
                output_path=output_video_path,
                source_vtt=source_vtt,
                translated_vtt=translated_vtt,
                bilingual_download=bilingual_dl,
            )
            result_output = output_video_path

        elif pipeline_mode == "mp3_only":
            _safe_update_status(job_id, "synthesizing", step=4, step_progress=0.0, step_detail="Loading TTS model...")
            with _step(job_id, "synthesize_tts"):
                dubbed_audio_path = synthesize_tts(
                    translated_srt_path, audio_path, job_id,
                    target_lang, source_srt_path=srt_path,
                    tts_engine=tts_engine,
                    progress_callback=progress_cb,
                )

            _safe_update_status(job_id, "exporting_mp3", step=5, step_progress=0.0, step_detail="Encoding MP3...")
            with _step(job_id, "export_mp3"):
                mp3_path = export_mp3(job_id, dubbed_audio_path)

            _safe_update_status(
                job_id, "done", step=6,
                step_progress=1.0, step_detail=None,
                output_path=mp3_path,
            )
            result_output = mp3_path

        elif pipeline_mode == "subtitles_export":
            _safe_update_status(job_id, "exporting_subtitles", step=4, step_progress=0.0, step_detail="Converting subtitles...")
            with _step(job_id, "export_subtitles"):
                source_vtt = srt_to_vtt(srt_path)
                translated_vtt = srt_to_vtt(translated_srt_path)

            _safe_update_status(
                job_id, "done", step=5,
                step_progress=1.0, step_detail=None,
                source_vtt=source_vtt,
                translated_vtt=translated_vtt,
            )
            result_output = translated_srt_path

        else:  # "dubbing" (default)
            _safe_update_status(job_id, "synthesizing", step=4, step_progress=0.0, step_detail="Loading TTS model...")
            with _step(job_id, "synthesize_tts"):
                dubbed_audio_path = synthesize_tts(
                    translated_srt_path, audio_path, job_id,
                    target_lang, source_srt_path=srt_path,
                    tts_engine=tts_engine,
                    progress_callback=progress_cb,
                )

            _safe_update_status(job_id, "muxing", step=5, step_progress=0.0, step_detail="Combining video and dubbed audio")
            with _step(job_id, "mux_video"):
                output_video_path, source_vtt, translated_vtt = mux_video(
                    job_id, dubbed_audio_path, srt_path, translated_srt_path
                )

            _safe_update_status(job_id, "rendering_downloads", step=6, step_progress=0.0, step_detail="Rendering bilingual download")
            with _step(job_id, "bilingual_download"):
                bilingual_dl = create_bilingual_download(job_id, srt_path, translated_srt_path)

            _safe_update_status(
                job_id, "done", step=7,
                step_progress=1.0, step_detail=None,
                output_path=output_video_path,
                source_vtt=source_vtt,
                translated_vtt=translated_vtt,
                bilingual_download=bilingual_dl,
            )
            result_output = output_video_path

        logger.info(f"[{job_id}] Pipeline complete")
        return {"job_id": job_id, "status": "done", "output_path": result_output}

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

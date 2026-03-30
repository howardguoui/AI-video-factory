import logging
from celery import Celery
from app.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "video_translate",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]


@celery_app.task(name="process_video", bind=True)
def process_video(self, job_id: str, target_lang: str, pipeline_mode: str = "dubbing") -> dict:
    from app.state import update_status
    from app.services.mux import extract_audio, mux_video, create_bilingual_download
    from app.services.asr import transcribe
    from app.services.translate import translate_srt
    from app.services.tts import synthesize_tts

    try:
        logger.info(f"[{job_id}] Pipeline started (lang={target_lang}, mode={pipeline_mode})")

        update_status(job_id, "extracting_audio", step=1)
        audio_path = extract_audio(job_id)
        logger.info(f"[{job_id}] Audio extracted: {audio_path}")

        update_status(job_id, "transcribing", step=2)
        srt_path = transcribe(audio_path, job_id)
        logger.info(f"[{job_id}] Transcription complete: {srt_path}")

        update_status(job_id, "translating", step=3)
        translated_srt_path = translate_srt(srt_path, target_lang)
        logger.info(f"[{job_id}] Translation complete: {translated_srt_path}")

        if pipeline_mode == "subtitles_only":
            # Skip TTS — keep original audio, just embed bilingual subtitles
            update_status(job_id, "muxing", step=4)
            output_video_path, source_vtt, translated_vtt = mux_video(
                job_id, audio_path, srt_path, translated_srt_path
            )
            logger.info(f"[{job_id}] Muxing complete (subtitles only): {output_video_path}")

            update_status(job_id, "rendering_downloads", step=5)
            bilingual_dl = create_bilingual_download(job_id, srt_path, translated_srt_path)

            update_status(
                job_id, "done", step=6,
                output_path=output_video_path,
                source_vtt=source_vtt,
                translated_vtt=translated_vtt,
                bilingual_download=bilingual_dl,
            )
        else:
            # Full dubbing pipeline
            update_status(job_id, "synthesizing", step=4)
            dubbed_audio_path = synthesize_tts(translated_srt_path, audio_path, job_id, target_lang, source_srt_path=srt_path)
            logger.info(f"[{job_id}] TTS synthesis complete: {dubbed_audio_path}")

            update_status(job_id, "muxing", step=5)
            output_video_path, source_vtt, translated_vtt = mux_video(
                job_id, dubbed_audio_path, srt_path, translated_srt_path
            )
            logger.info(f"[{job_id}] Muxing complete: {output_video_path}")

            update_status(job_id, "rendering_downloads", step=6)
            bilingual_dl = create_bilingual_download(job_id, srt_path, translated_srt_path)
            logger.info(f"[{job_id}] Download video ready")

            update_status(
                job_id, "done", step=7,
                output_path=output_video_path,
                source_vtt=source_vtt,
                translated_vtt=translated_vtt,
                bilingual_download=bilingual_dl,
            )

        logger.info(f"[{job_id}] Pipeline complete")
        return {"job_id": job_id, "status": "done", "output_path": output_video_path}

    except Exception as exc:
        logger.exception(f"[{job_id}] Pipeline failed: {exc}")
        update_status(job_id, "failed", error=str(exc))
        raise

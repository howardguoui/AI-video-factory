# Roadmap

Shipped items move to the bottom with the date. Quality and speed numbers are only committed from real runs on the
RTX 5070 Ti (`backend/scripts/publish_results.ps1`); nothing in `backend/evals/results/` is hand-written.
Day-to-day session notes stay in PROGRESS.md.

## Next

- [ ] **First published quality benchmark:** FLEURS zh→en and ja→en (50 clips each), ASR CER and speed for
      large-v3 vs large-v3-turbo, translation chrF++ per model; commit `backend/evals/results/latest.md` and replace
      the estimated figures in `docs/reviews/2026-10-04-model-upgrade.md` with measured ones.
- [ ] **End-to-end GPU run of every mode** (dub, mp3_only, subtitles_export, webpage) with per-stage timings
      recorded per job, so speed-ups are measured, not estimated.
- [ ] **Per-stage VRAM telemetry:** sample NVML during each stage and store peak VRAM per stage on the job, shown
      on the job page; proves the four stages fit in 16 GB and shows the headroom.
- [ ] **Context-aware translation:** pass the previous segments as context to the LLM and measure the chrF++ change
      on FLEURS before switching the default.
- [ ] **Remove the RecentJobs remount key** in `app/page.tsx` now that the job-history store notifies subscribers.
- [ ] **Speaker diarization** so multi-speaker videos get one cloned voice per speaker.
- [ ] **Background music separation** (Demucs) so dubbing keeps the original music bed.
- [ ] **In-browser trim editor** with FFmpeg.wasm (plan in FUTURE.md).
- [ ] **Lip-sync** (Wav2Lip) as an optional final stage.

## Shipped

- 2026-10-07: Backend unit tests without a GPU: error classification (CUDA OOM vs transient), SRT helpers,
  translation batching and retry against a fake OpenAI-compatible server. Fixed SRT timestamps that rounded to
  ":60" seconds, and Ollama connection drops that were never retried.
- 2026-10-06: CI for backend tests and frontend lint / typecheck / build.
- 2026-10-06: Celery late acknowledgement, re-queue on worker loss, one GPU job per worker.
- 2026-10-06: FLEURS quality benchmark (CER/WER, real-time factor, chrF++, BLEU, full cascade).
- 2026-10-06: frontend lint clean; job history via a subscribable store.
- 2026-10-04: URL ingestion (yt-dlp), webpage translation, MP3-only and subtitle-export modes, chat API.

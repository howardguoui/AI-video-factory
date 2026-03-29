# Project Progress Log
> Project: AI Video Translation Platform
> Started: 2026-03-28

---

## Current Status: PLANNING

---

## Session Log

### Session 1 — 2026-03-28
**Completed:**
- [x] Research Cutrix product (https://www.cutrix.cc/zh)
- [x] Define 4-stage pipeline (ASR → Translation → TTS → Lip-sync)
- [x] Evaluate TTS options: ElevenLabs vs Qwen3-TTS vs IndexTTS2 vs GPT-SoVITS
- [x] Decision: Qwen3-TTS 1.7B (beats ElevenLabs on speaker similarity, free, self-hosted)
- [x] Confirm hardware: RTX 5070 Ti (16GB VRAM, CUDA 12.8) — full pipeline fits locally
- [x] Study pyVideoTrans as reference implementation
- [x] Document full requirements in REQUIREMENTS.md

**Decisions Made:**
| Decision | Choice | Reason |
|---|---|---|
| TTS Engine | Qwen3-TTS 1.7B | Free, beats ElevenLabs on similarity (0.789 vs 0.646), 3s voice clone |
| ASR | faster-whisper Large-v3 | Free, local, best quality |
| Translation | GPT-4o API | Best quality for idioms/drama content |
| Frontend | Next.js + Tailwind | User knows JS |
| Backend | FastAPI | Python-native AI libraries |
| Queue | Celery + Redis | Background video processing |
| Lip-sync | Defer to Phase 3 | MVP ships without it |

**Next Steps:**
- [ ] Scaffold Next.js frontend project
- [ ] Scaffold FastAPI backend project
- [ ] Install and test faster-whisper on local GPU
- [ ] Install and test Qwen3-TTS on local GPU
- [ ] Build video upload UI component
- [ ] Wire ASR stage end-to-end

---

## Backlog

- Speaker diarization (Phase 2)
- Demucs background music separation (Phase 2)
- YouTube URL input via yt-dlp (Phase 2)
- Wav2Lip lip-sync (Phase 3)
- Email auth (Phase 2)
- Language selector UI

---

## Architecture Diagram

```
[Browser UI - Next.js]
        |
        | POST /api/jobs (video file or YouTube URL)
        v
[FastAPI Backend]
        |
        | enqueue job
        v
[Celery Worker]
        |
        |-- 1. Extract audio (FFmpeg)
        |-- 2. Transcribe (faster-whisper) --> SRT
        |-- 3. Translate (GPT-4o) --> translated SRT
        |-- 4. Clone voice + TTS (Qwen3-TTS) --> dubbed audio
        |-- 5. Mux video + audio (FFmpeg)
        |-- 6. [Phase 3] Lip-sync (Wav2Lip)
        |
        v
[Storage: Local / S3]
        |
        v
[Browser UI: preview + download]
```

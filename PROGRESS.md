# Project Progress Log
> Project: AI Video Translation Platform
> Started: 2026-03-28

---

## Current Status: MVP COMPLETE — maintenance / portfolio (see `E:\ClaudeProject\plans\2026-10-03-next-projects.md`)

---

## Session Log

### Session — 2026-10-06
**Completed:**
- [x] Frontend lint clean (`eslint .` → 0 problems; was 1 error + 2 warnings). `tsc --noEmit` passes; `next build --webpack` passes.
  - `RecentJobs.tsx`: reads job history with `useSyncExternalStore` instead of `setState` in an effect. `lib/jobHistory.ts` now notifies subscribers on every write and listens for cross-tab `storage` events, so the Navbar and home-page lists stay in sync without remounting.
  - `VideoPlayer.tsx`: one effect per subtitle track keyed on its URL, with a cancel guard so a late response can't overwrite newer cues.
  - `JobStatus.tsx`: removed unused `isFuture`.
- [x] Quality evaluation (`backend/evals/quality_eval.py`) on Google FLEURS: ASR error rate (CER for zh/ja/ko, WER otherwise) and real-time factor per Whisper model; translation chrF++ and BLEU per LLM using the app's own `_translate_batch`; full speech→translation cascade score. 6 unit tests in `backend/tests/test_quality_eval.py`.

**Open:**
- [ ] **Run the quality eval on the RTX machine** to get measured numbers (the figures in `docs/reviews/2026-10-04-model-upgrade.md` are estimates, not runs):
      `cd backend && pip install -r evals/requirements.txt && python -m evals.quality_eval --src zh --tgt en --limit 50`
      Results land in `backend/evals/results/latest.md`; commit them.
- [ ] End-to-end GPU run of the new modes (mp3_only, subtitles_export, webpage) not yet exercised — needs the local RTX machine.
- [ ] `app/page.tsx` still bumps a `key` to remount `RecentJobs` after upload; no longer needed now that the store notifies, safe to remove after a manual check.

### Session — 2026-10-04
**Completed:**
- [x] Verified + committed uncommitted backend work (`5ce718a`): yt-dlp URL download, webpage-text translation, MP3-only and subtitle-export modes, `/api/chat` assistant. Backend compiles and imports; deps installed.
- [x] Frontend: fixed 2 `prefer-const` lint errors (5 → 3 problems); `tsc --noEmit` passes. Changes are **uncommitted** — see open item below.
- [x] Synced REQUIREMENTS.md checkboxes with the code.

**Open:**
- [x] `frontend/` folded into this repo (2026-10-04, `b25f4a6`); old nested history in `.frontend-git-backup/`.
- [x] Remaining frontend lint: `RecentJobs.tsx` setState-in-effect error, 2 hook-deps warnings. (fixed 2026-10-06)
- [ ] End-to-end GPU run of the new modes (mp3_only, subtitles_export, webpage) not yet exercised.

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
- [x] Scaffold Next.js frontend project
- [x] Scaffold FastAPI backend project
- [x] Install and test faster-whisper on local GPU
- [x] Install and test Qwen3-TTS on local GPU
- [x] Build video upload UI component
- [x] Wire ASR stage end-to-end

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

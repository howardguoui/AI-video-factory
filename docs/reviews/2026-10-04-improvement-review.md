# AI-Video-Factory: Improvement Review
**Date:** 2026-10-04 | **Hardware:** RTX 5070 Ti 16GB VRAM

---

## Part A: Code Review Findings

| Severity | File:Line | Issue | Fix |
|----------|-----------|-------|-----|
| **HIGH** | routers/jobs.py:94-101 | Path traversal: `"..", "/", "\\"` check bypassed by URL encoding (`%2e%2e`) and symlinks | Use `Path.resolve()`, verify result is within job_dir; reject if not |
| **HIGH** | routers/jobs.py:22 | SSRF via `source_url`: no protocol/domain validation; `file://` URLs leak local files | Whitelist `http(s)://` only; validate domain against blocklist (localhost, 127.0.0.1, 10.x, etc.) |
| **HIGH** | routers/jobs.py:38-41 | Unbounded upload: reads entire file into memory without size check; 10GB file → OOM | Check `Content-Length` header; reject if >2GB; use streaming upload (e.g., `shutil.copyfileobj`) |
| **MEDIUM** | main.py:26 | CORS hardcoded to localhost; breaks on production deployment | Read from env var; validate against whitelist per deployment |
| **MEDIUM** | worker.py:158-161 | Missing validation: if URL download fails or file upload is None, `extract_audio()` crashes with unclear error | Validate `input_path` exists before step 1; raise user-friendly error |
| **MEDIUM** | mux.py:161-162 | Windows path escaping bug: `_ff_path()` escapes colons but FFmpeg filter needs quotes around path for spaces | Use quotes: `f"'{{_ff_path(...)}}'"`; test with spaces in storage_path |
| **MEDIUM** | worker.py:313-342 | Race condition: `on_worker_shutdown()` scans job keys without lock; task finish between scan & update overwrites success with "failed" | Use Redis WATCH/MULTI or Lua script for atomic scan-and-update |
| **LOW** | download.py:20-29 | No timeout on `yt-dlp.download()`; can hang indefinitely on bad URLs | Add `socket_timeout=30` to ydl_opts; wrap in try-except for timeout exception |
| **LOW** | tts.py:421-426 | VRAM not explicitly reclaimed: `torch.cuda.empty_cache()` alone doesn't sync; model destruction may lag | Add `torch.cuda.synchronize()` before process exit |
| **LOW** | download.py:49 | `trafilatura.fetch_url()` has no timeout; blocks worker indefinitely | Add `timeout=10` parameter; catch `TimeoutError` |

---

## Part B: Bigger Improvements (Ranked by User Value ÷ Effort)

### 1. **Speaker Diarization + Multi-Role Dubbing** ⭐ 9/10 UX → 2 days
**Why:** All top competitors (HeyGen, Rask, ElevenLabs) separate speakers; allows realistic multi-person videos.

**Implementation:**
- **ASR Layer:** Replace `faster-whisper` with [WhisperX](https://github.com/m-bain/whisperx) (adds pyannote diarization + word-level timestamps)
  - Install: `pip install git+https://github.com/m-bain/whisperx.git`
  - Change: `asr.py` — use `WhisperModel.transcribe()` + `diarize_model.apply()` in subprocess
  - VRAM: +1.5GB (pyannote ≈ 1GB, fits in 16GB alongside whisper)
  - Output: SRT now includes `{speaker}:` prefix per segment
  
- **TTS Layer:** Assign voice clones per speaker
  - Parse speaker labels from diarized SRT in `tts.py`
  - For each speaker, extract a separate reference clip from corresponding timestamps
  - Generate TTS with speaker-specific ref_audio
  - Cost: negligible (reuse existing voice clone logic)

- **Files to touch:** `asr.py` (ASR subprocess), `tts.py` (speaker-aware synthesis), `services/translate.py` (preserve speaker labels in SRT)

---

### 2. **Vocal/Background Separation + Audio Ducking** ⭐ 7.5/10 UX → 1.5 days
**Why:** Preserve background music, fade it during dubbing (pyVideoTrans has this; critical for content creators).

**Implementation:**
- **Separation:** Use [Demucs v4](https://github.com/facebookresearch/demucs) (4-stem: vocals, drums, bass, other)
  - Install: `pip install demucs`
  - Add step after `extract_audio()` in worker: `separate_stems(audio_path, job_id)` → returns `{vocals.wav, background.wav}`
  - VRAM: ~2GB peak (fits)
  - Time: ~30s for 1min video
  
- **Ducking:** Mix dubbed audio over background at -12dB
  - In `tts.py` `_assemble_audio_clips()`, load background stems and blend using numpy
  - Formula: `final_audio = 0.7 * dubbed_audio + 0.3 * background_audio`
  
- **Files to touch:** `mux.py` (add `separate_stems()` function), `worker.py` (call after audio extraction), `tts.py` (mix in assembly)

---

### 3. **Subtitle Quality + Smart Line Breaking** ⭐ 6/10 UX → 1 day
**Why:** Netflix/broadcast standard is 32–42 chars/line; current SRT has no limits; readable subtitles = more professional output.

**Implementation:**
- **Character Limit Enforcement:**
  - Add to `translate.py`: function `enforce_subtitle_limits(srt_path, max_chars=42, max_lines=2)`
  - After translation, re-wrap each segment using `textwrap.wrap(text, width=42)` + linguistic awareness (don't break mid-phrase)
  - If segment exceeds 2 lines, flag for manual review or split into sub-segments with adjusted timing
  
- **Linguistic Line Breaking:**
  - Use simple heuristics: break at sentence boundaries (`.!?`), commas, or last space within 42-char window
  - Don't break mid-word or after articles (a/an/the)
  
- **Files to touch:** `translate.py` (add `enforce_subtitle_limits()`), `worker.py` (call after translation step)

---

## Quick Wins (<1h each)

1. **Add input validation for `target_lang` and `pipeline_mode`** (jobs.py:24-25)
   - Check against allowed lists; return 400 if invalid → prevents silent LLM fallback errors

2. **Add explicit timeouts to external service calls** (download.py, translate.py)
   - yt-dlp: `socket_timeout=30`; trafilatura: `timeout=10`; Ollama: `timeout=15`
   - Prevents worker hangs; improves job queue throughput

3. **Store & expose subtitle metadata** (worker.py, jobs.py)
   - After translation, save char count, line count, language pair to job state
   - Return in `/api/jobs/{id}` response → frontend can show "41 chars max" warning badge

4. **Add job cancellation endpoint** (routers/jobs.py)
   - `DELETE /api/jobs/{job_id}` → revoke Celery task, mark as "cancelled"
   - Users can abort stuck jobs without server restart

5. **Implement subtitle editor UI preview** (frontend)
   - Pre-download VTT files; show in-browser with timing scrubber
   - Let users preview before final burn-in → reduce re-renders

---

## Feasibility Summary

All three major improvements are **locally feasible** on RTX 5070 Ti:
- **WhisperX + diarization:** +1.5GB VRAM → still ≤14.5GB total
- **Demucs separation:** +2GB peak, sequential (not concurrent with TTS)
- **Subtitle polishing:** CPU-only, negligible overhead

**Time budget:** ~4 days for all three (shipped incrementally).
**Complexity:** Medium (new libs, moderate integration).
**User impact:** High (feature parity with commercial tools; multi-speaker support is the "wow" feature).

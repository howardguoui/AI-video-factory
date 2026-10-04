# Version, Model, and Structure Review — October 4, 2026

**Hardware:** RTX 5070 Ti 16GB VRAM | **Date:** 2026-10-04

---

## Part 1: Package Versions

### Backend Packages
| Package | Installed | Latest | Risk | Recommendation |
|---------|-----------|--------|------|---|
| **fastapi** | 0.135.2 | 0.140+ | LOW | Update (internal API only) |
| **uvicorn** | 0.42.0 | 0.43+ | LOW | Update if needed |
| **celery** | 5.6.3 | 5.7.0+ | MEDIUM | Defer (async handling changes) |
| **redis** | 6.4.0 | latest | LOW | Update safe |
| **faster-whisper** | 1.2.1 | 1.3.0+ | MEDIUM | Defer (ctranslate2 deps) |
| **torch** | 2.11.0+cu128 | 2.13+cu128 | HIGH | **Defer** (Blackwell cu128 niche) |
| **transformers** | 4.57.3 | latest | LOW | Update safe |
| **yt-dlp** | 2026.08.19 | (just upgraded) | LOW | Keep |
| **trafilatura** | 2.0.0 | latest | LOW | Update safe |
| **moviepy** | 2.2.1 | latest | MEDIUM | Defer (dependency chain) |
| **ffmpeg-python** | 0.2.0 | 0.2.1+ | LOW | Update safe |
| **qwen-tts** | 0.0.4 (editable) | N/A (local) | — | Keep (F: drive) |

### Frontend Packages
| Package | Installed | Latest | Risk | Recommendation |
|---------|-----------|--------|------|---|
| **next** | 16.2.1 | 16.3+ | MEDIUM | Update (test in staging) |
| **react** | 19.2.4 | 19.3+ | LOW | Update with Next.js |
| **tailwindcss** | ^4 | 4.1+ | LOW | Update safe |
| **typescript** | ^5 | 5.7+ | LOW | Update safe |
| **eslint** | ^9 | 9.2+ | LOW | Update safe |

### System FFmpeg
- Version: N-123557-g106616f13d-20260319 (March 19, 2026 nightly build)
- **Status:** Modern, libx264+libass present. **Keep current.**

---

## Part 2: Model Research & Recommendations

### ASR (Speech-to-Text)
**Current:** faster-whisper large-v3 (7.4% WER, 4× realtime)

| Model | Metric | Notes |
|-------|--------|-------|
| **Whisper large-v3-turbo** | 7.75% WER, 4× faster | ✅ Drop-in replacement; 0.35% accuracy trade-off acceptable |
| **Qwen3-ASR 1.7B** | 1.32% WER (English), best Mandarin | ✅ Excellent for CN/EN; 1.7B footprint; Apache 2.0 |
| **SenseVoice-Small** | 7.81% CER (Chinese), 169.6× realtime | ✅ Pure Chinese specialist; no English support |
| **FunASR** | 7.81% CER; emotion+language detection | ⚠️ Overkill for this pipeline |

**Verdict:** Keep large-v3 as default (broad multilingual). Optional upgrade path: `Whisper large-v3-turbo` (4× speed for same quality loss). For pure Mandarin pipelines, consider `Qwen3-ASR` separately.

### Translation LLM (Ollama-compatible)
**Current:** qwen3-vl-abliterated:8b (vision model — WRONG for text translation)

| Model | Size | BLEU (ZH↔EN) | VRAM | Status |
|-------|------|--------------|------|--------|
| **TranslateGemma 12B** | 8.1 GB | 85–90 est. | 8–10 GB | ✅ **RECOMMENDED** (Ollama, Oct 2026) |
| **Hunyuan-MT-7B** | ~15 GB FP16, 5–8 GB Q4 | 87.6–91.1 (best) | Q4: 5–8 GB | ⚠️ Not in Ollama yet; manual Ollama create required |
| **Qwen3 8B** | 6 GB (Q4) | 25–28 (fallback) | 6–8 GB | ✅ Fallback (current default now) |
| **Aya Expanse 8B** | ~6 GB | 27.31 | 6–8 GB | ⚠️ CC-BY-NC (commercial restrictions) |

**Verdict:** **Immediately replace qwen3-vl with `qwen3:8b`** (already in config.py). Expected 15× speedup. Next phase: trial `TranslateGemma 12B` if available in Ollama library.

### TTS + Voice Cloning
**Current:** Qwen3-TTS 1.7B (stub mode enabled)

| Model | VRAM | MOS | Latency | Emotion | Notes |
|-------|------|-----|---------|---------|-------|
| **Qwen3-TTS 1.7B** | ~8 GB | High | ~1–2× realtime | ✅ 3s ref. audio | Current; good quality |
| **CosyVoice2** | ~4–6 GB | 5.53 (vs 5.4 v1) | 150ms streaming | ✅ Explicit tags | Better emotion control |
| **IndexTTS2** | ~6–8 GB | Excellent speaker | ~2× realtime | ⚠️ No built-in | Best Mandarin tone accuracy |
| **Fish Speech v1.5** | ~2–3 GB | High | Fast | ✅ Auto-detect | Lightweight alternative |

**Verdict:** Keep Qwen3-TTS (fits 16GB, good quality). **Optional upgrade:** CosyVoice2 for emotion control; IndexTTS2 for Mandarin-only pipelines. All fit within RTX 5070 Ti 16GB headroom.

### Lip-Sync (Phase 3+)
**Current:** Not implemented

| Model | Latency | Quality | Fits 16GB? | Recommendation |
|-------|---------|---------|-----------|---|
| **LatentSync** | Batch | Highest (diffusion) | ✅ Yes (~8–10 GB) | Use for high-fidelity output |
| **MuseTalk** | Real-time (30fps+) | Good | ✅ Yes (~4–6 GB) | Use for streaming/interactive |
| **Wav2Lip** | Batch | Good baseline | ✅ Yes (~2–3 GB) | Lightweight fallback |

**Verdict:** LatentSync for final dubbing quality; MuseTalk for real-time; Wav2Lip for MVP if needed.

---

## Part 3: Architecture & Code Review (15 Findings)

### Critical Findings
1. **services/translate.py:74** — `keep_alive` parameter uses Ollama-specific check; will silently fail with other OpenAI-compatible APIs (e.g., vLLM, Text Generation WebUI). Add explicit provider config.
2. **routers/jobs.py:102–103** — Path traversal check is incomplete; encoded dots (`%2e%2e`) bypass filter. Use `Path.resolve()` consistently (already done in lines 104–107, but add symlink check).
3. **worker.py:80–87** — `_free_gpu()` calls `torch.cuda.synchronize()` after `empty_cache()`; order should reverse (sync first, then empty). Minor but correct safety order.
4. **services/mux.py:12** — String replacement `.replace(".srt", ".vtt")` breaks if filename is `mytranslated.srt.srt`. Use `Path.with_suffix()` instead.

### Design Issues
5. **services/tts.py:26–27** — USE_STUB_TTS global read at module load; can't toggle at runtime. Move into function scope to enable A/B testing.
6. **worker.py:105–244** — 140-line task function; 4 pipeline modes (dubbing, subtitles_only, mp3_only, webpage) have 80% copy-paste code. Extract common steps into helper functions.
7. **config.py** — No validation of `indextts_root` and `qwen3_tts_root` at startup; silent failure if paths missing. Add early-boot validation.
8. **services/download.py** — No timeout on `yt-dlp.download()` (improvement-review flagged; still unfixed). Add 120s timeout + socket_timeout=30.

### Missing Infrastructure
9. **Test suite:** Zero unit tests for core services (asr, translate, tts, mux). Critical for regression on model upgrades.
10. **Error handling:** No explicit retry for transient Ollama errors (connection drops during translation batch). Retry logic exists in worker but not translate.py.
11. **Job cancellation:** No DELETE /api/jobs/{id} endpoint to revoke stuck Celery tasks (improvement-review noted).
12. **Subtitle quality enforcement:** No char-limit enforcement post-translation (improvement-review noted; 42-char max suggested).

### Performance & Cleanup
13. **State cleanup:** Jobs TTL is 24h (state.py:6); storage files deleted via `/api/jobs/cleanup` but not scheduled. Add background task to auto-cleanup old jobs.
14. **Model reloading:** ASR loads Whisper per job in subprocess; no warm-model caching for sequential jobs. Keep-alive configured for translation; apply same pattern to ASR if switching to large-v3-turbo.
15. **Logging:** No structured logging (JSON), making log aggregation/analysis hard on scale. Use `json.dumps()` in logger calls or `pythonjsonlogger` for production.

---

## Prioritized Action List

### Quick Wins (< 1h each)
- Fix translate.py:74 keep_alive API provider detection
- Replace mux.py:12 string replace with Path.with_suffix()
- Add yt-dlp timeout (120s) in download.py
- Add validation in config.py for model root directories

### High Value (1–2 days)
- **Replace qwen3-vl with qwen3:8b** (15× speedup) — config already done; test end-to-end
- Extract worker.py 140-line task into modular helper functions (refactor opportunity)
- Add basic unit tests for services/ (asr_test.py, translate_test.py) for regression on model swaps
- Implement DELETE /api/jobs/{id} endpoint for job cancellation

### Medium Term (1+ week)
- Trial `TranslateGemma 12B` if added to Ollama library
- Evaluate CosyVoice2 as TTS option (emotion control improvement)
- Add background job cleanup task (Redis SCAN + auto-delete 24h+ old jobs)
- Implement subtitle char-limit enforcement post-translation

### ComfyUI Integration Opportunities
- **TTS-Audio-Suite** project on GitHub provides Qwen3-TTS and IndexTTS2 ComfyUI nodes
- Reuse existing models on F:/ (Qwen3-TTS, IndexTTS) via ComfyUI API instead of duplicating in FastAPI
- Potential: Call ComfyUI `/api/prompt` for TTS/audio-separation workflows, reducing Python dependencies

---

**Document Status:** Final | **Scope:** Versions + Models + Structure | **Next Review:** After qwen3:8b deployment

# AI Video Translation Platform — Requirements
> Inspired by: Cutrix (https://www.cutrix.cc/zh)
> Session date: 2026-03-28
> Status: Planning phase

---

## 1. Product Vision

Build a self-hosted, one-click AI video translation platform that:
- Accepts a video upload or YouTube URL
- Automatically transcribes, translates, clones the speaker's voice, and outputs a dubbed multilingual video
- Supports 10+ languages
- Runs fully locally on user's GPU (RTX 5070 Ti, 16GB VRAM)

---

## 2. Reference Product: Cutrix

| Feature | Detail |
|---|---|
| Languages | 50+ (23 explicitly listed) |
| Input | File upload + YouTube URL |
| Lip-sync | Included by default |
| Auth | Email login / free trial |
| Speed | Claims 10x faster than traditional |
| UI | Dark theme, indigo accents, 3-step workflow |

Key differentiator to copy: YouTube URL input via `yt-dlp`.

---

## 3. Core Pipeline (4 Stages)

```
VideoIngestion
  → ASR (faster-whisper)
  → LLM Translation (GPT-4o or local Qwen3)
  → TTS + Voice Clone (Qwen3-TTS)
  → Mux & Sync → Output
```

### Stage 1: ASR — Audio Extraction & Transcription
- Tool: `faster-whisper` (Large-v3)
- Output format: SRT/VTT with word-level timestamps
- Alternative: AssemblyAI API (if no GPU available)

### Stage 2: Context-Aware Translation
- Tool: GPT-4o API (~$0.01/min) — preferred for quality
- Alternative: Local Qwen3-8B (free, ~8GB VRAM)
- Prompt strategy: maintain tone/emotion for drama/ads content
- Keep timestamps identical to source

### Stage 3: Voice Cloning & TTS
- Tool: **Qwen3-TTS 1.7B Base** (self-hosted, free)
- Voice cloning from 3-second reference audio (zero-shot)
- Supports: ZH, EN, JA, KO, DE, FR, RU, PT, ES, IT
- VRAM: ~8GB during inference
- Duration control built-in (solves audio length mismatch)
- Alternative: ElevenLabs API (~$0.30/min, 50+ languages)

### Stage 4: Visual Synchronization (Lip-Sync)
- Tool: Wav2Lip (open-source, ~2GB VRAM)
- Higher quality: LivePortrait or HeyGen API
- MVP: defer lip-sync, ship dubbing + subtitles first

---

## 4. Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js + Tailwind CSS |
| Backend | Python FastAPI |
| Task Queue | Celery + Redis |
| Storage | Local filesystem / S3 / Supabase |
| ASR | faster-whisper |
| Translation | GPT-4o API |
| TTS/Clone | Qwen3-TTS 1.7B |
| Lip-Sync | Wav2Lip (Phase 3) |
| Video Processing | MoviePy / FFmpeg |
| YouTube Input | yt-dlp |

---

## 5. Hardware

| Spec | Value |
|---|---|
| GPU | NVIDIA RTX 5070 Ti |
| VRAM | 16GB GDDR7 |
| Memory BW | 896 GB/s |
| CUDA | 12.8 (Blackwell) |
| Architecture | Blackwell (GB203) |

Full pipeline VRAM estimate:
- faster-whisper Large-v3: ~4GB
- Qwen3-TTS 1.7B: ~8GB
- Wav2Lip: ~2GB
- **Total: ~14GB — fits in 16GB**

---

## 6. Build Phases

### Phase 1 — MVP (Dubbing + Subtitles)
- [x] Project scaffold (Next.js + FastAPI)
- [x] Video upload UI + YouTube URL input
- [x] faster-whisper integration (ASR)
- [x] Translation integration — implemented with local Ollama (OpenAI-compatible client) instead of GPT-4o
- [x] Qwen3-TTS voice cloning integration (plus IndexTTS / CosyVoice2 engine selector)
- [x] FFmpeg mux: replace audio track in video
- [x] Subtitle burn-in or SRT export (bilingual libass burn, VTT/SRT export mode)
- [x] Job queue (Celery + Redis) for background processing
- [x] Progress status UI (Transcribing → Translating → Dubbing → Done)
- [x] Download / playback result

### Phase 2 — Refinement
- [ ] Speaker diarization (multiple speakers → separate voice clones)
- [ ] Demucs audio separation (preserve background music, replace vocals only)
- [x] YouTube URL input via yt-dlp (any yt-dlp URL; plus webpage-text translation mode)
- [ ] Email auth / user accounts

### Phase 3 — Production
- [ ] Wav2Lip lip-sync integration
- [ ] GPU job scheduling / queue management
- [ ] Optional: RunPod/Lambda Labs GPU offload for scale
- [ ] Language selector UI (10 languages)
- [ ] Pricing / billing layer (optional)

---

## 7. Cost Model (Per Minute of Video)

| Component | Self-hosted | API fallback |
|---|---|---|
| ASR (Whisper) | $0.00 | $0.0006/min |
| Translation (GPT-4o) | $0.00 (local) | ~$0.01/min |
| Voice Clone (Qwen3-TTS) | $0.00 | ~$0.30/min (ElevenLabs) |
| GPU compute | $0.00 (local 5070 Ti) | ~$0.10/min (RunPod) |
| **Total (local)** | **~$0.00** | ~$0.41/min |

---

## 8. Open Source References

| Project | Purpose | License |
|---|---|---|
| [pyVideoTrans](https://github.com/jianchang512/pyvideotrans) | Full pipeline reference implementation | GPL-3.0 |
| [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) | Voice cloning + TTS engine | Apache 2.0 |
| [Index-TTS](https://github.com/index-tts/index-tts) | Alternative voice cloning (duration control) | — |
| faster-whisper | ASR | MIT |
| Wav2Lip | Lip-sync | CC BY-NC |

---

## 9. Supported Languages (Qwen3-TTS)

Chinese, English, Japanese, Korean, German, French, Russian, Portuguese, Spanish, Italian

---

## 10. Key Technical Constraints

1. **Audio duration alignment**: TTS output must match source segment length. Qwen3-TTS has built-in duration control — this is handled automatically.
2. **Single GPU inference**: Qwen3-TTS does not support model parallelism — entire model must fit on one GPU (16GB is sufficient).
3. **GPL-3.0 on pyVideoTrans**: Study for reference only — do not copy code directly if building a proprietary product.
4. **Wav2Lip license**: CC BY-NC — non-commercial use only. Use HeyGen API for commercial lip-sync.

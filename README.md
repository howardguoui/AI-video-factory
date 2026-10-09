# VideoFactory — AI Video Pipeline

A fully local, GPU-accelerated pipeline that translates videos from any language into Chinese (or other target languages). Supports two modes: **Full Dubbing** (replaces audio with AI-synthesized voice) and **Subtitles Only** (keeps original audio, adds bilingual subtitles).

## How It Works

```
Upload MP4
    │
    ▼
Extract Audio (FFmpeg, 16kHz mono WAV)
    │
    ▼
Transcribe (faster-whisper large-v3, CUDA) → source.srt
    │
    ▼
Translate (Ollama / Qwen3-VL, OpenAI-compatible API) → translated.srt
    │
    ├─── [Subtitles Only mode] ────────────────────────────────┐
    │                                                           │
    ▼                                                           │
Synthesize TTS (Qwen3-TTS 1.7B, voice-cloned from source)     │
    │                                                           │
    ▼                                                           │
Mux Video (FFmpeg: replace audio + embed subtitle tracks) ◄────┘
    │
    ▼
Burn Bilingual Subtitles (FFmpeg drawtext: yellow CN bottom, white EN above)
    │
    ▼
Download bilingual_with_subs.mp4
```

## Architecture

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15 + Tailwind CSS |
| API | FastAPI (Python 3.12) |
| Task Queue | Celery + Redis |
| ASR | faster-whisper large-v3 (CUDA float16) |
| Translation | Ollama — `huihui_ai/qwen3-vl-abliterated:8b-instruct` |
| TTS | Qwen3-TTS 1.7B Base (`qwen_tts` package) |
| Media Processing | FFmpeg |
| State Store | Redis (job status, 24h TTL) |

## Hardware Requirements

- NVIDIA GPU with CUDA 12.x (tested on RTX 5070 Ti, 16GB VRAM)
- 16GB+ VRAM recommended (large-v3 Whisper + Qwen3-TTS simultaneously)
- 32GB+ system RAM recommended

## Prerequisites

Install the following before starting:

1. **CUDA Toolkit 12.x** — https://developer.nvidia.com/cuda-downloads
2. **Redis** — `winget install Redis.Redis` (Windows) or `brew install redis` (Mac)
3. **Ollama** — https://ollama.com/download
4. **FFmpeg** (with `libx264` and `libass`) — https://ffmpeg.org/download.html — must be on PATH
5. **Python 3.12** — https://www.python.org/downloads/
6. **Node.js 20+** — https://nodejs.org/

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/howardguoui/AI-video-factory.git
cd AI-video-factory
```

### 2. Backend — Python environment

```bash
cd backend

# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Mac/Linux

# Install dependencies
pip install fastapi uvicorn celery redis pydantic-settings \
            faster-whisper ffmpeg-python soundfile numpy \
            openai python-multipart
```

To enable real TTS synthesis (optional — stub mode works for subtitle-only testing):

```bash
pip install qwen3-tts
```

### 3. Backend — environment variables

Create `backend/.env`:

```env
# Redis
REDIS_URL=redis://localhost:6379/0

# Storage path for uploaded and processed videos
STORAGE_PATH=./storage

# Whisper ASR
WHISPER_MODEL_SIZE=large-v3
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16

# Translation via Ollama
OLLAMA_BASE_URL=http://localhost:11434/v1
TRANSLATION_MODEL=huihui_ai/qwen3-vl-abliterated:8b-instruct

# TTS: set to false when qwen3-tts is installed
USE_STUB_TTS=true

# GPU device for TTS
QWEN_DEVICE=cuda

# Per-stage VRAM telemetry (needs nvidia-ml-py; turns itself off without an NVIDIA driver)
VRAM_TELEMETRY=true
VRAM_GPU_INDEX=0               # NVML index (PCI bus order, ignores CUDA_VISIBLE_DEVICES)
VRAM_SAMPLE_INTERVAL_S=0.25
```

### 4. Frontend — Node dependencies

```bash
cd frontend
npm install
```

Create `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api
```

### 5. Pull the translation model in Ollama

```bash
ollama pull huihui_ai/qwen3-vl-abliterated:8b-instruct
```

## Running the Application

Open four terminal windows, all from the project root.

### Terminal 1 — Redis

```bash
redis-server
```

### Terminal 2 — FastAPI backend

```bash
cd backend
venv\Scripts\activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Terminal 3 — Celery worker

> **Important:** Use `-P solo` (single-process) to avoid ctranslate2/CUDA process crashes when models share GPU memory.

```bash
cd backend
venv\Scripts\activate
celery -A app.worker.celery_app worker -P solo --loglevel=info
```

### Terminal 4 — Next.js frontend

```bash
cd frontend
npm run dev
```

Open http://localhost:3000 in your browser.

## Usage

1. Open http://localhost:3000
2. **Select pipeline mode:**
   - **Full Dubbing** — transcribes, translates, synthesizes Chinese TTS audio, replaces original audio
   - **Subtitles Only** — transcribes, translates, keeps original audio, burns in bilingual subtitles
3. **Select target language** (default: Chinese)
4. **Upload an MP4 video** (or paste a YouTube URL if downloader is configured)
5. Click **Start Translation** and wait — progress is shown step by step
6. Once complete, the result page shows:
   - In-browser video player with switchable subtitle tracks (Original / Translation / Both / Off)
   - **Download with Bilingual Subtitles** — downloads a burned-in MP4 with yellow Chinese subtitles at the bottom and white English subtitles above
   - **GPU Memory per Stage** — the peak VRAM the worker sampled over NVML while each stage ran (also after a
     failure, so an out-of-memory stage shows how close it got). The figure is device-wide: it includes the Whisper
     subprocess, Ollama, the TTS model and anything else on the GPU, which is what decides whether a stage fits.

## Pipeline Steps & Estimated Time

| Step | Description | Time (approx.) |
|------|-------------|----------------|
| 1 | Extract audio | ~5s |
| 2 | Transcribe (Whisper large-v3) | ~0.3x real-time on RTX 5070 Ti |
| 3 | Translate (Qwen3-VL via Ollama) | ~1–3 min depending on length |
| 4 | Synthesize TTS (Qwen3-TTS) | ~1–2x real-time per segment |
| 5 | Mux video + subtitles | ~10s |
| 6 | Burn bilingual subtitles | ~1–3 min (libx264 re-encode) |

## Project Structure

```
AI-video-factory/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, CORS, router mount
│   │   ├── config.py            # Pydantic settings, reads .env
│   │   ├── worker.py            # Celery task: full pipeline orchestration
│   │   ├── state.py             # Redis-backed job state (set/get/update)
│   │   ├── vram.py              # NVML sampler: peak GPU memory per pipeline stage
│   │   ├── models/
│   │   │   └── job.py           # JobResponse Pydantic model
│   │   ├── routers/
│   │   │   └── jobs.py          # POST /jobs, GET /jobs/:id, GET /files/:id/:name
│   │   └── services/
│   │       ├── asr.py           # faster-whisper transcription → SRT
│   │       ├── translate.py     # Ollama translation, SRT parse/write
│   │       ├── tts.py           # Qwen3-TTS voice cloning + audio assembly
│   │       └── mux.py           # FFmpeg audio extract, mux, subtitle burn
│   └── .env                     # (create this — not committed)
├── frontend/
│   ├── app/
│   │   ├── page.tsx             # Upload form (home page)
│   │   └── jobs/[id]/page.tsx   # Job status + video player + download
│   ├── components/
│   │   ├── UploadForm.tsx       # File picker, language selector, pipeline mode
│   │   ├── VideoPlayer.tsx      # HTML5 video + subtitle mode switcher
│   │   ├── JobStatus.tsx        # Step progress indicator
│   │   └── StageVram.tsx        # Peak GPU memory per stage
│   └── lib/
│       └── api.ts               # API client (createJob, getJob, getFileUrl)
└── README.md
```

## Subtitle Styling

The burned-in bilingual subtitle style matches the in-browser player:

| Track | Color | Position | Font size |
|-------|-------|----------|-----------|
| Translated (Chinese) | Yellow `#FDE047` | Bottom center | ~4% of video height |
| Original (English) | White | Above Chinese | ~2.8% of video height |

Both tracks have a semi-transparent black background box (`black@0.65`). Font: Microsoft YaHei (bundled with Windows), which supports CJK and Latin characters.

## Troubleshooting

**Celery worker stops mid-synthesis**
- Use `-P solo` flag. Loading multiple ctranslate2 models (Whisper + TTS) in separate forked processes crashes the CUDA context.

**TTS audio sounds like wrong language**
- Ensure `x_vector_only_mode=True` is set in `tts.py`. This extracts only the speaker's timbre without including English phoneme codes from the reference audio, preventing language bleed.

**FFmpeg subtitle burn fails with path error on Windows**
- The `create_bilingual_download` function uses `subprocess.run(cwd=job_dir)` with bare filenames — this avoids drive letter colon escaping issues in FFmpeg filter strings.

**Audio plays at wrong speed / garbled**
- Ensure Qwen3-TTS output is saved as PCM_16 WAV (`sf.write(..., subtype="PCM_16")`). Saving as float32 and reading back as int16 produces 2x sample count and wrong pitch.

**Job stuck on "translating"**
- Check Ollama is running: `ollama list`. The translation model must be pulled first.
- If Ollama drops the connection mid-job (restart, crash), the job shows "retrying" and is re-run up to twice,
  30 s apart, like a Redis or network error. A CUDA out-of-memory error is never retried; it fails with a hint.

## Tests

The backend tests need no GPU, Redis, Ollama or downloads: translation batching and retries run against a fake
OpenAI-compatible server (`backend/tests/conftest.py`), alongside the SRT helpers, job-failure classification
(`backend/app/errors.py`), per-stage VRAM telemetry against a fake NVML module (`backend/tests/test_vram.py`) and the
quality-eval metrics.

```bash
cd backend && pip install -r evals/requirements.txt httpx openai pydantic-settings && python -m pytest -q tests
```

## License

MIT

## F-Drive Model Paths (Current Setup)

Models are stored on a separate drive to avoid clutter in the project folder. These paths are set via `backend/.env`:

| Model | Location |
|-------|----------|
| Qwen3-TTS weights | `F:\Qwen3-TTS\Qwen3-TTS-12Hz-1.7B-Base\` |
| Qwen3-TTS package | `F:\Qwen3-TTS\qwen_tts\` (editable install) |
| IndexTTS | `F:\index-tts-20\index-tts-20\` |

```env
QWEN3_TTS_ROOT=F:/Qwen3-TTS
INDEXTTS_ROOT=F:/index-tts-20/index-tts-20
```

## Venv Rebuild (After Moving the Project)

Windows venv `.exe` launchers store the Python path as a binary string — they **will break** if you rename or move the project folder. Rebuild from scratch:

```powershell
# 1. Delete the broken venv
Remove-Item -Recurse -Force backend\venv

# 2. Recreate it
python -m venv backend\venv

# 3. Install PyTorch FIRST — must use the PyTorch wheel index (not PyPI)
backend\venv\Scripts\python.exe -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

# 4. Install remaining dependencies
backend\venv\Scripts\python.exe -m pip install fastapi uvicorn celery redis pydantic-settings faster-whisper ffmpeg-python soundfile numpy openai python-multipart

# 5. Re-link Qwen3-TTS from F drive
backend\venv\Scripts\python.exe -m pip install -e F:\Qwen3-TTS
```

> **RTX 5070 Ti note:** requires `cu128` builds (sm_120 / Blackwell). If cu128 stable isn't available for your Python version, use `--pre` nightly builds with the same `--index-url`.

> **flash-attn note:** may fail on Blackwell. Uninstall if you see DLL errors — the pipeline runs without it:
> ```powershell
> backend\venv\Scripts\python.exe -m pip uninstall flash-attn -y
> ```

## Starting the Application (Without activate)

Since `.exe` launchers can break after a move, use `python.exe -m` directly:

```powershell
# FastAPI (from backend\)
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# Celery worker (from backend\)
.\venv\Scripts\python.exe -m celery -A app.worker worker --loglevel=info -P solo -n worker1@%COMPUTERNAME%
```

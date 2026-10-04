================================================================================
 VideoFactory — Quick Start & Setup Guide
================================================================================

DAILY START (all from their respective folders)
--------------------------------------------------------------------------------

1. Redis (keep running in background):
   docker update --restart always redis
   docker start redis

2. Backend — FastAPI  (run from: AI-video-factory\backend\)
   .\venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000

3. Backend — Celery worker  (run from: AI-video-factory\backend\)
   .\venv\Scripts\python.exe -m celery -A app.worker worker --loglevel=info -P solo -n worker1@%COMPUTERNAME%

4. Frontend  (run from: AI-video-factory\frontend\)
   npm run dev

5. Ollama (must be running for translation):
   ollama serve

App runs at: http://localhost:3000
API runs at: http://localhost:8000

PURGE CELERY QUEUE (if jobs get stuck):
   .\venv\Scripts\python.exe -m celery -A app.worker purge
Restart the Network ServiceSometimes simply restarting the service that manages these reservations can clear the temporary block without a full reboot.Run the following commands in an Admin terminal:net stop hns (Host Network Service)net start hns

================================================================================
 F-DRIVE MODEL PATHS  (models stored on F:/, NOT in the project folder)
================================================================================

Qwen3-TTS:      F:\Qwen3-TTS\
  - Model weights:  F:\Qwen3-TTS\Qwen3-TTS-12Hz-1.7B-Base\
  - Package:        F:\Qwen3-TTS\qwen_tts\
  - Start demo:     F:\Qwen3-TTS\Run_Base_Webui.bat

IndexTTS:       F:\index-tts-20\index-tts-20\
  - Checkpoints:    F:\index-tts-20\index-tts-20\checkpoints\

These paths are configured in backend\.env:
  QWEN3_TTS_ROOT=F:/Qwen3-TTS
  INDEXTTS_ROOT=F:/index-tts-20/index-tts-20


================================================================================
 BACKEND .ENV  (create at AI-video-factory\backend\.env)
================================================================================

OPENAI_API_KEY=ollama
REDIS_URL=redis://localhost:6379/0
STORAGE_PATH=E:/ClaudeProject/AI-video-factory/backend/storage

# ASR (Speech-to-Text)
WHISPER_MODEL_SIZE=large-v3          # Options: large-v3, large-v3-turbo (4x faster)
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16         # Options: int8 (smaller), float16 (better)
QWEN_DEVICE=cuda
LOG_LEVEL=INFO

USE_STUB_TTS=false

# Translation (via Ollama)
OLLAMA_BASE_URL=http://localhost:11434/v1
TRANSLATION_MODEL=qwen3:8b           # Text model (Oct 2026 upgrade)
                                      # Alternatives: translategemma:12b, aya-expanse:8b
OLLAMA_KEEP_ALIVE=5m                 # Keep model warm in VRAM (5m, 24h, etc.)

QWEN3_TTS_ROOT=F:/Qwen3-TTS
INDEXTTS_ROOT=F:/index-tts-20/index-tts-20


================================================================================
 FRONTEND .ENV.LOCAL  (create at AI-video-factory\frontend\.env.local)
================================================================================

NEXT_PUBLIC_API_URL=http://localhost:8000/api


================================================================================
 VENV REBUILD (if you move the project folder or venv breaks)
================================================================================

The backend venv WILL break if you rename or move the project folder.
All .exe launchers in venv\Scripts\ have the old path baked in.
Fix: delete and recreate the venv from scratch.

Step 1 — Delete the broken venv:
   Remove-Item -Recurse -Force E:\ClaudeProject\AI-video-factory\backend\venv

Step 2 — Recreate it:
   python -m venv E:\ClaudeProject\AI-video-factory\backend\venv

Step 3 — Install PyTorch FIRST (must use PyTorch wheel index, not PyPI):
   .\venv\Scripts\python.exe -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

Step 4 — Install remaining backend dependencies:
   .\venv\Scripts\python.exe -m pip install fastapi uvicorn celery redis pydantic-settings faster-whisper ffmpeg-python soundfile numpy openai python-multipart

Step 5 — Re-link Qwen3-TTS package (editable install from F drive):
   .\venv\Scripts\python.exe -m pip install -e F:\Qwen3-TTS

NOTE: If PyTorch cu128 is not available for your Python version, use nightly:
   .\venv\Scripts\python.exe -m pip install --pre torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/cu128

NOTE: flash-attn is optional and may fail on Blackwell (RTX 5070 Ti / sm_120).
   .\venv\Scripts\python.exe -m pip uninstall flash-attn -y


================================================================================
 QWEN3-TTS DEMO (standalone Gradio UI)
================================================================================

Run: F:\Qwen3-TTS\Run_Base_Webui.bat
Opens at: http://localhost:8000

These bat files call python.exe -m qwen_tts.cli.demo directly with --no-flash-attn.
Do NOT use the .exe launchers — they break when the folder is moved.


================================================================================
 INSTALL SoX (required by some audio libs)
================================================================================

winget install sox.sox
(Restart terminal after install so PATH updates)


================================================================================
 MODEL SELECTION (Oct 4, 2026 Upgrade)
================================================================================

ASR (Audio Transcription):
  large-v3 (DEFAULT)     — 7.4% WER, balanced speed/accuracy
  large-v3-turbo         — 7.75% WER, 4× faster (CTranslate2 ONNX optimized)

  Switch: Set WHISPER_MODEL_SIZE=large-v3-turbo in .env

Translation (Text via Ollama):
  qwen3:8b (DEFAULT)     — 6 GB VRAM, ~112 tok/s, general-purpose
  translategemma:12b     — 8.1 GB VRAM, 25.9% error reduction, MT-specialized
  aya-expanse:8b         — 8 GB VRAM, 93-language support, multilingual

  Switch: Set TRANSLATION_MODEL=<model_name> in .env, then:
    ollama pull <model_name>

  Notes:
    - Oct 2026 changed from vision model (qwen3-vl) to text models (8–12× faster)
    - Keep OLLAMA_KEEP_ALIVE set to prevent model reload between jobs

Compute Precision:
  float16 (DEFAULT)      — 2× smaller than FP32, good accuracy
  int8                   — 4× smaller than FP32, minor WER impact (~1–3%)

  Use INT8 only if VRAM < 4 GB.

Performance Tuning Guide:
  Faster:   large-v3-turbo + qwen3:8b + OLLAMA_KEEP_ALIVE=24h
  Quality:  large-v3 + translategemma:12b + longer keep-alive
  Balanced: large-v3 + qwen3:8b (current defaults)


================================================================================
 TROUBLESHOOTING
================================================================================

"Fatal error in launcher: Unable to create process"
  -> Venv was moved. Rebuild it. See VENV REBUILD section above.
  -> Use .\venv\Scripts\python.exe -m <module> instead of .exe launchers.

"CUDA error: no kernel image is available"
  -> PyTorch too old for RTX 5070 Ti (needs sm_120 / cu128).
  -> Redo Step 3 of VENV REBUILD with --index-url https://download.pytorch.org/whl/cu128

"Cannot reach Ollama"
  -> Run: ollama serve
  -> Pull translation model: ollama pull qwen3:8b
  -> Or custom model: ollama pull translategemma:12b

"Translation very slow (first request ~30s, then fast)"
  -> Model cold-start. Increase OLLAMA_KEEP_ALIVE in .env to keep warm.
  -> Default 5m = unloads from VRAM after 5 min inactivity.
  -> Set to "24h" for 16 GB GPU to pin model all day.

"Celery worker crashes mid-job"
  -> Always use -P solo. Forked workers crash the CUDA context.

"Job stuck on transcribing"
  -> Check GPU memory: nvidia-smi
  -> Reduce ASR_CHUNK_MINUTES (e.g., 5 min chunks instead of 10) to lower peak VRAM
  -> Or switch to smaller model (Qwen3-ASR 1.7B for Mandarin-only)

================================================================================

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

WHISPER_MODEL_SIZE=large-v3
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16
QWEN_DEVICE=cuda
LOG_LEVEL=INFO

USE_STUB_TTS=false

OLLAMA_BASE_URL=http://localhost:11434/v1
TRANSLATION_MODEL=huihui_ai/qwen3-vl-abliterated:8b-instruct

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
  -> Pull model: ollama pull huihui_ai/qwen3-vl-abliterated:8b-instruct

"Celery worker crashes mid-job"
  -> Always use -P solo. Forked workers crash the CUDA context.

"Job stuck on translating"
  -> Check Ollama is running: ollama list

================================================================================

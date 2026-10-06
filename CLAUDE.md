# CLAUDE.md: AI-video-factory

Local video translation and dubbing on one 16 GB GPU (owner's RTX 5070 Ti, Windows): faster-whisper ASR → LLM
translation (Ollama) → voice-cloned TTS (Qwen3-TTS) → FFmpeg mux, queued through Celery + Redis, Next.js frontend.
Default branch: `AI-feature-implementation`. The frontend has its own CLAUDE.md / AGENTS.md.

## Commands

```bash
cd backend && pip install -r evals/requirements.txt httpx openai pydantic-settings && python -m pytest -q tests
cd frontend && npm ci && npx eslint . && npx tsc --noEmit && npx next build --webpack
```

## Rules

- **Never fabricate results.** `backend/evals/results/` holds only real runs from
  `backend/scripts/publish_results.ps1` on the GPU machine. Cloud sessions have no GPU and usually can't reach
  Hugging Face; write tests that need neither.
- Keep CI green (backend tests, frontend lint, typecheck, build) and add tests for new behavior.
- One roadmap item per change; move it to "Shipped" in ROADMAP.md with the date, and add a dated entry to PROGRESS.md.
- Commit to `AI-feature-implementation` with a descriptive message; never force-push.

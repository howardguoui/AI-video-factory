import asyncio
import json
import logging
import urllib.request

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

SYSTEM_PROMPT = """You are a concise AI assistant built into AI Video Factory — a local video translation and dubbing pipeline.

You help users with:
- Video translation & dubbing (YouTube, Bilibili, file uploads)
- Pipeline modes: Full Dubbing, Subtitles Only, MP3 Audio Only, Export Subtitles, Webpage Extraction
- TTS engines: Qwen3-TTS, IndexTTS, CosyVoice2
- Transcription (Whisper) and translation (Ollama LLM) settings
- Troubleshooting errors or slow jobs

Keep responses short and direct. Use bullet points when listing steps or options."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _probe_ollama() -> tuple[bool, str | None]:
    """
    Synchronous probe of Ollama.  Call via asyncio.to_thread.
    Returns (reachable, model_name_or_None).

    Strategy:
      1. /api/ps  — currently warm models (prefer these, instant response)
      2. /api/tags — all installed models (cold but usable)
      3. Give up → (False, None)
    """
    base = settings.ollama_base_url.rstrip("/").replace("/v1", "")

    def _get(path: str) -> dict | None:
        try:
            with urllib.request.urlopen(f"{base}{path}", timeout=5) as resp:
                return json.loads(resp.read())
        except Exception:
            return None

    # 1. Warm models
    data = _get("/api/ps")
    if data is not None:
        names = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        if names:
            return True, names[0]

    # 2. Installed models
    data = _get("/api/tags")
    if data is not None:
        names = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        if names:
            return True, names[0]
        # Ollama is reachable but no models are installed
        return True, None

    return False, None


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str   # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    context: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/chat/status")
async def chat_status():
    """
    Returns:
      ok      – True if Ollama is reachable
      model   – model name that will be used (or null if none installed)
      error   – human-readable problem description when ok=False
    """
    try:
        reachable, model = await asyncio.to_thread(_probe_ollama)
    except Exception as e:
        return {"ok": False, "model": None, "error": str(e)}

    if not reachable:
        return {
            "ok": False,
            "model": None,
            "error": "Cannot reach Ollama. Run `ollama serve` in a terminal.",
        }
    if model is None:
        return {
            "ok": False,
            "model": None,
            "error": "Ollama is running but no models are installed. Run `ollama pull <model>`.",
        }
    return {"ok": True, "model": model, "error": None}


@router.post("/chat")
async def chat(req: ChatRequest):
    """Stream an Ollama chat completion as SSE."""
    try:
        reachable, model = await asyncio.to_thread(_probe_ollama)
    except Exception:
        reachable, model = False, None

    if not reachable or model is None:
        # Return a single error event instead of 500 so the UI can surface it
        async def _error():
            msg = (
                "Ollama is not reachable. Start it with `ollama serve`."
                if not reachable
                else "No models installed in Ollama. Run `ollama pull <model>`."
            )
            yield f"data: {json.dumps(msg)}\n\ndata: [DONE]\n\n"
        return StreamingResponse(_error(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    logger.info(f"Chat request: model={model}, messages={len(req.messages)}")

    system_content = SYSTEM_PROMPT
    if req.context:
        system_content += f"\n\nContext from the current page:\n{req.context}"

    messages: list[dict] = [{"role": "system", "content": system_content}]
    messages.extend({"role": m.role, "content": m.content} for m in req.messages)

    async def generate():
        try:
            client = AsyncOpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.ollama_base_url,
            )
            stream = await client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True,
                temperature=0.7,
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta is None or delta.content is None:
                    continue
                yield f"data: {json.dumps(delta.content)}\n\n"
        except Exception as e:
            logger.error(f"Chat stream error: {e}")
            yield f"data: {json.dumps(f'⚠ {e}')}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

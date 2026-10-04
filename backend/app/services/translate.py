import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from openai import OpenAI
from app.config import settings

logger = logging.getLogger(__name__)

LANGUAGE_NAMES: dict[str, str] = {
    "zh": "Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "de": "German",
    "fr": "French",
    "ru": "Russian",
    "pt": "Portuguese",
    "es": "Spanish",
    "it": "Italian",
}

BATCH_SIZE = 20


@dataclass
class Segment:
    index: int
    start: str  # "HH:MM:SS,mmm"
    end: str    # "HH:MM:SS,mmm"
    text: str


def parse_srt(content: str) -> list[Segment]:
    """Parse SRT content into a list of Segment objects."""
    segments = []
    # Split on blank lines; strip trailing whitespace
    blocks = re.split(r"\n\s*\n", content.strip())
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue
        try:
            index = int(lines[0].strip())
        except ValueError:
            continue
        time_parts = lines[1].split(" --> ")
        if len(time_parts) != 2:
            continue
        start, end = time_parts[0].strip(), time_parts[1].strip()
        text = " ".join(line.strip() for line in lines[2:])
        segments.append(Segment(index=index, start=start, end=end, text=text))
    return segments


def rebuild_srt(segments: list[Segment]) -> str:
    """Rebuild an SRT string from a list of Segment objects."""
    blocks = []
    for seg in segments:
        blocks.append(f"{seg.index}\n{seg.start} --> {seg.end}\n{seg.text}")
    return "\n\n".join(blocks) + "\n"


def _call_llm(client: OpenAI, system_prompt: str, user_content: str, model: str) -> str:
    """Single LLM call, returns raw string content."""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


def _parse_json_list(raw: str) -> list | None:
    """Try to parse a JSON list from the model response. Returns None on failure."""
    try:
        result = json.loads(raw)
        return result if isinstance(result, list) else None
    except json.JSONDecodeError:
        # Strip markdown fences if present
        stripped = raw.strip("`").strip()
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
        try:
            result = json.loads(stripped)
            return result if isinstance(result, list) else None
        except json.JSONDecodeError:
            return None


def _translate_batch(client: OpenAI, texts: list[str], target_lang: str, model: str) -> list[str]:
    """
    Translate a batch of subtitle texts. If the model returns the wrong item
    count (common with small local models that merge adjacent lines), the batch
    is split in half and each half is retried recursively. Single-item batches
    that still fail fall back to the original text so the pipeline never halts.
    """
    lang_name = LANGUAGE_NAMES.get(target_lang, target_lang)
    system_prompt = (
        f"You are a professional subtitle translator. Translate the following texts to {lang_name}. "
        "Preserve tone, emotion, and natural speech patterns. "
        "Each input line is a separate subtitle segment — do NOT merge or split lines. "
        f"Return ONLY a JSON array of exactly {len(texts)} translated strings in the same order. "
        "No explanations, no extra text."
    )
    user_content = json.dumps(texts, ensure_ascii=False)

    raw = _call_llm(client, system_prompt, user_content, model)
    result = _parse_json_list(raw)

    # If malformed JSON, retry once with stricter prompt
    if result is None:
        logger.warning(f"Malformed JSON for batch of {len(texts)}, retrying")
        strict_prompt = system_prompt + " You MUST return valid JSON only — nothing else."
        raw = _call_llm(client, strict_prompt, user_content, model)
        result = _parse_json_list(raw)

    # Correct count — happy path
    if result is not None and len(result) == len(texts):
        return [str(t) for t in result]

    # Wrong count: split and retry halves recursively
    if len(texts) > 1:
        got = len(result) if result is not None else "non-list"
        logger.warning(
            f"Count mismatch: got {got}, expected {len(texts)} — "
            f"splitting batch in half and retrying"
        )
        mid = len(texts) // 2
        left = _translate_batch(client, texts[:mid], target_lang, model)
        right = _translate_batch(client, texts[mid:], target_lang, model)
        return left + right

    # Single item still failing — use original text as fallback
    logger.warning(f"Single-item translation failed, keeping original: {texts[0][:60]!r}")
    return list(texts)


def _detect_ollama_model() -> str:
    """
    Query Ollama's /api/ps endpoint to find the currently loaded model.
    Falls back to the configured translation_model if Ollama is unreachable.
    Returns a display string like 'qwen3:8b (running)' or 'qwen3:8b (config, not loaded)'.
    """
    import urllib.request
    import urllib.error

    base = settings.ollama_base_url.rstrip("/").replace("/v1", "")
    configured = settings.translation_model
    try:
        with urllib.request.urlopen(f"{base}/api/ps", timeout=3) as resp:
            data = json.loads(resp.read())
        models = [m.get("name", "") for m in data.get("models", [])]
        if models:
            running = ", ".join(models)
            loaded = configured in running
            status = "running" if loaded else f"running: {running}"
            return f"{configured} ({status})"
        return f"{configured} (configured, none loaded in Ollama)"
    except Exception:
        return f"{configured} (Ollama unreachable — using configured value)"


def translate_text(
    source_txt_path: str,
    target_lang: str,
    llm_model: str | None = None,
    progress_callback=None,
) -> str:
    """
    Translate a plain-text file (e.g. extracted from a webpage) to target_lang.
    Splits on double-newlines (paragraphs), translates in batches, and writes
    the result to translated.txt alongside the source file.
    Returns the path to translated.txt.
    """
    job_dir = Path(source_txt_path).parent
    translated_path = str(job_dir / "translated.txt")

    with open(source_txt_path, encoding="utf-8") as f:
        text = f.read()

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        raise ValueError(f"No text content found in {source_txt_path}")

    model = llm_model or settings.translation_model
    total_batches = max(1, (len(paragraphs) + BATCH_SIZE - 1) // BATCH_SIZE)
    logger.info(
        f"Translating {len(paragraphs)} paragraphs to "
        f"{LANGUAGE_NAMES.get(target_lang, target_lang)} "
        f"in {total_batches} batches | model: {model}"
    )

    client = OpenAI(api_key=settings.openai_api_key, base_url=settings.ollama_base_url)
    translated_parts: list[str] = []

    for i in range(0, len(paragraphs), BATCH_SIZE):
        batch = paragraphs[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        if progress_callback:
            progress_callback(i / len(paragraphs), f"Batch {batch_num}/{total_batches}")
        try:
            translated_parts.extend(_translate_batch(client, batch, target_lang, model))
        except Exception as e:
            err = str(e)
            if "Connection error" in err or "10061" in err or "ConnectError" in err:
                raise RuntimeError(
                    f"Cannot reach Ollama at {settings.ollama_base_url}. "
                    "Make sure Ollama is running and the model is pulled."
                ) from e
            raise

    if progress_callback:
        progress_callback(1.0, "Translation complete")

    with open(translated_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(translated_parts))

    logger.info(f"Translated text written: {translated_path}")
    return translated_path


def translate_srt(
    srt_path: str,
    target_lang: str,
    llm_model: str | None = None,
    progress_callback=None,
) -> str:
    """Translate an SRT file to target_lang using Ollama. Returns path to translated SRT."""
    job_dir = Path(srt_path).parent
    translated_srt_path = str(job_dir / "translated.srt")

    with open(srt_path, encoding="utf-8") as f:
        content = f.read()

    segments = parse_srt(content)
    if not segments:
        raise ValueError(f"No segments parsed from {srt_path}")

    model = llm_model or settings.translation_model
    total_batches = max(1, (len(segments) + BATCH_SIZE - 1) // BATCH_SIZE)
    logger.info(
        f"Translating {len(segments)} segments to {LANGUAGE_NAMES.get(target_lang, target_lang)} "
        f"in {total_batches} batches | model: {model}"
    )

    client = OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.ollama_base_url,
    )
    translated_segments: list[Segment] = []

    for i in range(0, len(segments), BATCH_SIZE):
        batch = segments[i : i + BATCH_SIZE]
        texts = [seg.text for seg in batch]
        batch_num = i // BATCH_SIZE + 1
        logger.info(f"Translating batch {batch_num}/{total_batches}: segments {i + 1}–{i + len(batch)}")

        if progress_callback:
            progress_callback(i / len(segments), f"Batch {batch_num}/{total_batches}")

        try:
            translated_texts = _translate_batch(client, texts, target_lang, model)
        except Exception as e:
            err = str(e)
            if "Connection error" in err or "10061" in err or "ConnectError" in err:
                raise RuntimeError(
                    f"Cannot reach Ollama at {settings.ollama_base_url}. "
                    "Make sure Ollama is running: open a terminal and run `ollama serve`, "
                    f"then ensure model '{model}' is pulled (`ollama pull {model}`)."
                ) from e
            raise

        for seg, translated_text in zip(batch, translated_texts):
            translated_segments.append(
                Segment(index=seg.index, start=seg.start, end=seg.end, text=translated_text)
            )

    if progress_callback:
        progress_callback(1.0, "Translation complete")

    srt_content = rebuild_srt(translated_segments)
    with open(translated_srt_path, "w", encoding="utf-8") as f:
        f.write(srt_content)

    logger.info(f"Translated SRT written: {translated_srt_path}")
    return translated_srt_path

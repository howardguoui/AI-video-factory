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


def _translate_batch(client: OpenAI, texts: list[str], target_lang: str) -> list[str]:
    """Translate a batch of texts via GPT-4o. Returns a list of translated strings."""
    lang_name = LANGUAGE_NAMES.get(target_lang, target_lang)
    system_prompt = (
        f"You are a professional subtitle translator. Translate the following texts to {lang_name}. "
        "Preserve tone, emotion, and natural speech patterns. "
        "Return ONLY a JSON array of translated strings in the same order as input. "
        "No explanations, no extra text."
    )
    user_content = json.dumps(texts, ensure_ascii=False)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=0.3,
    )
    raw = response.choices[0].message.content.strip()

    # Parse JSON — retry once if malformed
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("GPT-4o returned malformed JSON, retrying with stricter prompt")
        retry_response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt + " You MUST return valid JSON only."},
                {"role": "user", "content": user_content},
                {"role": "assistant", "content": raw},
                {"role": "user", "content": "Please return ONLY the JSON array, nothing else."},
            ],
            temperature=0,
        )
        result = json.loads(retry_response.choices[0].message.content.strip())

    if not isinstance(result, list) or len(result) != len(texts):
        raise ValueError(
            f"Translation returned {len(result) if isinstance(result, list) else 'non-list'} "
            f"items, expected {len(texts)}"
        )
    return [str(t) for t in result]


def translate_srt(srt_path: str, target_lang: str) -> str:
    """Translate an SRT file to target_lang using GPT-4o. Returns path to translated SRT."""
    job_dir = Path(srt_path).parent
    translated_srt_path = str(job_dir / "translated.srt")

    with open(srt_path, encoding="utf-8") as f:
        content = f.read()

    segments = parse_srt(content)
    if not segments:
        raise ValueError(f"No segments parsed from {srt_path}")

    logger.info(
        f"Translating {len(segments)} segments to {LANGUAGE_NAMES.get(target_lang, target_lang)} "
        f"in batches of {BATCH_SIZE}"
    )

    client = OpenAI(api_key=settings.openai_api_key)
    translated_segments: list[Segment] = []

    for i in range(0, len(segments), BATCH_SIZE):
        batch = segments[i : i + BATCH_SIZE]
        texts = [seg.text for seg in batch]
        logger.info(f"Translating batch {i // BATCH_SIZE + 1}: segments {i + 1}–{i + len(batch)}")
        translated_texts = _translate_batch(client, texts, target_lang)

        for seg, translated_text in zip(batch, translated_texts):
            translated_segments.append(
                Segment(index=seg.index, start=seg.start, end=seg.end, text=translated_text)
            )

    srt_content = rebuild_srt(translated_segments)
    with open(translated_srt_path, "w", encoding="utf-8") as f:
        f.write(srt_content)

    logger.info(f"Translated SRT written: {translated_srt_path}")
    return translated_srt_path

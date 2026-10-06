"""Measure ASR accuracy, translation quality and speed on Google FLEURS.

FLEURS has the same ~2,000 sentences read aloud in 100+ languages, with human
transcripts aligned by sentence id. That gives, for every clip:
  - a reference transcript in the source language   -> ASR word/character error rate
  - a reference translation in the target language  -> translation chrF++ and BLEU

Three things are measured:
  1. ASR: each Whisper model on the clips (WER, or CER for zh/ja/ko) and real-time factor.
  2. Translation: each LLM on the reference transcripts (isolates MT from ASR errors).
  3. Cascade: best ASR output -> first LLM, i.e. what the real pipeline produces.

Usage (from backend/, with Ollama running and a CUDA GPU):
    pip install -r evals/requirements.txt
    python -m evals.quality_eval --src zh --tgt en --limit 50 \
        --asr-models large-v3 large-v3-turbo --mt-models qwen3:8b

Results: evals/results/latest.md and a timestamped JSON.
Data: https://huggingface.co/datasets/google/fleurs (CC-BY 4.0).
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import tarfile
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx

HERE = Path(__file__).parent
CACHE = HERE / ".cache"
RESULTS = HERE / "results"
FLEURS = "https://huggingface.co/datasets/google/fleurs/resolve/main/data"

# App language code -> FLEURS config name
FLEURS_LANG = {
    "zh": "cmn_hans_cn", "en": "en_us", "ja": "ja_jp", "ko": "ko_kr", "de": "de_de",
    "fr": "fr_fr", "ru": "ru_ru", "pt": "pt_br", "es": "es_419", "it": "it_it",
}
CHAR_LANGS = {"zh", "ja", "ko"}  # no word spaces: score characters, not words
SAMPLE_RATE = 16_000


@dataclass
class Clip:
    id: int
    file_name: str
    source: str  # reference transcript (source language)
    target: str  # reference translation (target language)
    seconds: float


@dataclass
class Report:
    src: str
    tgt: str
    split: str
    n_clips: int
    run_at: str
    asr: dict = field(default_factory=dict)
    mt: dict = field(default_factory=dict)
    cascade: dict = field(default_factory=dict)


# ---------------------------------------------------------------- data


def parse_tsv(text: str) -> list[dict]:
    """FLEURS TSV, no header: id, file_name, raw_transcription, transcription, phonemes, num_samples, gender."""
    rows = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 6 or not parts[0].isdigit():
            continue
        rows.append({"id": int(parts[0]), "file_name": parts[1], "raw": parts[2], "num_samples": int(parts[5])})
    return rows


def align(src_rows: list[dict], tgt_rows: list[dict], limit: int | None) -> list[Clip]:
    """One clip per sentence id (first recording), paired with the target-language text of the same id."""
    tgt_text: dict[int, str] = {}
    for r in tgt_rows:
        tgt_text.setdefault(r["id"], r["raw"])
    clips, seen = [], set()
    for r in src_rows:
        if r["id"] in seen or r["id"] not in tgt_text:
            continue
        seen.add(r["id"])
        clips.append(Clip(r["id"], r["file_name"], r["raw"], tgt_text[r["id"]], r["num_samples"] / SAMPLE_RATE))
        if limit and len(clips) >= limit:
            break
    return clips


def _download(url: str, dest: Path) -> Path:
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with httpx.stream("GET", url, follow_redirects=True, timeout=600) as r:
        r.raise_for_status()
        with tmp.open("wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
    tmp.rename(dest)
    return dest


def load_clips(src: str, tgt: str, split: str, limit: int | None) -> list[Clip]:
    def rows(lang: str) -> list[dict]:
        code = FLEURS_LANG[lang]
        path = _download(f"{FLEURS}/{code}/{split}.tsv", CACHE / code / f"{split}.tsv")
        return parse_tsv(path.read_text(encoding="utf-8"))

    return align(rows(src), rows(tgt), limit)


def extract_audio(src: str, split: str, clips: list[Clip]) -> Path:
    """Download the split's audio archive once and extract only the clips we need."""
    code = FLEURS_LANG[src]
    archive = _download(f"{FLEURS}/{code}/audio/{split}.tar.gz", CACHE / code / f"{split}.tar.gz")
    out = CACHE / code / split
    wanted = {c.file_name for c in clips if not (out / c.file_name).exists()}
    if wanted:
        out.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, "r:gz") as tar:
            for m in tar:
                name = Path(m.name).name
                if m.isfile() and name in wanted:
                    (out / name).write_bytes(tar.extractfile(m).read())
    return out


# ---------------------------------------------------------------- metrics


def normalize(text: str, lang: str) -> str:
    """Lowercase, drop punctuation, collapse spaces; Chinese is folded to Simplified when OpenCC is installed."""
    if lang == "zh":
        try:
            from opencc import OpenCC

            text = OpenCC("t2s").convert(text)
        except ImportError:
            pass
    text = unicodedata.normalize("NFKC", text).lower()
    text = "".join(" " if unicodedata.category(ch).startswith("P") else ch for ch in text)
    text = re.sub(r"\s+", " ", text).strip()
    if lang in CHAR_LANGS:
        text = text.replace(" ", "")
    return text


def error_rate(refs: list[str], hyps: list[str], lang: str) -> float:
    """WER for spaced languages, CER for zh/ja/ko (corpus level)."""
    import jiwer

    r = [normalize(x, lang) for x in refs]
    h = [normalize(x, lang) for x in hyps]
    pairs = [(a, b) for a, b in zip(r, h, strict=True) if a]
    r, h = [p[0] for p in pairs], [p[1] for p in pairs]
    return float(jiwer.cer(r, h) if lang in CHAR_LANGS else jiwer.wer(r, h))


def translation_scores(hyps: list[str], refs: list[str], tgt: str) -> dict:
    import sacrebleu

    tokenize = {"zh": "zh", "ja": "char", "ko": "char"}.get(tgt, "13a")
    chrf = sacrebleu.corpus_chrf(hyps, [refs], word_order=2)  # chrF++
    bleu = sacrebleu.corpus_bleu(hyps, [refs], tokenize=tokenize)
    return {"chrf_pp": round(chrf.score, 2), "bleu": round(bleu.score, 2)}


# ---------------------------------------------------------------- runs


def run_asr(model_size: str, clips: list[Clip], audio_dir: Path, src: str) -> tuple[dict, list[str]]:
    from faster_whisper import WhisperModel

    from app.config import settings

    t0 = time.perf_counter()
    model = WhisperModel(model_size, device=settings.whisper_device, compute_type=settings.whisper_compute_type)
    load_s = time.perf_counter() - t0
    hyps, proc_s = [], 0.0
    for c in clips:
        t = time.perf_counter()
        segments, _ = model.transcribe(
            str(audio_dir / c.file_name), language=src, beam_size=settings.whisper_beam_size, vad_filter=True
        )
        hyps.append(" ".join(s.text.strip() for s in segments))
        proc_s += time.perf_counter() - t
    audio_s = sum(c.seconds for c in clips)
    metric = "cer" if src in CHAR_LANGS else "wer"
    return {
        metric: round(error_rate([c.source for c in clips], hyps, src), 4),
        "rtf": round(proc_s / audio_s, 4),  # < 1 means faster than real time
        "x_realtime": round(audio_s / proc_s, 1),
        "audio_minutes": round(audio_s / 60, 1),
        "model_load_s": round(load_s, 1),
        "compute_type": settings.whisper_compute_type,
        "beam_size": settings.whisper_beam_size,
    }, hyps


def translate_all(texts: list[str], tgt: str, model: str, batch: int = 20) -> tuple[list[str], float]:
    from openai import OpenAI

    from app.config import settings
    from app.services.translate import _translate_batch

    client = OpenAI(api_key=settings.openai_api_key, base_url=settings.ollama_base_url)
    _translate_batch(client, texts[:1], tgt, model)  # warm-up: load the model into VRAM
    out, t0 = [], time.perf_counter()
    for i in range(0, len(texts), batch):
        out.extend(_translate_batch(client, texts[i : i + batch], tgt, model))
    return out, time.perf_counter() - t0


def run_mt(model: str, sources: list[str], refs: list[str], tgt: str) -> dict:
    hyps, secs = translate_all(sources, tgt, model)
    return {
        **translation_scores(hyps, refs, tgt),
        "segments": len(sources),
        "seconds": round(secs, 1),
        "segments_per_s": round(len(sources) / secs, 2) if secs else None,
        "untranslated": sum(h.strip() == s.strip() for h, s in zip(hyps, sources, strict=True)),
    }


def write_report(rep: Report) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M")
    data = rep.__dict__
    (RESULTS / f"{stamp}_{rep.src}-{rep.tgt}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))
    (RESULTS / "latest.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))

    err = "CER" if rep.src in CHAR_LANGS else "WER"
    lines = [
        f"# Quality eval: {rep.src} → {rep.tgt}, FLEURS {rep.split}, {rep.n_clips} clips",
        "",
        f"Run {rep.run_at}. Lower {err} is better; chrF++ and BLEU are 0–100, higher is better.",
    ]
    if rep.asr:
        lines += ["", "## Speech recognition", "", f"| Model | {err} | Speed | Audio |", "| --- | --- | --- | --- |"]
        for m, r in rep.asr.items():
            lines.append(f"| {m} | {r[err.lower()]:.1%} | {r['x_realtime']}× real time | {r['audio_minutes']} min |")
    if rep.mt:
        lines += ["", "## Translation (reference transcripts in)", "",
                  "| Model | chrF++ | BLEU | Segments/s | Untranslated |", "| --- | --- | --- | --- | --- |"]
        for m, r in rep.mt.items():
            lines.append(f"| {m} | {r['chrf_pp']} | {r['bleu']} | {r['segments_per_s']} | {r['untranslated']} |")
    if rep.cascade:
        c = rep.cascade
        lines += ["", "## Full pipeline (speech → translation)", "",
                  f"{c['asr_model']} → {c['mt_model']}: chrF++ {c['chrf_pp']}, BLEU {c['bleu']} "
                  f"(vs {c['reference_chrf_pp']} from perfect transcripts)"]
    path = RESULTS / "latest.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> Report:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default="zh", choices=sorted(FLEURS_LANG))
    ap.add_argument("--tgt", default="en", choices=sorted(FLEURS_LANG))
    ap.add_argument("--split", default="test", choices=["dev", "test"])
    ap.add_argument("--limit", type=int, default=50, help="Number of sentences (each ~10 s of audio)")
    ap.add_argument("--asr-models", nargs="*", default=["large-v3", "large-v3-turbo"])
    ap.add_argument("--mt-models", nargs="*", default=["qwen3:8b"])
    a = ap.parse_args(argv)

    clips = load_clips(a.src, a.tgt, a.split, a.limit)
    rep = Report(a.src, a.tgt, a.split, len(clips), datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"))
    print(f"{len(clips)} clips, {sum(c.seconds for c in clips) / 60:.1f} min of audio")

    asr_hyps: dict[str, list[str]] = {}
    if a.asr_models:
        audio_dir = extract_audio(a.src, a.split, clips)
        for m in a.asr_models:
            rep.asr[m], asr_hyps[m] = run_asr(m, clips, audio_dir, a.src)
            print("ASR", m, rep.asr[m])

    refs = [c.target for c in clips]
    for m in a.mt_models:
        rep.mt[m] = run_mt(m, [c.source for c in clips], refs, a.tgt)
        print("MT", m, rep.mt[m])

    if asr_hyps and a.mt_models:
        err = "cer" if a.src in CHAR_LANGS else "wer"
        best = min(rep.asr, key=lambda m: rep.asr[m][err])
        hyps, _ = translate_all(asr_hyps[best], a.tgt, a.mt_models[0])
        rep.cascade = {"asr_model": best, "mt_model": a.mt_models[0], **translation_scores(hyps, refs, a.tgt),
                       "reference_chrf_pp": rep.mt[a.mt_models[0]]["chrf_pp"]}

    print(write_report(rep).read_text(encoding="utf-8"))
    return rep


if __name__ == "__main__":
    main()

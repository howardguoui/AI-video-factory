"""Tests for the quality eval's data handling and metrics (no GPU, Ollama or downloads needed)."""

import json

import pytest

from evals import quality_eval as qe

TSV_ZH = (
    "1001\t1.wav\t今天天气很好。\t今天天气很好\tx\t160000\tFEMALE\n"
    "1001\t2.wav\t今天天气很好。\t今天天气很好\tx\t150000\tMALE\n"
    "1002\t3.wav\t我们去公园吧！\t我们去公园吧\tx\t96000\tMALE\n"
    "1003\t4.wav\t只有中文。\t只有中文\tx\t80000\tMALE\n"
    "malformed line\n"
)
TSV_EN = (
    "1001\ta.wav\tThe weather is nice today.\tthe weather is nice today\tx\t1\tMALE\n"
    "1002\tb.wav\tLet's go to the park!\tlet's go to the park\tx\t1\tMALE\n"
)


def test_parse_and_align_one_clip_per_sentence():
    clips = qe.align(qe.parse_tsv(TSV_ZH), qe.parse_tsv(TSV_EN), limit=None)
    assert [c.id for c in clips] == [1001, 1002]  # duplicate recording and unmatched id dropped
    assert clips[0].file_name == "1.wav" and clips[0].seconds == 10.0
    assert clips[1].target == "Let's go to the park!"
    assert len(qe.align(qe.parse_tsv(TSV_ZH), qe.parse_tsv(TSV_EN), limit=1)) == 1


def test_normalize_strips_punctuation_and_spaces_for_chinese():
    assert qe.normalize("今天， 天气 很好！", "zh") == "今天天气很好"
    assert qe.normalize("Hello,  World!", "en") == "hello world"


def test_error_rates():
    assert qe.error_rate(["今天天气很好"], ["今天天气很好。"], "zh") == 0.0
    assert qe.error_rate(["今天天气很好"], ["今天天汽很好"], "zh") == pytest.approx(1 / 6)
    assert qe.error_rate(["the cat sat"], ["the cat sat down"], "en") == pytest.approx(1 / 3)


def test_translation_scores_reward_matches():
    refs = ["The weather is nice today.", "Let's go to the park!"]
    perfect = qe.translation_scores(refs, refs, "en")
    worse = qe.translation_scores(["Weather good.", "Park now."], refs, "en")
    assert perfect["chrf_pp"] == pytest.approx(100.0) and perfect["bleu"] == pytest.approx(100.0)
    assert worse["chrf_pp"] < perfect["chrf_pp"] and worse["bleu"] < perfect["bleu"]


def test_run_mt_uses_the_app_translator(monkeypatch):
    calls = []

    def fake_batch(client, texts, tgt, model):
        calls.append((len(texts), tgt, model))
        return ["The weather is nice today." if "天气" in t else t for t in texts]

    import app.services.translate as tr

    monkeypatch.setattr(tr, "_translate_batch", fake_batch)
    r = qe.run_mt("qwen3:8b", ["今天天气很好。", "我们去公园吧！"], ["The weather is nice today.", "Let's go!"], "en")
    assert calls[0] == (1, "en", "qwen3:8b")  # warm-up
    assert r["segments"] == 2 and r["untranslated"] == 1
    assert 0 < r["chrf_pp"] < 100


def test_report_is_written(tmp_path, monkeypatch):
    monkeypatch.setattr(qe, "RESULTS", tmp_path)
    rep = qe.Report("zh", "en", "test", 2, "2026-10-06 18:00 UTC")
    rep.asr = {"large-v3-turbo": {"cer": 0.081, "x_realtime": 22.4, "audio_minutes": 8.3}}
    rep.mt = {"qwen3:8b": {"chrf_pp": 51.2, "bleu": 22.1, "segments_per_s": 3.4, "untranslated": 0}}
    rep.cascade = {"asr_model": "large-v3-turbo", "mt_model": "qwen3:8b", "chrf_pp": 48.0, "bleu": 20.0,
                   "reference_chrf_pp": 51.2}
    md = qe.write_report(rep).read_text(encoding="utf-8")
    assert "| large-v3-turbo | 8.1% | 22.4× real time | 8.3 min |" in md
    assert "| qwen3:8b | 51.2 | 22.1 | 3.4 | 0 |" in md
    assert json.loads((tmp_path / "latest.json").read_text())["n_clips"] == 2


def test_echo_survives_a_console_without_unicode():
    import io

    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252")  # a redirected Windows console
    qe.echo("zh → en: chrF++ 52.3", stream)
    stream.flush()
    assert raw.getvalue().decode("cp1252") == "zh ? en: chrF++ 52.3\n"

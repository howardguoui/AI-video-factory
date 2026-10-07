"""Translation batching, count-mismatch splitting and retries, against a fake OpenAI-compatible server."""

import json
import socket

import pytest

from app.config import settings
from app.services import translate as tr
from app.services.asr import seconds_to_srt_time


def _write_srt(tmp_path, texts):
    segs = [
        tr.Segment(i + 1, seconds_to_srt_time(2 * i), seconds_to_srt_time(2 * i + 1.5), t)
        for i, t in enumerate(texts)
    ]
    path = tmp_path / "source.srt"
    path.write_text(tr.rebuild_srt(segs), encoding="utf-8")
    return path, segs


def _read_srt(path):
    return tr.parse_srt(open(path, encoding="utf-8").read())


def test_translate_srt_batches_and_keeps_timing(fake_llm, tmp_path):
    texts = [f"line {i}" for i in range(45)]
    path, source = _write_srt(tmp_path, texts)
    progress = []

    out = tr.translate_srt(str(path), "en", llm_model="test-model", progress_callback=lambda p, d: progress.append(p))

    result = _read_srt(out)
    assert out.endswith("translated.srt")
    assert [s.text for s in result] == [f"T:{t}" for t in texts]
    assert [(s.index, s.start, s.end) for s in result] == [(s.index, s.start, s.end) for s in source]
    # 45 segments in batches of BATCH_SIZE (20): 20 + 20 + 5
    assert [len(json.loads(c["messages"][1]["content"])) for c in fake_llm.calls] == [20, 20, 5]
    assert {c["model"] for c in fake_llm.calls} == {"test-model"}
    assert "English" in fake_llm.calls[0]["messages"][0]["content"]
    assert progress[-1] == 1.0 and progress == sorted(progress)


def test_markdown_fenced_json_is_accepted(fake_llm, tmp_path):
    fake_llm.reply = lambda texts, system: "```json\n" + json.dumps([t.upper() for t in texts]) + "\n```"
    path, _ = _write_srt(tmp_path, ["a", "b"])

    assert [s.text for s in _read_srt(tr.translate_srt(str(path), "en"))] == ["A", "B"]
    assert len(fake_llm.calls) == 1


def test_malformed_json_retries_once_with_stricter_prompt(fake_llm, tmp_path):
    def reply(texts, system):
        if "MUST return valid JSON" in system:
            return json.dumps([t + "!" for t in texts])
        return "Sure! Here are the translations: a!, b!"

    fake_llm.reply = reply
    path, _ = _write_srt(tmp_path, ["a", "b"])

    assert [s.text for s in _read_srt(tr.translate_srt(str(path), "en"))] == ["a!", "b!"]
    assert len(fake_llm.calls) == 2


def test_merged_lines_split_the_batch_until_counts_match(fake_llm, tmp_path):
    # A small model that merges adjacent lines whenever it gets more than two.
    def reply(texts, system):
        if len(texts) > 2:
            return json.dumps([" ".join(texts)])
        return json.dumps([f"T:{t}" for t in texts])

    fake_llm.reply = reply
    texts = ["a", "b", "c", "d", "e"]
    path, _ = _write_srt(tmp_path, texts)

    assert [s.text for s in _read_srt(tr.translate_srt(str(path), "en"))] == [f"T:{t}" for t in texts]
    sizes = [len(json.loads(c["messages"][1]["content"])) for c in fake_llm.calls]
    assert sizes == [5, 2, 3, 1, 2]  # whole batch, left half, right half, then the right half split again


def test_single_line_that_never_translates_keeps_the_original(fake_llm, tmp_path):
    fake_llm.reply = lambda texts, system: "not json" if "bad" in texts else json.dumps([f"T:{t}" for t in texts])
    path, _ = _write_srt(tmp_path, ["ok", "bad"])

    assert [s.text for s in _read_srt(tr.translate_srt(str(path), "en"))] == ["T:ok", "bad"]


def test_translate_text_translates_paragraphs(fake_llm, tmp_path):
    src = tmp_path / "source.txt"
    src.write_text("First paragraph.\n\n\n\nSecond paragraph.\n", encoding="utf-8")

    out = tr.translate_text(str(src), "zh")

    assert open(out, encoding="utf-8").read() == "T:First paragraph.\n\nT:Second paragraph."
    assert "Chinese" in fake_llm.calls[0]["messages"][0]["content"]


def test_unreachable_server_raises_a_clear_error(monkeypatch, tmp_path):
    with socket.socket() as s:  # grab a free port, then close it so nothing is listening
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    monkeypatch.setattr(settings, "ollama_base_url", f"http://127.0.0.1:{port}/v1")
    path, _ = _write_srt(tmp_path, ["a"])

    with pytest.raises(RuntimeError, match="Cannot reach Ollama"):
        tr.translate_srt(str(path), "en", llm_model="m")


def test_empty_srt_is_rejected(tmp_path):
    path = tmp_path / "empty.srt"
    path.write_text("\n", encoding="utf-8")
    with pytest.raises(ValueError, match="No segments"):
        tr.translate_srt(str(path), "en")

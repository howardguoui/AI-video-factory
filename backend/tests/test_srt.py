"""SRT timestamp formatting, writing and parsing."""

from types import SimpleNamespace

import pytest

from app.services.asr import seconds_to_srt_time, segments_to_srt
from app.services.translate import Segment, parse_srt, rebuild_srt


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "00:00:00,000"),
        (1.5, "00:00:01,500"),
        (61.25, "00:01:01,250"),
        (3723.004, "01:02:03,004"),
        # Rounding up to the next millisecond carries through seconds, minutes and hours.
        (0.9996, "00:00:01,000"),
        (59.9996, "00:01:00,000"),
        (3599.9999, "01:00:00,000"),
        (-0.0001, "00:00:00,000"),
    ],
)
def test_seconds_to_srt_time(seconds, expected):
    assert seconds_to_srt_time(seconds) == expected


def test_segments_to_srt_then_parse_round_trips():
    segs = [
        SimpleNamespace(start=0.0, end=2.5, text="  你好，世界  "),
        SimpleNamespace(start=59.9996, end=62.0, text="second line"),
    ]
    parsed = parse_srt(segments_to_srt(segs))

    assert parsed == [
        Segment(1, "00:00:00,000", "00:00:02,500", "你好，世界"),
        Segment(2, "00:01:00,000", "00:01:02,000", "second line"),
    ]
    assert parse_srt(rebuild_srt(parsed)) == parsed


def test_parse_srt_handles_crlf_multiline_text_and_skips_broken_blocks():
    content = (
        "1\r\n00:00:01,000 --> 00:00:02,000\r\nfirst\r\nwrapped\r\n\r\n"
        "x\r\n00:00:03,000 --> 00:00:04,000\r\nbad index\r\n\r\n"
        "3\r\nno arrow here\r\ntext\r\n\r\n"
        "4\r\n00:00:05,000 --> 00:00:06,000\r\n\r\n"  # no text line
        "5\r\n00:00:07,000 --> 00:00:08,000\r\nlast\r\n"
    )
    assert parse_srt(content) == [
        Segment(1, "00:00:01,000", "00:00:02,000", "first wrapped"),
        Segment(5, "00:00:07,000", "00:00:08,000", "last"),
    ]

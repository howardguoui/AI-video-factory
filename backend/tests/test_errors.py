"""Job failure classification: CUDA OOM (fail, no retry) vs transient (retry) vs other (fail)."""

import openai
import pytest

from app.errors import is_cuda_oom, is_transient


class OutOfMemoryError(RuntimeError):
    """Same class name as torch.OutOfMemoryError, without importing torch."""


class ConnectionError(Exception):  # noqa: A001 — mimics redis.exceptions.ConnectionError's name
    pass


def wrapped(inner: BaseException, step: str = "transcribe") -> RuntimeError:
    """Raise `inner` and wrap it the way worker._step does; return the wrapper."""
    try:
        try:
            raise inner
        except BaseException as exc:
            raise RuntimeError(f"Step '{step}' failed after 1.0s: {exc}") from exc
    except RuntimeError as outer:
        return outer


def openai_connection_error() -> openai.APIConnectionError:
    import httpx

    return openai.APIConnectionError(request=httpx.Request("POST", "http://localhost:11434/v1/chat/completions"))


@pytest.mark.parametrize(
    "exc",
    [
        RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB"),
        RuntimeError("CUDA failed with error out of memory"),  # CTranslate2
        OutOfMemoryError("allocation failed"),
        wrapped(OutOfMemoryError("allocation failed"), "synthesize_tts"),
    ],
)
def test_cuda_oom_is_detected(exc):
    assert is_cuda_oom(exc)


@pytest.mark.parametrize(
    "exc",
    [
        wrapped(ConnectionRefusedError(111, "Connection refused")),
        wrapped(TimeoutError("timed out")),  # message names neither type nor "connection"
        wrapped(BrokenPipeError(32, "Broken pipe")),
        wrapped(ConnectionError("Error 111 connecting to localhost:6379.")),  # redis-style, by class name
        wrapped(openai_connection_error(), "translate"),  # "Connection error." from openai
        RuntimeError("redis is loading the dataset in memory"),
    ],
)
def test_transient_errors_are_retried(exc):
    assert is_transient(exc)
    assert not is_cuda_oom(exc)


def test_ollama_unreachable_through_translate_wrapper_is_transient():
    # translate_srt re-raises connection failures as "Cannot reach Ollama ..." from the openai error.
    try:
        try:
            raise openai_connection_error()
        except openai.APIConnectionError as e:
            raise RuntimeError("Cannot reach Ollama at http://localhost:11434/v1.") from e
    except RuntimeError as exc:
        assert is_transient(wrapped(exc, "translate"))


@pytest.mark.parametrize(
    "exc",
    [
        wrapped(ValueError("No segments parsed from source.srt")),
        RuntimeError("FFmpeg audio extraction failed: Invalid data found when processing input"),
        wrapped(FileNotFoundError("input.mp4")),
    ],
)
def test_ordinary_failures_are_neither(exc):
    assert not is_transient(exc)
    assert not is_cuda_oom(exc)


def test_self_referencing_chain_terminates():
    a, b = RuntimeError("a"), RuntimeError("b")
    a.__context__, b.__context__ = b, a
    assert not is_transient(a) and not is_cuda_oom(a)

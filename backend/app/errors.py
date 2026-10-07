"""
Failure classification for the Celery pipeline: decide whether a failed job is
a CUDA out-of-memory error (don't retry, tell the user how to shrink the job),
a transient infrastructure error (retry), or anything else (fail).

Kept free of Celery, Redis and torch imports so it can be unit-tested anywhere.

Pipeline steps wrap their exceptions (`RuntimeError("Step 'x' failed ...") from
exc`, `RuntimeError("Cannot reach Ollama ...") from e`), and the message of a
wrapped network error often names neither its type nor the word "connection"
(openai's APIConnectionError reads "Connection error.", a socket timeout reads
"timed out"). So both checks walk the whole exception chain and look at each
exception's type as well as its message.
"""

from collections.abc import Iterator

_OOM_TYPE_NAMES = frozenset({"OutOfMemoryError"})  # torch.OutOfMemoryError / torch.cuda.OutOfMemoryError
_OOM_MESSAGES = ("CUDA out of memory", "OutOfMemoryError", "out of memory")

# Matched by class name so the check needs neither redis nor openai installed.
# Built-in ConnectionError (incl. BrokenPipe/ConnectionRefused/Reset) and
# TimeoutError are also matched with isinstance below.
_TRANSIENT_TYPE_NAMES = frozenset({
    "ConnectionError",      # redis.exceptions.ConnectionError, requests.ConnectionError
    "TimeoutError",         # redis.exceptions.TimeoutError
    "APIConnectionError",   # openai: server (Ollama) unreachable or dropped the connection
    "APITimeoutError",      # openai: request timed out
})
_TRANSIENT_MESSAGES = (
    "ConnectionError", "TimeoutError", "redis", "ECONNREFUSED",
    "Connection refused", "BrokenPipeError",
)


def _chain(exc: BaseException) -> Iterator[BaseException]:
    """Yield exc and every exception it was raised from or during, without looping."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def is_cuda_oom(exc: BaseException) -> bool:
    """True if any exception in the chain is a GPU out-of-memory error."""
    return any(
        type(e).__name__ in _OOM_TYPE_NAMES or any(kw in str(e) for kw in _OOM_MESSAGES)
        for e in _chain(exc)
    )


def is_transient(exc: BaseException) -> bool:
    """True if any exception in the chain is a network / Redis / Ollama connection failure worth retrying."""
    for e in _chain(exc):
        if isinstance(e, (ConnectionError, TimeoutError)):
            return True
        if any(cls.__name__ in _TRANSIENT_TYPE_NAMES for cls in type(e).__mro__):
            return True
        if any(kw in str(e) for kw in _TRANSIENT_MESSAGES):
            return True
    return False

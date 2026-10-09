"""
Per-stage GPU memory telemetry.

While a pipeline stage runs, a background thread polls NVML for the GPU's used
memory and keeps the peak. NVML reports device-wide usage, so the number covers
every process on the card: the Whisper subprocess, the Ollama server, the TTS
model in the worker, and anything else using the GPU (desktop, browser). That is
the figure that matters for "does this stage fit in 16 GB".

Telemetry is best-effort: without nvidia-ml-py, without an NVIDIA driver, or on
any NVML error it records nothing and never fails the job. Kept free of Celery,
Redis and torch imports so it can be unit-tested anywhere.

NVML calls used (nvidia-ml-py, module `pynvml`): nvmlInit, nvmlShutdown,
nvmlDeviceGetHandleByIndex, nvmlDeviceGetMemoryInfo (returns `.total`, `.free`,
`.used` in bytes).
"""

import logging
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from types import ModuleType

logger = logging.getLogger(__name__)

MIB = 1024 * 1024


def _load_nvml() -> ModuleType | None:
    try:
        import pynvml  # provided by the nvidia-ml-py package
    except Exception:
        return None
    return pynvml


class VramSampler:
    """
    Polls one GPU's used memory on a daemon thread between start() and stop().

    stop() returns {"peak_mib": int, "total_mib": int}, or None when nothing
    could be measured. A sample is taken at start and at stop as well, so even a
    stage shorter than the polling interval gets a reading.
    """

    def __init__(self, nvml: ModuleType | None = None, device_index: int = 0, interval_s: float = 0.25):
        self._nvml = nvml
        self._device_index = device_index
        self._interval_s = interval_s
        self._handle = None
        self._initialised = False
        self._peak_bytes: int | None = None
        self._total_bytes: int | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        nvml = self._nvml or _load_nvml()
        if nvml is None:
            logger.debug("VRAM telemetry off: nvidia-ml-py (pynvml) is not installed")
            return
        try:
            nvml.nvmlInit()
        except Exception as exc:
            logger.debug(f"VRAM telemetry off: NVML init failed: {exc}")
            return
        self._nvml = nvml
        self._initialised = True
        try:
            self._handle = nvml.nvmlDeviceGetHandleByIndex(self._device_index)
        except Exception as exc:
            logger.warning(f"VRAM telemetry off: no GPU at NVML index {self._device_index}: {exc}")
            return
        self._sample()
        self._thread = threading.Thread(target=self._run, name="vram-sampler", daemon=True)
        self._thread.start()

    def _sample(self) -> None:
        try:
            info = self._nvml.nvmlDeviceGetMemoryInfo(self._handle)
        except Exception as exc:
            logger.debug(f"VRAM sample failed: {exc}")
            return
        with self._lock:
            if self._peak_bytes is None or info.used > self._peak_bytes:
                self._peak_bytes = int(info.used)
            self._total_bytes = int(info.total)

    def _run(self) -> None:
        while not self._stop.wait(self._interval_s):
            self._sample()

    def stop(self) -> dict | None:
        if self._thread is not None:
            self._stop.set()
            self._thread.join(timeout=max(1.0, 4 * self._interval_s))
            self._thread = None
            self._sample()
        if self._initialised:
            self._initialised = False
            try:
                self._nvml.nvmlShutdown()
            except Exception:
                pass
        with self._lock:
            if self._peak_bytes is None or self._total_bytes is None:
                return None
            return {
                "peak_mib": round(self._peak_bytes / MIB),
                "total_mib": round(self._total_bytes / MIB),
            }


@contextmanager
def track_stage_vram(
    stage: str,
    record: Callable[[str, dict], None],
    *,
    enabled: bool = True,
    device_index: int = 0,
    interval_s: float = 0.25,
    nvml: ModuleType | None = None,
) -> Iterator[None]:
    """
    Measure peak GPU memory while the block runs and pass it to `record(stage, peak)`.

    The peak is recorded whether the block succeeds or raises (a stage that hits
    CUDA OOM is the one whose peak you most want to see). The block's exception
    always propagates unchanged; a failing `record` is logged and swallowed.
    """
    sampler = VramSampler(nvml=nvml, device_index=device_index, interval_s=interval_s) if enabled else None
    if sampler is not None:
        sampler.start()
    try:
        yield
    finally:
        peak = sampler.stop() if sampler is not None else None
        if peak is not None:
            logger.info(f"{stage}: peak VRAM {peak['peak_mib']} / {peak['total_mib']} MiB")
            try:
                record(stage, peak)
            except Exception as exc:
                logger.error(f"Recording VRAM for stage '{stage}' failed: {exc}")

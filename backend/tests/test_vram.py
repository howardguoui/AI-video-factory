"""Per-stage VRAM telemetry against a fake NVML module (no GPU, driver or nvidia-ml-py needed)."""

import importlib
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from app.models.job import JobResponse
from app.vram import MIB, VramSampler, track_stage_vram

TOTAL = 16303 * MIB  # what NVML reports for a 16 GB card


class FakeNvml:
    """Stands in for `pynvml`. Each memory query returns the next `used` value; the last one repeats."""

    def __init__(self, used_mib, *, fail_init=False, fail_handle=False, fail_query_at=()):
        self.used = [u * MIB for u in used_mib]
        self.fail_init = fail_init
        self.fail_handle = fail_handle
        self.fail_query_at = set(fail_query_at)
        self.queries = 0
        self.inits = 0
        self.shutdowns = 0
        self.handle_index = None
        self.lock = threading.Lock()

    def nvmlInit(self):  # noqa: N802 (NVML API names)
        if self.fail_init:
            raise RuntimeError("NVML Shared Library Not Found")
        self.inits += 1

    def nvmlShutdown(self):  # noqa: N802
        self.shutdowns += 1

    def nvmlDeviceGetHandleByIndex(self, index):  # noqa: N802
        if self.fail_handle:
            raise RuntimeError("Invalid Argument")
        self.handle_index = index
        return object()

    def nvmlDeviceGetMemoryInfo(self, handle):  # noqa: N802
        with self.lock:
            i = self.queries
            self.queries += 1
        if i in self.fail_query_at:
            raise RuntimeError("GPU is lost")
        used = self.used[min(i, len(self.used) - 1)]
        return SimpleNamespace(total=TOTAL, free=TOTAL - used, used=used)


def test_peak_is_highest_sample_and_total_is_reported():
    nvml = FakeNvml([2000, 9000, 14500, 6000])
    sampler = VramSampler(nvml=nvml, interval_s=0.001)
    sampler.start()
    deadline = time.monotonic() + 5
    while nvml.queries < 6 and time.monotonic() < deadline:
        time.sleep(0.001)
    assert sampler.stop() == {"peak_mib": 14500, "total_mib": 16303}
    assert nvml.inits == nvml.shutdowns == 1


def test_stage_shorter_than_interval_still_gets_start_and_stop_samples():
    nvml = FakeNvml([3000, 7000])
    sampler = VramSampler(nvml=nvml, interval_s=60)
    sampler.start()
    assert sampler.stop() == {"peak_mib": 7000, "total_mib": 16303}
    assert nvml.queries == 2


def test_sampler_thread_stops():
    nvml = FakeNvml([1000])
    sampler = VramSampler(nvml=nvml, interval_s=0.001)
    sampler.start()
    sampler.stop()
    after = nvml.queries
    threading.Event().wait(0.05)
    assert nvml.queries == after
    assert not any(t.name == "vram-sampler" for t in threading.enumerate())


def test_uses_configured_device_index():
    nvml = FakeNvml([1000])
    sampler = VramSampler(nvml=nvml, device_index=1, interval_s=60)
    sampler.start()
    sampler.stop()
    assert nvml.handle_index == 1


def test_failed_samples_are_skipped():
    nvml = FakeNvml([5000, 8000], fail_query_at={0})
    sampler = VramSampler(nvml=nvml, interval_s=60)
    sampler.start()
    assert sampler.stop() == {"peak_mib": 8000, "total_mib": 16303}


@pytest.mark.parametrize("nvml", [
    FakeNvml([1000], fail_init=True),     # no NVIDIA driver
    FakeNvml([1000], fail_handle=True),   # wrong device index
    FakeNvml([1000], fail_query_at={0, 1}),  # every query fails
])
def test_no_reading_when_nvml_is_unusable(nvml):
    sampler = VramSampler(nvml=nvml, interval_s=60)
    sampler.start()
    assert sampler.stop() is None
    assert nvml.shutdowns == nvml.inits  # shut down exactly when initialised


def test_no_reading_when_pynvml_is_not_installed(monkeypatch):
    monkeypatch.setattr("app.vram._load_nvml", lambda: None)
    sampler = VramSampler(interval_s=60)
    sampler.start()
    assert sampler.stop() is None


def test_track_stage_records_peak():
    recorded = []
    with track_stage_vram("transcribe", lambda s, p: recorded.append((s, p)), nvml=FakeNvml([4000, 9500]), interval_s=60):
        pass
    assert recorded == [("transcribe", {"peak_mib": 9500, "total_mib": 16303})]


def test_track_stage_records_peak_when_stage_fails_and_reraises_unchanged():
    recorded = []
    err = RuntimeError("CUDA out of memory")
    with pytest.raises(RuntimeError) as info:
        with track_stage_vram("synthesize_tts", lambda s, p: recorded.append(s), nvml=FakeNvml([15900]), interval_s=60):
            raise err
    assert info.value is err
    assert recorded == ["synthesize_tts"]


def test_track_stage_survives_a_failing_recorder():
    def record(stage, peak):
        raise ConnectionError("redis down")

    with track_stage_vram("translate", record, nvml=FakeNvml([1000]), interval_s=60):
        pass  # no exception: telemetry must never fail the job


def test_track_stage_disabled_records_nothing_and_never_touches_nvml():
    nvml = FakeNvml([1000])
    recorded = []
    with track_stage_vram("mux_video", lambda s, p: recorded.append(s), enabled=False, nvml=nvml):
        pass
    assert recorded == [] and nvml.inits == 0 and nvml.queries == 0


def test_track_stage_without_gpu_records_nothing():
    recorded = []
    with track_stage_vram("transcribe", lambda s, p: recorded.append(s), nvml=FakeNvml([1], fail_init=True)):
        pass
    assert recorded == []


def test_job_response_exposes_stage_vram_in_run_order():
    job = JobResponse(
        job_id="j", status="done",
        stage_vram={
            "transcribe": {"peak_mib": 9500, "total_mib": 16303},
            "translate": {"peak_mib": 7100, "total_mib": 16303},
        },
    )
    assert list(job.model_dump()["stage_vram"]) == ["transcribe", "translate"]
    assert job.stage_vram["transcribe"].peak_mib == 9500
    assert JobResponse(job_id="k", status="queued").stage_vram == {}


class FakeRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = value


def test_update_status_merges_stage_vram_per_stage(monkeypatch):
    # app.state imports redis at module level; CI does not install it.
    if "app.state" not in sys.modules:
        try:
            import redis  # noqa: F401
        except ImportError:
            monkeypatch.setitem(sys.modules, "redis", SimpleNamespace(from_url=lambda *a, **k: None))
    state = importlib.import_module("app.state")
    monkeypatch.setattr(state, "_redis", FakeRedis())

    state.set_job("j", {"job_id": "j", "status": "transcribing"})
    state.update_status("j", None, stage_vram={"transcribe": {"peak_mib": 9500, "total_mib": 16303}})
    state.update_status("j", "translating", step=3)
    state.update_status("j", None, stage_vram={"translate": {"peak_mib": 7100, "total_mib": 16303}})

    job = state.get_job_data("j")
    assert job["status"] == "translating"
    assert job["stage_vram"] == {
        "transcribe": {"peak_mib": 9500, "total_mib": 16303},
        "translate": {"peak_mib": 7100, "total_mib": 16303},
    }

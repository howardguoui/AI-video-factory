"""
ASR service — transcription via faster-whisper.

The WhisperModel is run inside a dedicated subprocess so that CTranslate2's
CUDA destructor crash (which kills the Celery worker process silently) is
contained. The subprocess exits normally; the OS reclaims GPU memory safely.
The parent process is unaffected even if the subprocess crashes.
"""
import gc
import json
import logging
import multiprocessing
import shutil
import sys
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SRT helpers (used by both main process and subprocess)
# ---------------------------------------------------------------------------

def seconds_to_srt_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds % 1) * 1000))
    if millis >= 1000:
        millis = 0
        secs += 1
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def segments_to_srt(segments) -> str:
    lines = []
    for i, segment in enumerate(segments, start=1):
        start = seconds_to_srt_time(segment.start)
        end = seconds_to_srt_time(segment.end)
        text = segment.text.strip()
        lines.append(f"{i}\n{start} --> {end}\n{text}\n")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Subprocess entry point — ALL CTranslate2/CUDA work happens here.
# No explicit model deletion: process exit reclaims GPU memory safely.
# ---------------------------------------------------------------------------

def _subprocess_transcribe(config_json: str, parent_sys_path: list) -> None:
    """
    Runs inside a spawned subprocess. Receives all config as a JSON string
    so there is no shared state with the parent process.

    Key design decision: we do NOT call `del model` or `torch.cuda.empty_cache()`
    before exiting. CTranslate2's CUDA destructor is broken under sustained use
    and causes a fatal C-level crash that bypasses Python exception handling.
    Letting the OS reclaim VRAM on process exit is safe and avoids the crash.
    """
    # Restore sys.path so app.* imports work inside the subprocess (spawn starts fresh)
    for p in parent_sys_path:
        if p not in sys.path:
            sys.path.insert(0, p)

    import logging as _logging
    _logging.basicConfig(
        level=_logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        force=True,
    )
    sub_log = _logging.getLogger(__name__)

    cfg = json.loads(config_json)
    job_id = cfg["job_id"]
    result_file = Path(cfg["result_file"])

    try:
        import torch
        from faster_whisper import WhisperModel
        import ffmpeg
        from types import SimpleNamespace

        device = cfg["device"]
        compute_type = cfg["compute_type"]

        if device == "cuda" and not torch.cuda.is_available():
            sub_log.warning(f"[{job_id}] CUDA not available, falling back to CPU")
            device = "cpu"
            compute_type = "int8"

        sub_log.info(
            f"[{job_id}] Loading Whisper model={cfg['model_size']} "
            f"device={device} compute_type={compute_type} beam_size={cfg['beam_size']}"
        )
        model = WhisperModel(cfg["model_size"], device=device, compute_type=compute_type)

        # ---- split audio into chunks ----
        job_dir = Path(cfg["storage_path"]) / job_id
        chunks_dir = job_dir / "chunks"
        chunks_dir.mkdir(exist_ok=True)

        try:
            probe = ffmpeg.probe(cfg["audio_path"])
            total_duration = float(probe["format"]["duration"])
        except Exception as e:
            raise RuntimeError(f"Could not probe audio duration: {e}") from e

        chunks = []
        offset, idx = 0.0, 0
        chunk_seconds = cfg["chunk_seconds"]
        while offset < total_duration:
            chunk_path = str(chunks_dir / f"chunk_{idx:03d}.wav")
            (
                ffmpeg
                .input(cfg["audio_path"], ss=offset, t=chunk_seconds)
                .output(chunk_path, ac=1, ar=16000, acodec="pcm_s16le")
                .overwrite_output()
                .run(quiet=True)
            )
            chunks.append((chunk_path, offset))
            offset += chunk_seconds
            idx += 1

        sub_log.info(f"[{job_id}] Split audio into {len(chunks)} chunks of {chunk_seconds}s each")

        # ---- transcribe sequentially ----
        all_segments = []
        for i, (chunk_path, chunk_offset) in enumerate(chunks):
            sub_log.info(f"[{job_id}] Chunk {i + 1}/{len(chunks)} (offset={chunk_offset:.0f}s)")
            raw_segs, _ = model.transcribe(
                chunk_path,
                word_timestamps=True,
                beam_size=cfg["beam_size"],
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
            )
            segs = [
                SimpleNamespace(
                    start=s.start + chunk_offset,
                    end=s.end + chunk_offset,
                    text=s.text,
                )
                for s in raw_segs
            ]
            all_segments.extend(segs)
            sub_log.info(f"[{job_id}] Chunk {i + 1} done: {len(segs)} segments")

        shutil.rmtree(chunks_dir, ignore_errors=True)
        sub_log.info(f"[{job_id}] Transcription complete: {len(all_segments)} segments total")

        # ---- write SRT ----
        srt_path = cfg["srt_path"]

        def _to_srt_time(s: float) -> str:
            h, m = int(s // 3600), int((s % 3600) // 60)
            sec, ms = int(s % 60), int(round((s % 1) * 1000))
            if ms >= 1000:
                ms, sec = 0, sec + 1
            return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"

        lines = []
        for i, seg in enumerate(all_segments, start=1):
            lines.append(f"{i}\n{_to_srt_time(seg.start)} --> {_to_srt_time(seg.end)}\n{seg.text.strip()}\n")
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        sub_log.info(f"[{job_id}] SRT written: {srt_path}")

        result_file.write_text(json.dumps({
            "status": "ok",
            "srt_path": srt_path,
            "segment_count": len(all_segments),
        }))

        # Intentionally NOT deleting model or calling cuda.empty_cache() here.
        # Process exit is the safe way to free CTranslate2 CUDA resources.

    except Exception as exc:
        import traceback
        result_file.write_text(json.dumps({
            "status": "error",
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }))
        sys.exit(1)


# ---------------------------------------------------------------------------
# Public API — called by the Celery worker
# ---------------------------------------------------------------------------

def transcribe(audio_path: str, job_id: str) -> str:
    """
    Transcribe audio to SRT. Spawns a subprocess to isolate CTranslate2's
    CUDA destructor crash from the Celery worker process.

    Optimisations active inside the subprocess:
      1. VAD pre-filter  — removes silence before feeding Whisper (~1.4x speedup)
      2. Audio chunking  — splits long audio into asr_chunk_minutes pieces
    """
    job_dir = Path(settings.storage_path) / job_id
    srt_path = str(job_dir / "source.srt")
    result_file = str(job_dir / "_transcribe_result.json")

    config_json = json.dumps({
        "job_id": job_id,
        "audio_path": audio_path,
        "srt_path": srt_path,
        "result_file": result_file,
        "model_size": settings.whisper_model_size,
        "device": settings.whisper_device,
        "compute_type": settings.whisper_compute_type,
        "beam_size": settings.whisper_beam_size,
        "chunk_seconds": settings.asr_chunk_minutes * 60,
        "storage_path": settings.storage_path,
    })

    logger.info(f"[{job_id}] Spawning transcription subprocess")
    ctx = multiprocessing.get_context("spawn")
    proc = ctx.Process(
        target=_subprocess_transcribe,
        args=(config_json, sys.path[:]),
        name=f"transcribe-{job_id[:8]}",
    )
    proc.start()
    timeout = settings.asr_chunk_minutes * 60 * 20  # generous: 20× chunk_minutes
    proc.join(timeout=timeout)

    if proc.is_alive():
        proc.kill()
        proc.join()
        raise RuntimeError(
            f"[{job_id}] Transcription subprocess timed out after {timeout}s"
        )

    result_path = Path(result_file)
    if not result_path.exists():
        raise RuntimeError(
            f"[{job_id}] Transcription subprocess exited with code {proc.exitcode} "
            "and left no result file — likely a fatal CUDA or OOM error"
        )

    result = json.loads(result_path.read_text())
    result_path.unlink(missing_ok=True)

    if result["status"] != "ok":
        tb = result.get("traceback", "")
        raise RuntimeError(
            f"[{job_id}] Transcription failed: {result.get('error', 'unknown')}\n{tb}"
        )

    logger.info(
        f"[{job_id}] Transcription complete: "
        f"{result.get('segment_count', '?')} segments, SRT: {result['srt_path']}"
    )
    return result["srt_path"]

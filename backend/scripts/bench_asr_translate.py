#!/usr/bin/env python3
"""
Benchmark ASR and translation performance: old settings vs new settings.

Usage:
    python scripts/bench_asr_translate.py [--video-path PATH] [--duration SECONDS]

Requires:
    - Ollama running (ollama serve) if testing translation
    - Redis (if testing translation with real models)

Outputs table with:
    - ASR time (seconds)
    - Translation time (seconds)
    - Segments generated
    - Characters translated
"""
import argparse
import json
import logging
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

# Ensure app is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

import torch
from app.config import settings
from app.services.mux import extract_audio
import ffmpeg

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def find_test_video() -> str:
    """Find shortest test video in storage, or return None."""
    storage_path = Path(settings.storage_path)
    videos = list(storage_path.glob("*/input.mp4"))
    if not videos:
        return None
    # Get duration of each
    shortest = None
    shortest_duration = float("inf")
    for video_path in videos:
        try:
            probe = ffmpeg.probe(str(video_path))
            duration = float(probe["format"]["duration"])
            if duration < shortest_duration:
                shortest_duration = duration
                shortest = str(video_path)
        except Exception:
            pass
    return shortest


def extract_audio_clip(video_path: str, max_duration: float = 60.0) -> str:
    """Extract audio from video, max duration."""
    with TemporaryDirectory() as tmpdir:
        audio_path = str(Path(tmpdir) / "audio.wav")
        try:
            probe = ffmpeg.probe(video_path)
            total_dur = float(probe["format"]["duration"])
            extract_dur = min(total_dur, max_duration)
            (
                ffmpeg.input(video_path, t=extract_dur)
                .output(audio_path, acodec="pcm_s16le", ar=16000, ac=1)
                .overwrite_output()
                .run(quiet=True)
            )
            # Copy to temp location that persists
            final_path = str(Path(settings.storage_path) / "bench_audio.wav")
            import shutil
            shutil.copy2(audio_path, final_path)
            return final_path
        except Exception as e:
            logger.error(f"Failed to extract audio: {e}")
            return None


def benchmark_asr_old(audio_path: str) -> dict:
    """
    Benchmark with OLD settings: large-v3, float16, beam_size=1, VAD enabled.
    This is the current default config.
    """
    logger.info("Starting ASR benchmark (OLD: large-v3, float16, beam_size=1)")
    t0 = time.monotonic()

    try:
        from faster_whisper import WhisperModel

        model = WhisperModel(
            "large-v3",
            device="cuda" if torch.cuda.is_available() else "cpu",
            compute_type="float16",
        )

        segments, _ = model.transcribe(
            audio_path,
            word_timestamps=False,
            beam_size=1,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )

        segs = list(segments)
        elapsed = time.monotonic() - t0

        char_count = sum(len(s.text) for s in segs)
        logger.info(f"ASR (OLD) complete: {len(segs)} segments, {char_count} chars in {elapsed:.1f}s")

        return {
            "model": "large-v3",
            "compute_type": "float16",
            "beam_size": 1,
            "duration_seconds": elapsed,
            "segment_count": len(segs),
            "char_count": char_count,
        }
    except Exception as e:
        logger.error(f"ASR (OLD) failed: {e}")
        return {
            "model": "large-v3",
            "error": str(e),
        }


def benchmark_asr_new(audio_path: str) -> dict:
    """
    Benchmark with NEW settings: large-v3-turbo (if available) or large-v3,
    float16, beam_size=1, VAD enabled.
    """
    logger.info("Starting ASR benchmark (NEW: large-v3-turbo if available, float16, beam_size=1)")
    t0 = time.monotonic()

    try:
        from faster_whisper import WhisperModel

        # Try turbo first, fall back to large-v3
        model_choice = "large-v3-turbo"
        try:
            model = WhisperModel(
                model_choice,
                device="cuda" if torch.cuda.is_available() else "cpu",
                compute_type="float16",
            )
        except Exception:
            logger.info(f"{model_choice} not available, using large-v3 instead")
            model_choice = "large-v3"
            model = WhisperModel(
                model_choice,
                device="cuda" if torch.cuda.is_available() else "cpu",
                compute_type="float16",
            )

        segments, _ = model.transcribe(
            audio_path,
            word_timestamps=False,
            beam_size=1,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )

        segs = list(segments)
        elapsed = time.monotonic() - t0

        char_count = sum(len(s.text) for s in segs)
        logger.info(f"ASR (NEW) complete: {len(segs)} segments, {char_count} chars in {elapsed:.1f}s")

        return {
            "model": model_choice,
            "compute_type": "float16",
            "beam_size": 1,
            "duration_seconds": elapsed,
            "segment_count": len(segs),
            "char_count": char_count,
        }
    except Exception as e:
        logger.error(f"ASR (NEW) failed: {e}")
        return {
            "model": "large-v3-turbo or large-v3",
            "error": str(e),
        }


def benchmark_translation() -> dict:
    """
    Benchmark translation: old model (qwen3-vl) vs new model (qwen3:8b text).
    Requires Ollama running with both models available.
    """
    from openai import OpenAI

    sample_texts = [
        "Hello, this is a test.",
        "The weather is nice today.",
        "How are you doing?",
        "I like machine learning.",
        "This is a benchmark test for translation models.",
    ]

    # OLD: vision model
    logger.info("Starting translation benchmark (OLD: qwen3-vl-abliterated:8b-instruct)")
    t0_old = time.monotonic()
    result_old = {
        "model": "qwen3-vl-abliterated:8b-instruct",
        "error": None,
        "duration_seconds": None,
    }

    try:
        client = OpenAI(api_key="ollama", base_url=settings.ollama_base_url)
        # Try a simple test call
        response = client.chat.completions.create(
            model="huihui_ai/qwen3-vl-abliterated:8b-instruct",
            messages=[
                {"role": "system", "content": "Translate to Chinese."},
                {"role": "user", "content": json.dumps(sample_texts[:2])},
            ],
            temperature=0.3,
        )
        elapsed_old = time.monotonic() - t0_old
        result_old["duration_seconds"] = elapsed_old
        logger.info(f"Translation (OLD) complete in {elapsed_old:.1f}s")
    except Exception as e:
        logger.warning(f"Translation (OLD) failed: {e}")
        result_old["error"] = str(e)

    # NEW: text model
    logger.info("Starting translation benchmark (NEW: qwen3:8b text)")
    t0_new = time.monotonic()
    result_new = {
        "model": "qwen3:8b",
        "error": None,
        "duration_seconds": None,
    }

    try:
        client = OpenAI(api_key="ollama", base_url=settings.ollama_base_url)
        response = client.chat.completions.create(
            model="qwen3:8b",
            messages=[
                {"role": "system", "content": "Translate to Chinese."},
                {"role": "user", "content": json.dumps(sample_texts[:2])},
            ],
            temperature=0.3,
            extra_body={"keep_alive": settings.ollama_keep_alive},
        )
        elapsed_new = time.monotonic() - t0_new
        result_new["duration_seconds"] = elapsed_new
        logger.info(f"Translation (NEW) complete in {elapsed_new:.1f}s")
    except Exception as e:
        logger.warning(f"Translation (NEW) failed: {e}")
        result_new["error"] = str(e)

    return {
        "old": result_old,
        "new": result_new,
    }


def print_benchmark_results(asr_old: dict, asr_new: dict, trans_results: dict) -> None:
    """Print results in a nice table."""
    print("\n" + "=" * 80)
    print("BENCHMARK RESULTS: ASR & TRANSLATION")
    print("=" * 80)

    print("\n--- ASR BENCHMARK ---")
    print(f"{'Metric':<30} {'OLD (large-v3)':<25} {'NEW (turbo)':<25}")
    print("-" * 80)

    if "error" not in asr_old:
        print(f"{'Duration (s)':<30} {asr_old.get('duration_seconds', 'N/A'):<25.1f}", end="")
    else:
        print(f"{'Duration (s)':<30} {'ERROR':<25}", end="")

    if "error" not in asr_new:
        print(f"{asr_new.get('duration_seconds', 'N/A'):<25.1f}")
    else:
        print(f"{'ERROR':<25}")

    if "error" not in asr_old:
        print(f"{'Segments':<30} {asr_old.get('segment_count', 'N/A'):<25}", end="")
    else:
        print(f"{'Segments':<30} {'N/A':<25}", end="")

    if "error" not in asr_new:
        print(f"{asr_new.get('segment_count', 'N/A'):<25}")
    else:
        print("N/A")

    if "error" not in asr_old:
        print(f"{'Characters':<30} {asr_old.get('char_count', 'N/A'):<25}", end="")
    else:
        print(f"{'Characters':<30} {'N/A':<25}", end="")

    if "error" not in asr_new:
        print(f"{asr_new.get('char_count', 'N/A'):<25}")
    else:
        print("N/A")

    print("\n--- TRANSLATION BENCHMARK ---")
    print(f"{'Model':<30} {'OLD (qwen3-vl)':<25} {'NEW (qwen3:8b)':<25}")
    print("-" * 80)

    old_trans = trans_results.get("old", {})
    new_trans = trans_results.get("new", {})

    old_time = old_trans.get("duration_seconds", "N/A")
    new_time = new_trans.get("duration_seconds", "N/A")

    if old_time != "N/A":
        print(f"{'Duration (s)':<30} {old_time:<25.1f}", end="")
    else:
        old_err = old_trans.get("error", "Unknown error")
        print(f"{'Duration (s)':<30} {old_err[:20]:<25}", end="")

    if new_time != "N/A":
        print(f"{new_time:<25.1f}")
    else:
        new_err = new_trans.get("error", "Unknown error")
        print(f"{new_err[:20]:<25}")

    print("\n" + "=" * 80)
    print("Note: Errors indicate the model may not be installed in Ollama.")
    print("Run: ollama pull qwen3:8b (if not installed)")
    print("=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Benchmark ASR and translation models")
    parser.add_argument("--video-path", type=str, default=None, help="Path to test video")
    parser.add_argument("--duration", type=float, default=60.0, help="Max duration to extract (seconds)")
    args = parser.parse_args()

    # Find or use provided video
    video_path = args.video_path or find_test_video()
    if not video_path:
        logger.error("No test video found in storage/*/input.mp4")
        print("Please provide a test video with --video-path")
        sys.exit(1)

    logger.info(f"Using test video: {video_path}")

    # Extract audio clip
    audio_path = extract_audio_clip(video_path, max_duration=args.duration)
    if not audio_path:
        logger.error("Failed to extract audio")
        sys.exit(1)

    logger.info(f"Audio extracted: {audio_path}")

    # Run benchmarks
    logger.info("\n" + "=" * 60)
    logger.info("ASR BENCHMARKS")
    logger.info("=" * 60)
    asr_old = benchmark_asr_old(audio_path)
    asr_new = benchmark_asr_new(audio_path)

    logger.info("\n" + "=" * 60)
    logger.info("TRANSLATION BENCHMARKS (requires Ollama running)")
    logger.info("=" * 60)
    trans_results = benchmark_translation()

    # Print results
    print_benchmark_results(asr_old, asr_new, trans_results)

    # Cleanup
    try:
        Path(audio_path).unlink()
    except Exception:
        pass


if __name__ == "__main__":
    main()

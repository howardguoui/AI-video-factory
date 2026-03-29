"""
TTS + Voice Cloning Service

Priority:
1. Qwen3-TTS 1.7B (when pip-installable)
2. CosyVoice2 (fallback)
3. STUB: copies source audio (enables end-to-end testing without TTS model)

Current default: STUB mode until models are installed.
To enable real TTS: pip install qwen3-tts (or cosyvoice2) and set USE_STUB_TTS=false in .env
"""
import logging
import os
import shutil
import struct
import wave
from pathlib import Path

import ffmpeg

from app.config import settings
from app.services.translate import Segment, parse_srt

logger = logging.getLogger(__name__)

# Set USE_STUB_TTS=false in .env to attempt real TTS model loading
USE_STUB_TTS = os.getenv("USE_STUB_TTS", "true").lower() != "false"


def _srt_time_to_seconds(time_str: str) -> float:
    """Convert SRT timestamp 'HH:MM:SS,mmm' to float seconds."""
    time_str = time_str.replace(",", ".")
    parts = time_str.split(":")
    hours = float(parts[0])
    minutes = float(parts[1])
    seconds = float(parts[2])
    return hours * 3600 + minutes * 60 + seconds


def extract_reference_clip(source_audio_path: str, job_id: str, duration: float = 3.0) -> str:
    """Extract a reference audio clip from the first N seconds of source audio."""
    job_dir = Path(settings.storage_path) / job_id
    ref_path = str(job_dir / "ref.wav")
    try:
        (
            ffmpeg
            .input(source_audio_path, t=duration)
            .output(ref_path, acodec="pcm_s16le", ar=16000, ac=1)
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as e:
        stderr = e.stderr.decode() if e.stderr else "unknown"
        raise RuntimeError(f"Failed to extract reference clip: {stderr}") from e
    logger.info(f"[{job_id}] Reference clip extracted: {ref_path}")
    return ref_path


def _make_silence_wav(path: str, duration_seconds: float, sample_rate: int = 16000) -> None:
    """Create a silent WAV file of the given duration."""
    num_frames = int(duration_seconds * sample_rate)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack("<" + "h" * num_frames, *([0] * num_frames)))


def _stub_synthesize_tts(
    segments: list[Segment],
    source_audio_path: str,
    job_id: str,
) -> str:
    """
    STUB: copies source audio as dubbed audio.
    Allows end-to-end pipeline testing without a real TTS model installed.
    """
    logger.warning(
        f"[{job_id}] TTS STUB MODE: copying original audio as dubbed output. "
        "Install Qwen3-TTS or CosyVoice2 and set USE_STUB_TTS=false to enable real voice cloning."
    )
    job_dir = Path(settings.storage_path) / job_id
    dubbed_path = str(job_dir / "dubbed.wav")
    job_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_audio_path, dubbed_path)
    return dubbed_path


def _assemble_audio_clips(
    clips: list[tuple[float, str]],  # (start_time_seconds, wav_path)
    total_duration: float,
    output_path: str,
    sample_rate: int = 16000,
) -> None:
    """
    Assemble audio clips into a single track at specific timestamps.
    Gaps are filled with silence.
    """
    import wave as wave_module

    all_samples: list[int] = [0] * int(total_duration * sample_rate)

    for start_time, clip_path in clips:
        start_sample = int(start_time * sample_rate)
        try:
            with wave_module.open(clip_path, "rb") as wf:
                clip_samples_raw = wf.readframes(wf.getnframes())
                # Unpack as 16-bit signed integers
                clip_samples = list(struct.unpack("<" + "h" * (len(clip_samples_raw) // 2), clip_samples_raw))
        except Exception as e:
            logger.warning(f"Could not read clip {clip_path}: {e}, skipping")
            continue

        end_sample = min(start_sample + len(clip_samples), len(all_samples))
        clip_end = end_sample - start_sample
        for idx in range(clip_end):
            # Clamp to int16 range
            all_samples[start_sample + idx] = max(-32768, min(32767, clip_samples[idx]))

    with wave_module.open(output_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack("<" + "h" * len(all_samples), *all_samples))


def _get_audio_duration(path: str) -> float:
    """Get audio duration in seconds using ffprobe."""
    try:
        probe = ffmpeg.probe(path)
        return float(probe["format"]["duration"])
    except Exception as e:
        raise RuntimeError(f"Could not get audio duration for {path}: {e}") from e


def synthesize_tts(translated_srt_path: str, source_audio_path: str, job_id: str) -> str:
    """
    Synthesize dubbed audio using voice cloning.
    Falls back through: Qwen3-TTS → CosyVoice2 → STUB.
    """
    with open(translated_srt_path, encoding="utf-8") as f:
        srt_content = f.read()
    segments = parse_srt(srt_content)

    if not segments:
        raise ValueError(f"No segments found in {translated_srt_path}")

    if USE_STUB_TTS:
        return _stub_synthesize_tts(segments, source_audio_path, job_id)

    # --- Real TTS path ---
    job_dir = Path(settings.storage_path) / job_id
    ref_audio_path = extract_reference_clip(source_audio_path, job_id)

    # Try Qwen3-TTS
    try:
        from qwen3_tts import Qwen3TTS  # type: ignore
        return _synthesize_with_qwen3(segments, ref_audio_path, source_audio_path, job_id, job_dir)
    except ImportError:
        logger.warning(f"[{job_id}] Qwen3-TTS not available, trying CosyVoice2")

    # Try CosyVoice2
    try:
        from cosyvoice.cli.cosyvoice import CosyVoice2  # type: ignore
        return _synthesize_with_cosyvoice(segments, ref_audio_path, source_audio_path, job_id, job_dir)
    except ImportError:
        logger.warning(f"[{job_id}] CosyVoice2 not available, falling back to stub")

    return _stub_synthesize_tts(segments, source_audio_path, job_id)


def _synthesize_with_qwen3(
    segments: list[Segment],
    ref_audio_path: str,
    source_audio_path: str,
    job_id: str,
    job_dir: Path,
) -> str:
    import torch
    from qwen3_tts import Qwen3TTS  # type: ignore

    logger.info(f"[{job_id}] Loading Qwen3-TTS model on {settings.qwen_device}")
    model = Qwen3TTS.from_pretrained("Qwen/Qwen3-TTS-1.7B-Base")
    model = model.to(settings.qwen_device)

    try:
        clips: list[tuple[float, str]] = []
        for i, seg in enumerate(segments):
            start_sec = _srt_time_to_seconds(seg.start)
            end_sec = _srt_time_to_seconds(seg.end)
            duration = end_sec - start_sec
            clip_path = str(job_dir / f"clip_{i:04d}.wav")

            wav = model.synthesize(
                text=seg.text,
                reference_audio=ref_audio_path,
                target_duration=duration,
            )
            # Save wav tensor to file
            import torchaudio
            torchaudio.save(clip_path, wav.unsqueeze(0).cpu(), sample_rate=16000)
            clips.append((start_sec, clip_path))
    finally:
        del model
        torch.cuda.empty_cache()
        logger.info(f"[{job_id}] Qwen3-TTS model unloaded")

    dubbed_path = str(job_dir / "dubbed.wav")
    total_duration = _get_audio_duration(source_audio_path)
    _assemble_audio_clips(clips, total_duration, dubbed_path)
    return dubbed_path


def _synthesize_with_cosyvoice(
    segments: list[Segment],
    ref_audio_path: str,
    source_audio_path: str,
    job_id: str,
    job_dir: Path,
) -> str:
    import torch
    from cosyvoice.cli.cosyvoice import CosyVoice2  # type: ignore

    logger.info(f"[{job_id}] Loading CosyVoice2 model on {settings.qwen_device}")
    model = CosyVoice2("iic/CosyVoice2-0.5B", load_jit=False, load_trt=False)
    try:
        model = model.to(settings.qwen_device)
    except Exception:
        pass  # CosyVoice2 may not support .to() — device selection via init args

    try:
        clips: list[tuple[float, str]] = []
        for i, seg in enumerate(segments):
            start_sec = _srt_time_to_seconds(seg.start)
            clip_path = str(job_dir / f"clip_{i:04d}.wav")
            # Zero-shot voice cloning with reference audio
            for result in model.inference_zero_shot(
                seg.text, ref_audio_path, ref_audio_path, stream=False
            ):
                import torchaudio
                torchaudio.save(clip_path, result["tts_speech"], model.sample_rate)
                break
            clips.append((start_sec, clip_path))
    finally:
        del model
        torch.cuda.empty_cache()
        logger.info(f"[{job_id}] CosyVoice2 model unloaded")

    dubbed_path = str(job_dir / "dubbed.wav")
    total_duration = _get_audio_duration(source_audio_path)
    _assemble_audio_clips(clips, total_duration, dubbed_path)
    return dubbed_path

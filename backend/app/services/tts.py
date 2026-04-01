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
USE_STUB_TTS = settings.use_stub_tts


def _srt_time_to_seconds(time_str: str) -> float:
    """Convert SRT timestamp 'HH:MM:SS,mmm' to float seconds."""
    time_str = time_str.replace(",", ".")
    parts = time_str.split(":")
    hours = float(parts[0])
    minutes = float(parts[1])
    seconds = float(parts[2])
    return hours * 3600 + minutes * 60 + seconds


def extract_reference_clip(source_audio_path: str, job_id: str, duration: float = 12.0) -> str:
    """
    Extract the best speech reference clip for Qwen3-TTS voice cloning.
    - Scans first 45s, picks window with highest speech ratio (RMS + non-silence frames)
    - Optimal duration: 10-15s (research shows quality plateaus/degrades beyond 15s)
    - Appends 0.5s silence to end to fix "rough start" first-word artifact
    - Outputs at 24kHz mono to match Qwen3-TTS native rate
    """
    import struct
    import numpy as np
    import wave as wave_module

    job_dir = Path(settings.storage_path) / job_id
    ref_path = str(job_dir / "ref.wav")
    scan_path = str(job_dir / "ref_scan.wav")

    total_duration = _get_audio_duration(source_audio_path)
    scan_duration = min(total_duration, 45.0)  # scan first 45s — avoid instability from 60s+

    try:
        (
            ffmpeg
            .input(source_audio_path, t=scan_duration)
            .output(scan_path, acodec="pcm_s16le", ar=24000, ac=1)
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as e:
        stderr = e.stderr.decode() if e.stderr else "unknown"
        raise RuntimeError(f"Failed to scan audio: {stderr}") from e

    with wave_module.open(scan_path, "rb") as wf:
        sr = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)

    window = int(duration * sr)
    step = int(sr)
    silence_threshold = 500.0  # below this RMS per frame = silence
    best_start = 0
    best_score = -1.0

    for start in range(0, max(1, len(samples) - window), step):
        chunk = samples[start: start + window]
        frame_size = int(0.02 * sr)  # 20ms frames
        frames = [chunk[i:i+frame_size] for i in range(0, len(chunk), frame_size) if len(chunk[i:i+frame_size]) == frame_size]
        speech_frames = sum(1 for f in frames if np.sqrt(np.mean(f**2)) > silence_threshold)
        speech_ratio = speech_frames / max(len(frames), 1)
        rms = float(np.sqrt(np.mean(chunk**2)))
        # Score: penalize low speech ratio — need ≥60% speech per research
        score = rms * min(speech_ratio / 0.6, 1.0)
        if score > best_score:
            best_score = score
            best_start = start

    best_start_sec = best_start / sr
    logger.info(f"[{job_id}] Best reference segment at {best_start_sec:.1f}s (score={best_score:.0f})")

    # Extract best segment at 24kHz
    try:
        (
            ffmpeg
            .input(source_audio_path, ss=best_start_sec, t=duration)
            .output(scan_path, acodec="pcm_s16le", ar=24000, ac=1)
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as e:
        stderr = e.stderr.decode() if e.stderr else "unknown"
        raise RuntimeError(f"Failed to extract reference clip: {stderr}") from e

    # Append 0.5s silence to fix "rough start" first-word artifact
    silence_samples = int(0.5 * 24000)
    with wave_module.open(scan_path, "rb") as wf:
        params = wf.getparams()
        audio_frames = wf.readframes(wf.getnframes())

    with wave_module.open(ref_path, "wb") as wf:
        wf.setparams(params)
        wf.writeframes(audio_frames)
        wf.writeframes(struct.pack("<" + "h" * silence_samples, *([0] * silence_samples)))

    logger.info(f"[{job_id}] Reference clip ready: {ref_path} ({duration}s + 0.5s silence)")
    return ref_path, best_start_sec


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
    Gaps are filled with silence. Uses numpy for speed.
    """
    import wave as wave_module
    import numpy as np

    total_samples = int(total_duration * sample_rate)
    track = np.zeros(total_samples, dtype=np.float32)

    for start_time, clip_path in clips:
        start_sample = int(start_time * sample_rate)
        try:
            with wave_module.open(clip_path, "rb") as wf:
                raw = wf.readframes(wf.getnframes())
                clip = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        except Exception as e:
            logger.warning(f"Could not read clip {clip_path}: {e}, skipping")
            continue

        end_sample = min(start_sample + len(clip), total_samples)
        track[start_sample:end_sample] += clip[:end_sample - start_sample]

    out = np.clip(track, -32768, 32767).astype(np.int16)
    with wave_module.open(output_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(out.tobytes())


def _get_audio_duration(path: str) -> float:
    """Get audio duration in seconds using ffprobe."""
    try:
        probe = ffmpeg.probe(path)
        return float(probe["format"]["duration"])
    except Exception as e:
        raise RuntimeError(f"Could not get audio duration for {path}: {e}") from e


def _synthesize_with_indextts(
    segments: list,
    ref_audio_path: str,
    source_audio_path: str,
    job_id: str,
    job_dir: Path,
    progress_callback=None,
) -> str:
    """Synthesize dubbed audio using IndexTTS (index-tts-20) voice cloning."""
    import sys
    import gc
    import torch

    indextts_root = str(Path(settings.indextts_root))
    if indextts_root not in sys.path:
        sys.path.insert(0, indextts_root)

    # Override HF_HUB_CACHE to absolute path BEFORE the module sets it to relative
    import os as _os
    _os.environ["HF_HUB_CACHE"] = str(Path(settings.indextts_root) / "checkpoints" / "hf_cache")

    from indextts.infer import IndexTTS  # type: ignore

    cfg_path = str(Path(settings.indextts_root) / "checkpoints" / "config.yaml")
    model_dir = str(Path(settings.indextts_root) / "checkpoints")

    logger.info(f"[{job_id}] Loading IndexTTS from {model_dir}")
    model = IndexTTS(cfg_path=cfg_path, model_dir=model_dir, is_fp16=True)

    try:
        clips: list[tuple[float, str]] = []
        total = len(segments)
        for i, seg in enumerate(segments):
            start_sec = _srt_time_to_seconds(seg.start)
            clip_path = str(job_dir / f"clip_{i:04d}.wav")
            try:
                model.infer_fast(
                    audio_prompt=ref_audio_path,
                    text=seg.text,
                    output_path=clip_path,
                )
                clips.append((start_sec, clip_path))
            except Exception as seg_err:
                logger.warning(f"[{job_id}] IndexTTS segment {i + 1} failed ({seg_err}), inserting silence")
                _make_silence_wav(clip_path, _srt_time_to_seconds(seg.end) - start_sec)
                clips.append((start_sec, clip_path))

            if progress_callback:
                progress_callback((i + 1) / total, f"IndexTTS segment {i + 1}/{total}")
    finally:
        del model
        torch.cuda.empty_cache()
        gc.collect()
        logger.info(f"[{job_id}] IndexTTS model unloaded")

    dubbed_path = str(job_dir / "dubbed.wav")
    total_duration = _get_audio_duration(source_audio_path)
    _assemble_audio_clips(clips, total_duration, dubbed_path, sample_rate=24000)
    logger.info(f"[{job_id}] IndexTTS assembly complete")
    return dubbed_path


def synthesize_tts(
    translated_srt_path: str,
    source_audio_path: str,
    job_id: str,
    target_lang: str = "zh",
    source_srt_path: str | None = None,
    tts_engine: str = "qwen3",
    progress_callback=None,
) -> str:
    """
    Synthesize dubbed audio using voice cloning.
    tts_engine selects the engine: "qwen3" | "indextts" | "cosyvoice2" | "stub"
    Falls back to stub if the selected engine is unavailable.
    """
    with open(translated_srt_path, encoding="utf-8") as f:
        srt_content = f.read()
    segments = parse_srt(srt_content)

    if not segments:
        raise ValueError(f"No segments found in {translated_srt_path}")

    if USE_STUB_TTS or tts_engine == "stub":
        return _stub_synthesize_tts(segments, source_audio_path, job_id)

    job_dir = Path(settings.storage_path) / job_id
    ref_duration = 12.0
    ref_audio_path, ref_start_sec = extract_reference_clip(source_audio_path, job_id, duration=ref_duration)
    srt_for_ref = source_srt_path or translated_srt_path

    if tts_engine == "indextts":
        try:
            return _synthesize_with_indextts(
                segments, ref_audio_path, source_audio_path, job_id, job_dir, progress_callback,
            )
        except Exception as e:
            logger.warning(f"[{job_id}] IndexTTS failed ({e}), falling back to stub")
            return _stub_synthesize_tts(segments, source_audio_path, job_id)

    if tts_engine == "cosyvoice2":
        try:
            from cosyvoice.cli.cosyvoice import CosyVoice2  # type: ignore
            return _synthesize_with_cosyvoice(segments, ref_audio_path, source_audio_path, job_id, job_dir)
        except ImportError:
            logger.warning(f"[{job_id}] CosyVoice2 not available, falling back to stub")
            return _stub_synthesize_tts(segments, source_audio_path, job_id)

    # Default: qwen3
    try:
        from qwen_tts import Qwen3TTSModel  # type: ignore
        return _synthesize_with_qwen3(
            segments, ref_audio_path, ref_start_sec, ref_duration,
            srt_for_ref, source_audio_path, job_id, job_dir, target_lang,
            progress_callback=progress_callback,
        )
    except ImportError:
        logger.warning(f"[{job_id}] Qwen3-TTS not available, trying CosyVoice2")

    try:
        from cosyvoice.cli.cosyvoice import CosyVoice2  # type: ignore
        return _synthesize_with_cosyvoice(segments, ref_audio_path, source_audio_path, job_id, job_dir)
    except ImportError:
        logger.warning(f"[{job_id}] CosyVoice2 not available, falling back to stub")

    return _stub_synthesize_tts(segments, source_audio_path, job_id)


def _ref_text_from_srt(source_srt_path: str, start_sec: float, duration: float) -> str:
    """
    Extract ref_text from the already-transcribed source SRT for the ref clip window.
    No Whisper re-load needed — reuses the transcription produced by the ASR step.
    """
    end_sec = start_sec + duration
    try:
        with open(source_srt_path, encoding="utf-8") as f:
            content = f.read()
        segments = parse_srt(content)
        words = []
        for seg in segments:
            seg_start = _srt_time_to_seconds(seg.start)
            seg_end = _srt_time_to_seconds(seg.end)
            # Include segment if it overlaps with the ref window
            if seg_start < end_sec and seg_end > start_sec:
                words.append(seg.text.strip())
        text = " ".join(words).strip()
        return text if text else "Hello, this is a reference audio clip."
    except Exception as e:
        logger.warning(f"Could not extract ref_text from SRT ({e}), using placeholder")
        return "Hello, this is a reference audio clip."


def _synthesize_with_qwen3(
    segments: list[Segment],
    ref_audio_path: str,
    ref_start_sec: float,
    ref_duration: float,
    source_srt_path: str,
    source_audio_path: str,
    job_id: str,
    job_dir: Path,
    target_lang: str = "zh",
    progress_callback=None,
) -> str:
    import torch
    import soundfile as sf
    from qwen_tts import Qwen3TTSModel  # type: ignore

    model_path = str(Path("E:/ClaudeProject/AI-video-translate/Qwen3-TTS/Qwen3-TTS-12Hz-1.7B-Base"))

    ref_text = _ref_text_from_srt(source_srt_path, ref_start_sec, ref_duration)
    logger.info(f"[{job_id}] Reference text (from SRT): {ref_text[:80]}")

    logger.info(f"[{job_id}] Loading Qwen3-TTS from {model_path}")
    model = Qwen3TTSModel.from_pretrained(
        model_path,
        device_map=f"{settings.qwen_device}:0",
        dtype=torch.bfloat16,
    )

    try:
        clips: list[tuple[float, str]] = []
        assembly_sr: int = 24000  # Qwen3-TTS native rate; updated from first real output
        lang_map = {"zh": "Chinese", "en": "English", "ja": "Japanese", "ko": "Korean",
                    "de": "German", "fr": "French", "ru": "Russian", "pt": "Portuguese",
                    "es": "Spanish", "it": "Italian"}
        language = lang_map.get(target_lang, "Chinese")
        logger.info(f"[{job_id}] TTS language: {language} ({len(segments)} segments)")

        for i, seg in enumerate(segments):
            start_sec = _srt_time_to_seconds(seg.start)
            end_sec = _srt_time_to_seconds(seg.end)
            seg_duration = max(end_sec - start_sec, 1.0)
            # 12 Hz codec: 2× segment duration + small buffer, capped at 600 (~50s)
            max_tokens = min(int(seg_duration * 2 * 12) + 60, 600)
            clip_path = str(job_dir / f"clip_{i:04d}.wav")
            try:
                # x_vector_only_mode=True: extract speaker timbre only, no English audio
                # codes in context — required for cross-lingual cloning (EN ref → ZH output).
                # ICL mode (False) bleeds English phoneme tokens into Chinese generation.
                wavs, sr = model.generate_voice_clone(
                    text=seg.text,
                    language=language,
                    ref_audio=ref_audio_path,
                    x_vector_only_mode=True,
                    max_new_tokens=max_tokens,
                )
                # Force 16-bit PCM so wave.open() in assembly reads samples correctly
                sf.write(clip_path, wavs[0], sr, subtype="PCM_16")
                assembly_sr = int(sr)
                clips.append((start_sec, clip_path))
                logger.info(f"[{job_id}] Segment {i+1}/{len(segments)}: {seg.text[:40]!r}")
            except Exception as seg_err:
                logger.warning(f"[{job_id}] Segment {i+1} failed ({seg_err}), inserting silence")
                _make_silence_wav(clip_path, _srt_time_to_seconds(seg.end) - start_sec)
                clips.append((start_sec, clip_path))

            if progress_callback:
                progress_callback((i + 1) / len(segments), f"Qwen3-TTS segment {i + 1}/{len(segments)}")
    finally:
        import gc
        del model
        torch.cuda.empty_cache()
        gc.collect()
        logger.info(f"[{job_id}] Qwen3-TTS model unloaded")

    dubbed_path = str(job_dir / "dubbed.wav")
    total_duration = _get_audio_duration(source_audio_path)
    _assemble_audio_clips(clips, total_duration, dubbed_path, sample_rate=assembly_sr)
    logger.info(f"[{job_id}] Assembly complete at {assembly_sr}Hz")
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

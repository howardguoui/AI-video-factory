from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    openai_api_key: str = "ollama"
    redis_url: str = "redis://localhost:6379/0"
    storage_path: str = "./storage"
    # ASR: model selection and compute
    whisper_model_size: str = "large-v3"  # can override to "large-v3-turbo", "distil-medium", etc.
    whisper_device: str = "cuda"
    whisper_compute_type: str = "float16"  # options: int8, float16, float32
    # ASR performance tuning
    whisper_beam_size: int = 1          # 1=fastest, 5=most accurate
    asr_chunk_minutes: int = 10         # split audio into N-minute chunks (sequential, VAD per chunk)
    # Translation via Ollama (OpenAI-compatible API)
    ollama_base_url: str = "http://localhost:11434/v1"
    translation_model: str = "qwen3:8b"  # text model only (not vision); changed from qwen3-vl
    ollama_keep_alive: str = "5m"       # keep model warm in VRAM for this duration
    qwen_device: str = "cuda"
    # TTS stub mode — set to false once Qwen3-TTS or CosyVoice2 is installed
    use_stub_tts: bool = True
    # IndexTTS — root directory of the index-tts-20 project (contains indextts/ package + checkpoints/)
    indextts_root: str = "F:/index-tts-20/index-tts-20"
    # Qwen3-TTS — root directory (contains qwen_tts/ package + Qwen3-TTS-12Hz-1.7B-Base/ weights)
    qwen3_tts_root: str = "F:/Qwen3-TTS"
    log_level: str = "INFO"


settings = Settings()

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    openai_api_key: str = "ollama"
    redis_url: str = "redis://localhost:6379/0"
    storage_path: str = "./storage"
    whisper_model_size: str = "large-v3"
    whisper_device: str = "cuda"
    whisper_compute_type: str = "float16"
    qwen_device: str = "cuda"
    log_level: str = "INFO"
    # Translation via Ollama (OpenAI-compatible API)
    ollama_base_url: str = "http://localhost:11434/v1"
    translation_model: str = "huihui_ai/qwen3-vl-abliterated:8b-instruct"
    # TTS stub mode — set to false once Qwen3-TTS or CosyVoice2 is installed
    use_stub_tts: bool = True


settings = Settings()

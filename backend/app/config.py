from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    openai_api_key: str = ""
    redis_url: str = "redis://localhost:6379/0"
    storage_path: str = "./storage"
    whisper_model_size: str = "large-v3"
    whisper_device: str = "cuda"
    whisper_compute_type: str = "float16"
    qwen_device: str = "cuda"
    log_level: str = "INFO"


settings = Settings()

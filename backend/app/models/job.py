from pydantic import BaseModel


class JobResponse(BaseModel):
    job_id: str
    status: str
    step: int = 0
    step_progress: float = 0.0
    step_detail: str | None = None
    output_path: str | None = None
    error: str | None = None
    target_lang: str = "zh"
    pipeline_mode: str = "dubbing"
    tts_engine: str = "qwen3"
    llm_model: str | None = None
    label: str | None = None
    source_vtt: str | None = None
    translated_vtt: str | None = None
    bilingual_download: str | None = None

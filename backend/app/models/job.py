from pydantic import BaseModel


class JobResponse(BaseModel):
    job_id: str
    status: str
    step: int = 0
    output_path: str | None = None
    error: str | None = None
    target_lang: str = "zh"
    pipeline_mode: str = "dubbing"
    source_vtt: str | None = None
    translated_vtt: str | None = None
    bilingual_download: str | None = None

from pydantic import BaseModel


class JobResponse(BaseModel):
    job_id: str
    status: str
    step: int = 0
    output_path: str | None = None
    error: str | None = None
    target_lang: str = "zh"

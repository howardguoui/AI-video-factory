import os
from pathlib import Path
from app.config import settings


def job_dir(job_id: str) -> Path:
    path = Path(settings.storage_path) / job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def job_file(job_id: str, filename: str) -> str:
    return str(job_dir(job_id) / filename)


def save_upload(job_id: str, content: bytes, filename: str = "input.mp4") -> str:
    path = job_file(job_id, filename)
    with open(path, "wb") as f:
        f.write(content)
    return path


def read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_file(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

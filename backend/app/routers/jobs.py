# Stub — will be fully implemented in Task 3
from fastapi import APIRouter

router = APIRouter()


@router.post("/jobs")
async def create_job():
    return {"message": "stub"}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    return {"job_id": job_id, "status": "stub"}

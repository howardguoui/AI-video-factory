# Shared in-memory job store (avoids circular imports between routers and worker)
job_store: dict[str, dict] = {}


def update_status(
    job_id: str,
    status: str,
    step: int | None = None,
    output_path: str | None = None,
    error: str | None = None,
) -> None:
    if job_id not in job_store:
        job_store[job_id] = {}
    job_store[job_id]["status"] = status
    if step is not None:
        job_store[job_id]["step"] = step
    if output_path is not None:
        job_store[job_id]["output_path"] = output_path
    if error is not None:
        job_store[job_id]["error"] = error

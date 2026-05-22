"""Job history endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from pen_plotter.persistence import JobRecord, get_job, list_jobs

router = APIRouter()


@router.get("/jobs")
async def jobs() -> list[JobRecord]:
    """List recent processed jobs, newest first."""
    return list_jobs()


@router.get("/jobs/{job_id}")
async def job(job_id: str) -> JobRecord:
    """Return a single job record.

    Raises:
        HTTPException: 404 if no job with the id exists.
    """
    record = get_job(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Unknown job: {job_id!r}")
    return record

"""Durable print-queue endpoints: enqueue, list, pause/resume/cancel, delete."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from pen_plotter import queue as q
from pen_plotter.audit import record
from pen_plotter.auth import require_api_key
from pen_plotter.hardware.controller import controller
from pen_plotter.profiles import get_profile

router = APIRouter()

#: Worker bound to the shared controller; started/stopped by the app lifespan.
print_queue = q.PrintQueue(controller)


class EnqueueRequest(BaseModel):
    """Body for adding a run to the print queue."""

    name: str
    profile_name: str
    gcode: str
    priority: int = 0


def _run_or_404(run_id: str) -> q.PrintRun:
    run = q.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Unknown run: {run_id!r}")
    return run


@router.get("/queue", dependencies=[Depends(require_api_key)])
async def list_queue() -> list[q.PrintRun]:
    """List print runs, active ones first.

    Protected because ``PrintRun.pause_points`` carries operator-facing
    prompts (e.g. "Insert pen slot 1: Red") that reveal the pen carousel
    configuration when an API key is configured.
    """
    return q.list_runs()


@router.get("/queue/{run_id}", dependencies=[Depends(require_api_key)])
async def get_one(run_id: str) -> q.PrintRun:
    """Return a single print run.

    Raises:
        HTTPException: 404 if the run is unknown.
    """
    return _run_or_404(run_id)


@router.post("/queue", dependencies=[Depends(require_api_key)])
async def create(
    request: EnqueueRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> q.PrintRun:
    """Enqueue a G-code program for the plotter.

    Supplying an ``Idempotency-Key`` header makes retries safe: if a run already
    exists with that key, it is returned instead of creating a duplicate.

    Raises:
        HTTPException: 404 if the profile is unknown.
    """
    if get_profile(request.profile_name) is None:
        raise HTTPException(status_code=404, detail=f"Unknown profile: {request.profile_name!r}")
    run = q.enqueue(
        request.name,
        request.profile_name,
        request.gcode,
        request.priority,
        idempotency_key=idempotency_key,
    )
    record("queue.enqueue", f"{run.name} ({run.id})")
    print_queue.wake()
    return run


@router.post("/queue/{run_id}/pause", dependencies=[Depends(require_api_key)])
async def pause(run_id: str) -> q.PrintRun:
    """Pause a run that is currently streaming."""
    _run_or_404(run_id)
    return print_queue.pause(run_id) or _run_or_404(run_id)


@router.post("/queue/{run_id}/resume", dependencies=[Depends(require_api_key)])
async def resume(run_id: str) -> q.PrintRun:
    """Resume a paused run, continuing it or re-queuing from its checkpoint."""
    _run_or_404(run_id)
    return print_queue.resume(run_id) or _run_or_404(run_id)


@router.post("/queue/{run_id}/cancel", dependencies=[Depends(require_api_key)])
async def cancel(run_id: str) -> q.PrintRun:
    """Cancel a run, aborting it if it is currently streaming."""
    _run_or_404(run_id)
    record("queue.cancel", run_id)
    return print_queue.cancel(run_id) or _run_or_404(run_id)


@router.delete("/queue/{run_id}", dependencies=[Depends(require_api_key)])
async def remove(run_id: str) -> dict[str, str]:
    """Delete a run from the queue.

    Raises:
        HTTPException: 404 if unknown; 409 if it is currently streaming.
    """
    run = _run_or_404(run_id)
    if run.id == print_queue.current_id:
        raise HTTPException(status_code=409, detail="Cancel the running job before deleting it.")
    q.delete_run(run_id)
    return {"deleted": run_id}

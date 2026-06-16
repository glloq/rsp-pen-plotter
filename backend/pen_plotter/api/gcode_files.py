"""G-code file library endpoints: save, list, rename, delete, print.

A saved G-code program is just stored text the operator can re-print on
demand — saving never starts a print. ``POST /gcode-files/{id}/print``
is the explicit launch: it enqueues the saved program as a run (linked
back to the file via ``gcode_file_id``) and wakes the queue worker.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from pen_plotter import gcode_library as lib
from pen_plotter import queue as q
from pen_plotter.api.queue import PrintRunSummary, _summary, print_queue
from pen_plotter.audit import record
from pen_plotter.auth import require_api_key
from pen_plotter.profiles import get_profile

router = APIRouter()


class GcodeFileSummary(BaseModel):
    """Wire projection of a saved program WITHOUT the G-code payload."""

    id: str
    name: str
    profile_name: str
    line_count: int
    size_bytes: int
    created_at: datetime
    updated_at: datetime


def _file_summary(record_: lib.GcodeFile) -> GcodeFileSummary:
    return GcodeFileSummary(
        id=record_.id,
        name=record_.name,
        profile_name=record_.profile_name,
        line_count=record_.line_count or 0,
        size_bytes=record_.size_bytes or 0,
        created_at=record_.created_at,
        updated_at=record_.updated_at,
    )


class GcodeFileCreate(BaseModel):
    """Body for ``POST /gcode-files`` — save the current program."""

    name: str
    profile_name: str
    gcode: str


class GcodeFilePatch(BaseModel):
    """Body for ``PATCH /gcode-files/{id}`` — rename."""

    name: str


@router.get("/gcode-files", dependencies=[Depends(require_api_key)])
async def list_files() -> list[GcodeFileSummary]:
    """List saved G-code programs, newest first (no payload)."""
    return [_file_summary(r) for r in lib.list_gcode_files()]


@router.post("/gcode-files", dependencies=[Depends(require_api_key)])
async def create_file(body: GcodeFileCreate) -> GcodeFileSummary:
    """Save a G-code program to the library.

    Lenient on the profile (a saved file is just text); the profile is
    validated again when the file is actually printed.

    Raises:
        HTTPException: 422 if the G-code is empty.
    """
    if not body.gcode.strip():
        raise HTTPException(status_code=422, detail="Cannot save an empty G-code program.")
    saved = lib.save_gcode_file(body.name.strip() or "gcode", body.profile_name, body.gcode)
    record("gcode.save", f"{saved.name} ({saved.id})")
    return _file_summary(saved)


@router.patch("/gcode-files/{file_id}", dependencies=[Depends(require_api_key)])
async def rename_file(file_id: str, body: GcodeFilePatch) -> GcodeFileSummary:
    """Rename a saved program.

    Raises:
        HTTPException: 404 if the file is unknown.
    """
    renamed = lib.rename_gcode_file(file_id, body.name.strip() or "gcode")
    if renamed is None:
        raise HTTPException(status_code=404, detail=f"Unknown G-code file: {file_id!r}")
    return _file_summary(renamed)


@router.delete("/gcode-files/{file_id}", dependencies=[Depends(require_api_key)])
async def delete_file(file_id: str) -> dict[str, bool]:
    """Delete a saved program.

    Raises:
        HTTPException: 404 if the file is unknown.
    """
    if not lib.delete_gcode_file(file_id):
        raise HTTPException(status_code=404, detail=f"Unknown G-code file: {file_id!r}")
    return {"deleted": True}


@router.post("/gcode-files/{file_id}/print", dependencies=[Depends(require_api_key)])
async def print_file(file_id: str) -> PrintRunSummary:
    """Launch a saved program: enqueue it as a run and wake the worker.

    Raises:
        HTTPException: 404 if the file or its profile is unknown.
    """
    saved = lib.get_gcode_file(file_id)
    if saved is None:
        raise HTTPException(status_code=404, detail=f"Unknown G-code file: {file_id!r}")
    if get_profile(saved.profile_name) is None:
        raise HTTPException(status_code=404, detail=f"Unknown profile: {saved.profile_name!r}")
    run = q.enqueue(saved.name, saved.profile_name, saved.gcode, gcode_file_id=saved.id)
    record("gcode.print", f"{saved.name} ({run.id})")
    print_queue.wake()
    return _summary(run)

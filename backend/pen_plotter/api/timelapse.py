"""Camera timelapse endpoints: start / stop / status / list / download / delete.

The camera stream URL lives client-side, so ``start`` receives it from the
SPA; the backend (free of browser CORS limits) grabs frames from it and
assembles a downloadable MP4 on stop. A single recording runs at a time.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from pen_plotter import timelapse as tl
from pen_plotter.audit import record

router = APIRouter()


class TimelapseStartRequest(BaseModel):
    """Body for ``POST /timelapse/start``."""

    stream_url: str
    interval_seconds: float = Field(default=5.0, ge=tl.MIN_INTERVAL_S, le=tl.MAX_INTERVAL_S)
    fps: int = Field(default=24, ge=tl.MIN_FPS, le=tl.MAX_FPS)
    label: str = ""


class TimelapseStatus(BaseModel):
    """The active recording (or the idle state)."""

    recording: bool
    session_id: str | None = None
    label: str = ""
    frame_count: int = 0
    interval_seconds: float = 0.0
    fps: int = 0
    started_at: str | None = None
    error: str | None = None


class TimelapseSummary(BaseModel):
    """A saved timelapse's metadata (no frames / payload)."""

    id: str
    label: str
    created_at: str
    interval_seconds: float
    fps: int
    frame_count: int
    duration_seconds: float
    has_video: bool
    size_bytes: int


@router.get("/timelapse/status")
async def status() -> TimelapseStatus:
    """Return the current recording status."""
    return TimelapseStatus(**tl.recorder.status())


@router.post("/timelapse/start")
async def start(body: TimelapseStartRequest) -> TimelapseStatus:
    """Begin capturing frames from the given camera stream URL.

    Raises:
        HTTPException: 422 on a non-http(s) URL, 409 if already recording.
    """
    url = body.stream_url.strip()
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="A http(s) camera stream URL is required.")
    try:
        state = await tl.recorder.start(url, body.interval_seconds, body.fps, body.label)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    record("timelapse.start", state.get("session_id") or "")
    return TimelapseStatus(**state)


@router.post("/timelapse/stop")
async def stop() -> TimelapseSummary:
    """Stop recording, assemble the MP4, and return the saved summary.

    Raises:
        HTTPException: 409 if no recording is in progress.
    """
    try:
        summary = await tl.recorder.stop()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    record("timelapse.stop", f"{summary['id']} ({summary['frame_count']} frames)")
    return TimelapseSummary(**summary)


@router.get("/timelapse")
async def list_all() -> list[TimelapseSummary]:
    """List saved timelapses, newest first."""
    return [TimelapseSummary(**m) for m in tl.recorder.list()]


@router.get("/timelapse/{timelapse_id}/video")
async def download_video(timelapse_id: str) -> FileResponse:
    """Download a timelapse's MP4.

    Raises:
        HTTPException: 404 if the timelapse has no assembled video.
    """
    path = tl.recorder.video_path(timelapse_id)
    if path is None:
        raise HTTPException(status_code=404, detail=f"No video for timelapse {timelapse_id!r}")
    meta = tl.recorder.get(timelapse_id) or {}
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(meta.get("label") or timelapse_id)).strip("_")
    filename = f"timelapse-{safe or timelapse_id}.mp4"
    return FileResponse(path, media_type="video/mp4", filename=filename)


@router.delete("/timelapse/{timelapse_id}")
async def delete(timelapse_id: str) -> dict[str, bool]:
    """Delete a saved timelapse (the active recording cannot be deleted).

    Raises:
        HTTPException: 404 if unknown or currently recording.
    """
    if not tl.recorder.delete(timelapse_id):
        raise HTTPException(
            status_code=404, detail=f"Unknown or active timelapse: {timelapse_id!r}"
        )
    return {"deleted": True}

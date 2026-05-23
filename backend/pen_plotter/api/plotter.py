"""Plotter connection and control endpoints (REST + WebSocket)."""

from __future__ import annotations

import contextlib
import os
from typing import Literal

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from pen_plotter.audit import record
from pen_plotter.auth import API_KEY_ENV
from pen_plotter.hardware.controller import controller
from pen_plotter.models import MachineProfile
from pen_plotter.profiles import get_profile

router = APIRouter()


_TERMINATORS = {"cr": "\r", "lf": "\n", "crlf": "\r\n"}


class ConnectRequest(BaseModel):
    """Serial connection parameters."""

    port: str
    baudrate: int = 115200
    terminator: Literal["cr", "lf", "crlf"] = "lf"


class JogRequest(BaseModel):
    """Relative jog parameters."""

    dx_mm: float
    dy_mm: float
    profile_name: str


class GotoRequest(BaseModel):
    """Absolute move parameters."""

    x_mm: float
    y_mm: float
    profile_name: str


class RunRequest(BaseModel):
    """G-code job to stream."""

    gcode: str


class StatusResponse(BaseModel):
    """Connection and streaming status."""

    connected: bool
    total: int
    sent: int
    acked: int
    state: str
    message: str | None = None


def _status() -> StatusResponse:
    """Build a status snapshot from the controller."""
    p = controller.progress
    return StatusResponse(
        connected=controller.connected,
        total=p.total,
        sent=p.sent,
        acked=p.acked,
        state=p.state.value,
        message=p.message,
    )


def _profile_or_404(name: str) -> MachineProfile:
    profile = get_profile(name)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Unknown profile: {name!r}")
    return profile


@router.get("/plotter/status")
async def status() -> StatusResponse:
    """Return the current connection and streaming status."""
    return _status()


@router.post("/plotter/connect")
async def connect(request: ConnectRequest) -> StatusResponse:
    """Open a serial connection to the plotter.

    Raises:
        HTTPException: 400 if the serial port cannot be opened.
    """
    try:
        await controller.open_serial(
            request.port, request.baudrate, _TERMINATORS[request.terminator]
        )
    except Exception as exc:  # hardware/serial errors
        raise HTTPException(status_code=400, detail=f"Could not connect: {exc}") from exc
    record("plotter.connect", f"{request.port} @ {request.baudrate}")
    return _status()


@router.post("/plotter/disconnect")
async def disconnect() -> StatusResponse:
    """Disconnect from the plotter."""
    await controller.disconnect()
    record("plotter.disconnect")
    return _status()


@router.post("/plotter/jog")
async def jog(request: JogRequest) -> StatusResponse:
    """Jog the head by a relative offset."""
    profile = _profile_or_404(request.profile_name)
    try:
        await controller.jog(request.dx_mm, request.dy_mm, profile)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _status()


@router.post("/plotter/goto")
async def goto(request: GotoRequest) -> StatusResponse:
    """Move the head to an absolute workspace position."""
    profile = _profile_or_404(request.profile_name)
    try:
        await controller.goto(request.x_mm, request.y_mm, profile)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _status()


@router.post("/plotter/home")
async def home(profile_name: str) -> StatusResponse:
    """Home the machine."""
    profile = _profile_or_404(profile_name)
    try:
        await controller.home(profile)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    record("plotter.home", profile_name)
    return _status()


@router.post("/plotter/run")
async def run(request: RunRequest) -> StatusResponse:
    """Start streaming a G-code job."""
    try:
        await controller.run(request.gcode)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    record("plotter.run", f"{request.gcode.count(chr(10)) + 1} lines")
    return _status()


@router.post("/plotter/pause")
async def pause() -> StatusResponse:
    """Pause the running job."""
    controller.pause()
    record("plotter.pause")
    return _status()


@router.post("/plotter/resume")
async def resume() -> StatusResponse:
    """Resume a paused job."""
    controller.resume()
    record("plotter.resume")
    return _status()


@router.post("/plotter/abort")
async def abort() -> StatusResponse:
    """Abort the running job."""
    controller.abort()
    record("plotter.abort")
    return _status()


@router.websocket("/ws/plotter")
async def plotter_ws(websocket: WebSocket) -> None:
    """Push streaming progress to a connected client until it disconnects.

    FastAPI router-level ``Depends(require_api_key)`` does not apply to
    WebSocket routes, so this handler validates the optional API key itself
    from the ``token`` query parameter (the only auth channel browsers can
    use on a WebSocket).
    """
    expected = os.environ.get(API_KEY_ENV)
    if expected:
        token = websocket.query_params.get("token")
        if token != expected:
            await websocket.close(code=1008, reason="Invalid or missing API key.")
            return
    await websocket.accept()
    queue = controller.subscribe()
    try:
        await websocket.send_json(_status().model_dump())
        while True:
            progress = await queue.get()
            await websocket.send_json(
                {
                    "connected": controller.connected,
                    "total": progress.total,
                    "sent": progress.sent,
                    "acked": progress.acked,
                    "state": progress.state.value,
                    "message": progress.message,
                }
            )
    except WebSocketDisconnect:
        pass
    finally:
        controller.unsubscribe(queue)
        with contextlib.suppress(Exception):
            await websocket.close()

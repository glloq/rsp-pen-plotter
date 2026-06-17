"""Plotter connection and control endpoints (REST + WebSocket)."""

from __future__ import annotations

import contextlib
import os
import secrets
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
    # Optional relative Z displacement for a motorised Z axis. Defaults to 0
    # so existing X/Y-only callers are unaffected.
    dz_mm: float = 0.0
    profile_name: str


class GotoRequest(BaseModel):
    """Absolute move parameters."""

    x_mm: float
    y_mm: float
    profile_name: str


class RunRequest(BaseModel):
    """G-code job to stream.

    ``profile_name`` is optional for backward compatibility, but supplying
    it lets the controller compute guided tool-change pauses (matching
    the print queue's behaviour) so a manual run on a multi-pen profile
    still halts at swap boundaries instead of blindly executing the
    firmware pause.
    """

    gcode: str
    profile_name: str | None = None


class StatusResponse(BaseModel):
    """Connection and streaming status."""

    connected: bool
    total: int
    sent: int
    acked: int
    state: str
    message: str | None = None


class CommandsResponse(BaseModel):
    """Recent G-code lines written to the device, oldest first."""

    commands: list[str]


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


@router.get("/plotter/commands")
async def commands() -> CommandsResponse:
    """Return the rolling history of G-code lines sent to the plotter."""
    return CommandsResponse(commands=controller.command_log)


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
        await controller.jog(request.dx_mm, request.dy_mm, profile, dz_mm=request.dz_mm)
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
async def home(profile_name: str, axis: str | None = None) -> StatusResponse:
    """Home the machine — all axes, or a single ``axis`` (X / Y / Z)."""
    profile = _profile_or_404(profile_name)
    normalized = axis.strip().upper() if axis else None
    if normalized is not None and normalized not in ("X", "Y", "Z"):
        raise HTTPException(status_code=422, detail=f"Invalid axis: {axis!r}")
    try:
        await controller.home(profile, normalized)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    record("plotter.home", f"{profile_name} axis={normalized or 'all'}")
    return _status()


@router.post("/plotter/run")
async def run(request: RunRequest) -> StatusResponse:
    """Start streaming a G-code job."""
    profile = _profile_or_404(request.profile_name) if request.profile_name else None
    try:
        await controller.run(request.gcode, profile=profile)
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


@router.post("/plotter/emergency_stop")
async def emergency_stop(profile_name: str | None = None) -> StatusResponse:
    """Send a real-time stop to the controller, preempting any in-flight move.

    Unlike ``/abort`` which waits for the current ``ok``, this writes the
    dialect-appropriate emergency payload (GRBL ``0x18``, Marlin ``M112``,
    EBB ``ES``) straight to the serial line and cancels the streaming
    task. Pass ``profile_name`` to pick the right dialect — defaults to
    GRBL when omitted.
    """
    profile = _profile_or_404(profile_name) if profile_name else None
    await controller.emergency_stop(profile)
    record("plotter.emergency_stop", profile_name or "grbl")
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
        token = websocket.query_params.get("token") or ""
        if not secrets.compare_digest(expected, token):
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

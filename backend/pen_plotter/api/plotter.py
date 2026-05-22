"""Plotter connection and control endpoints (REST + WebSocket)."""

from __future__ import annotations

import contextlib
from typing import Literal

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from pen_plotter.hardware.controller import controller
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


def _status() -> StatusResponse:
    """Build a status snapshot from the controller."""
    p = controller.progress
    return StatusResponse(
        connected=controller.connected,
        total=p.total,
        sent=p.sent,
        acked=p.acked,
        state=p.state.value,
    )


def _profile_or_404(name: str):  # type: ignore[no-untyped-def]
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
    return _status()


@router.post("/plotter/disconnect")
async def disconnect() -> StatusResponse:
    """Disconnect from the plotter."""
    await controller.disconnect()
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


@router.post("/plotter/home")
async def home(profile_name: str) -> StatusResponse:
    """Home the machine."""
    profile = _profile_or_404(profile_name)
    try:
        await controller.home(profile)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _status()


@router.post("/plotter/run")
async def run(request: RunRequest) -> StatusResponse:
    """Start streaming a G-code job."""
    try:
        await controller.run(request.gcode)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _status()


@router.post("/plotter/pause")
async def pause() -> StatusResponse:
    """Pause the running job."""
    controller.pause()
    return _status()


@router.post("/plotter/resume")
async def resume() -> StatusResponse:
    """Resume a paused job."""
    controller.resume()
    return _status()


@router.post("/plotter/abort")
async def abort() -> StatusResponse:
    """Abort the running job."""
    controller.abort()
    return _status()


@router.websocket("/ws/plotter")
async def plotter_ws(websocket: WebSocket) -> None:
    """Push streaming progress to a connected client until it disconnects."""
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
                }
            )
    except WebSocketDisconnect:
        pass
    finally:
        controller.unsubscribe(queue)
        with contextlib.suppress(Exception):
            await websocket.close()

"""Camera-assisted pen-tip offset measurement (ADR 0005, phase 2).

Endpoints that drive the dedicated measurement station: take one frame for
a presented pen, locate its tip, and report the XY offset it implies relative
to the reference pen. Persisting the offset onto the profile stays with the
existing ``POST /profiles`` path (the magazine editor already owns that), so
these endpoints are side-effect-free except for the in-memory session that
remembers measurements within a calibration run.

The frame grabber and detector are injected into the module-level
:class:`~pen_plotter.vision.tip_detect.TipCalibrator`, so tests exercise the
whole flow with a fake camera.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from pen_plotter.audit import record
from pen_plotter.hardware.controller import controller
from pen_plotter.models import MachineProfile, Point, TipCameraRoi
from pen_plotter.profiles import get_profile
from pen_plotter.timelapse import grab_jpeg
from pen_plotter.vision.tip_detect import Roi, TipCalibrator

router = APIRouter()

# One calibration session per appliance, mirroring the timelapse recorder.
_calibrator = TipCalibrator(grabber=grab_jpeg)


class TipMeasureRequest(BaseModel):
    """Body for ``POST /plotter/tip-calibration/measure``.

    Carries the station config inline (the SPA reads it from the active
    profile) so the backend stays free of profile lookups.
    """

    slot: int = Field(ge=0)
    camera_url: str
    mm_per_pixel: float = Field(gt=0.0)
    reference_slot: int = Field(default=0, ge=0)
    dark_threshold: int = Field(default=80, ge=0, le=255)
    roi: TipCameraRoi | None = None
    # Optional guided travel: when ``move_to_station`` is set, the head is
    # moved to ``station_position`` (machine mm) before the frame is grabbed,
    # so the operator need not jog by hand. Requires a connected plotter and
    # ``profile_name`` (for the dialect / transform). Omit to measure whatever
    # is currently presented.
    move_to_station: bool = False
    station_position: Point | None = None
    # Optional absolute Z (machine mm) for the station move, for machines with
    # a real Z axis. ``None`` leaves Z untouched.
    station_z_mm: float | None = None
    profile_name: str | None = None
    # Optional automatic pen-fetch: load this slot's pen via a tool-change
    # swap (host-macro / firmware profiles) before measuring. Manual-swap
    # profiles can't fetch on their own → 409. Runs before move_to_station.
    fetch_pen: bool = False
    # Optional camera lighting: when ``light`` is set and a ``light_on_command``
    # is given, the light is switched on around the measurement and off again
    # afterwards. Needs a connected plotter (the light is driven by the
    # controller).
    light: bool = False
    light_on_command: str | None = None
    light_off_command: str | None = None


class TipMeasureResponse(BaseModel):
    """Result of one measurement plus the offset it implies."""

    found: bool
    slot: int
    is_reference: bool
    tip_px: Point | None = None
    confidence: float = 0.0
    reference_measured: bool = False
    # Offset (mm) of this slot's tip relative to the reference pen — the value
    # to write onto the slot's ``xy_offset_mm``. ``None`` until both this slot
    # and the reference have been measured.
    offset_mm: Point | None = None
    message: str = ""
    # Data URL (``data:image/jpeg;base64,…``) of the frame with the detected
    # tip marked — for the operator to confirm the right blob was picked.
    # ``None`` when the frame couldn't be decoded.
    annotated_image: str | None = None


async def _fetch_pen(profile: MachineProfile, slot: int) -> None:
    """Drive an automatic swap to load ``slot``'s pen before measuring.

    Reuses the tool-change orchestrator: a host-macro / firmware profile
    yields the swap commands, which we send immediately (honouring the
    per-line ``wait_ms`` dwell host-side, exactly as the streamer does for a
    host-timed swap). A *manual* profile can't fetch on its own — the operator
    loads the pen by hand — so that surfaces as a 409.
    """
    from pen_plotter.domain.toolchange.orchestrator import (
        PauseKind,
        SwapContext,
        ToolChangeOrchestrator,
    )

    pen = next((p for p in profile.effective_pens() if p.index == slot), None)
    plan = ToolChangeOrchestrator(profile).plan(
        SwapContext(
            slot_index=slot,
            pen_label=pen.name if pen else "",
            pen_color=pen.color if pen else "",
        )
    )
    if plan.pause_kind == PauseKind.OPERATOR_CONFIRM:
        raise HTTPException(
            status_code=409,
            detail="This profile changes pens manually; load the pen by hand, then measure.",
        )
    try:
        for cmd in plan.commands:
            if cmd.send.strip():
                await controller.send_commands([cmd.send])
            if cmd.wait_ms > 0:
                await asyncio.sleep(cmd.wait_ms / 1000.0)
    except RuntimeError as exc:  # disconnected / job in flight
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    record("tip_calibration_fetch", f"slot={slot} mode={plan.mode.value}")


@router.post("/plotter/tip-calibration/measure")
async def measure(req: TipMeasureRequest) -> TipMeasureResponse:
    """Grab a frame for ``slot`` and locate its tip.

    Optional motion happens first, in order: ``fetch_pen`` loads the slot's
    pen via an automatic swap, then ``move_to_station`` travels the head to
    ``station_position`` (optional Z). Both need a connected plotter +
    ``profile_name``; without them the operator presents the pen by hand. The
    camera light (when ``light``) is on around the grab. Returns the implied
    offset once the reference slot has also been measured this session.
    """
    profile: MachineProfile | None = None
    if req.fetch_pen or req.move_to_station:
        if req.profile_name is None:
            raise HTTPException(
                status_code=422,
                detail="fetch_pen / move_to_station require profile_name",
            )
        profile = get_profile(req.profile_name)
        if profile is None:
            raise HTTPException(status_code=404, detail=f"Unknown profile: {req.profile_name!r}")

    if req.fetch_pen and profile is not None:
        await _fetch_pen(profile, req.slot)

    if req.move_to_station and profile is not None:
        if req.station_position is None:
            raise HTTPException(status_code=422, detail="move_to_station requires station_position")
        try:
            await controller.goto(
                req.station_position.x,
                req.station_position.y,
                profile,
                z_mm=req.station_z_mm,
            )
        except RuntimeError as exc:  # disconnected / job in flight
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    roi = (
        Roi(x=req.roi.x, y=req.roi.y, width=req.roi.width, height=req.roi.height)
        if req.roi
        else None
    )
    light_on = req.light and bool(req.light_on_command and req.light_on_command.strip())
    if light_on:
        try:
            await controller.send_commands([req.light_on_command.strip()])
        except RuntimeError as exc:  # disconnected / job in flight
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        result = _calibrator.measure(
            slot=req.slot,
            reference_slot=req.reference_slot,
            camera_url=req.camera_url,
            mm_per_pixel=req.mm_per_pixel,
            dark_threshold=req.dark_threshold,
            roi=roi,
        )
    except Exception as exc:  # frame grab / decode failure
        raise HTTPException(status_code=502, detail=f"Camera read failed: {exc}") from exc
    finally:
        # Always switch the light back off, even if the grab failed.
        if light_on and req.light_off_command and req.light_off_command.strip():
            with contextlib.suppress(RuntimeError):
                await controller.send_commands([req.light_off_command.strip()])

    m = result.measurement
    record("tip_calibration_measure", f"slot={req.slot} found={m.found} conf={m.confidence:.2f}")
    annotated = (
        "data:image/jpeg;base64," + base64.b64encode(m.annotated_jpeg).decode()
        if m.annotated_jpeg
        else None
    )
    return TipMeasureResponse(
        found=m.found,
        slot=result.slot,
        is_reference=result.is_reference,
        tip_px=Point(x=m.tip_px[0], y=m.tip_px[1]) if m.tip_px else None,
        confidence=m.confidence,
        reference_measured=result.reference_measured,
        offset_mm=(
            Point(x=result.offset_mm[0], y=result.offset_mm[1]) if result.offset_mm else None
        ),
        message=m.message,
        annotated_image=annotated,
    )


class TipCalibrationStatus(BaseModel):
    """Which slots have been measured in the current session."""

    measured_slots: list[int]


@router.get("/plotter/tip-calibration/status")
async def status() -> TipCalibrationStatus:
    """Slots measured so far this calibration run."""
    return TipCalibrationStatus(measured_slots=_calibrator.measured_slots)


@router.post("/plotter/tip-calibration/reset")
async def reset() -> TipCalibrationStatus:
    """Forget all measurements and start a fresh calibration run."""
    _calibrator.reset()
    record("tip_calibration_reset")
    return TipCalibrationStatus(measured_slots=_calibrator.measured_slots)


class LightRequest(BaseModel):
    """Body for ``POST /plotter/tip-calibration/light`` — manual On/Off.

    Sends one raw light command (the SPA passes the profile's
    ``light_on_command`` or ``light_off_command``) so the operator can aim the
    camera with the station lit before running a measurement.
    """

    command: str = Field(min_length=1)
    on: bool = True


@router.post("/plotter/tip-calibration/light")
async def light(req: LightRequest) -> dict[str, bool]:
    """Toggle the station light by sending one raw command to the plotter."""
    try:
        await controller.send_commands([req.command.strip()])
    except RuntimeError as exc:  # disconnected / job in flight
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    record("tip_calibration_light", "on" if req.on else "off")
    return {"on": req.on}

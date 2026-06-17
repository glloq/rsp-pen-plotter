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

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from pen_plotter.audit import record
from pen_plotter.hardware.controller import controller
from pen_plotter.models import Point, TipCameraRoi
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
    profile_name: str | None = None


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


@router.post("/plotter/tip-calibration/measure")
async def measure(req: TipMeasureRequest) -> TipMeasureResponse:
    """Grab a frame for ``slot`` and locate its tip.

    With ``move_to_station`` the head first travels to ``station_position``
    (needs a connected plotter + ``profile_name``); otherwise the operator
    presents the pen by hand. Returns the implied offset once the reference
    slot has also been measured this session.
    """
    if req.move_to_station:
        if req.station_position is None or req.profile_name is None:
            raise HTTPException(
                status_code=422,
                detail="move_to_station requires station_position and profile_name",
            )
        profile = get_profile(req.profile_name)
        if profile is None:
            raise HTTPException(status_code=404, detail=f"Unknown profile: {req.profile_name!r}")
        try:
            await controller.goto(req.station_position.x, req.station_position.y, profile)
        except RuntimeError as exc:  # disconnected / job in flight
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    roi = (
        Roi(x=req.roi.x, y=req.roi.y, width=req.roi.width, height=req.roi.height)
        if req.roi
        else None
    )
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

    m = result.measurement
    record("tip_calibration_measure", f"slot={req.slot} found={m.found} conf={m.confidence:.2f}")
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

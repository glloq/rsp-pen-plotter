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
import threading
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from pen_plotter.audit import record
from pen_plotter.hardware.controller import controller
from pen_plotter.hardware.gpio import AVAILABLE_GPIO_PINS
from pen_plotter.hardware.gpio import light as gpio_light
from pen_plotter.models import MachineProfile, Point, TipCameraRoi
from pen_plotter.profiles import get_profile
from pen_plotter.timelapse import CameraUrlError, grab_jpeg
from pen_plotter.vision.tip_detect import (
    Roi,
    ScaleMeasurement,
    TipCalibrator,
    detect_object_extent,
)

router = APIRouter()

# One calibration session per appliance, mirroring the timelapse recorder.
_calibrator = TipCalibrator(grabber=grab_jpeg)

# ``measure``/``grab``/``detect_object_extent`` do synchronous HTTP reads plus
# NumPy image work — a measurement averages up to 20 frames, each with a 5 s
# camera timeout, so an unreachable camera could otherwise block the event
# loop for ~100 s and stall every other route (including an emergency stop).
# All three run in a worker thread via ``asyncio.to_thread`` so the loop stays
# free, and ``_CALIBRATION_TIMEOUT_S`` bounds the wait the client sees.
_CALIBRATION_TIMEOUT_S = 120.0

# Serialise calibrations: they share the injected camera / GPIO light and the
# in-memory measurement session, so two at once would interleave frames and
# corrupt the reference. Rebuilt on loop change so a second TestClient (new
# event loop) doesn't await a lock bound to the previous loop.
_calibration_lock: asyncio.Lock | None = None
_calibration_lock_loop: asyncio.AbstractEventLoop | None = None


def _get_calibration_lock() -> asyncio.Lock:
    """Return the per-loop calibration lock, (re)creating it on loop change."""
    global _calibration_lock, _calibration_lock_loop
    loop = asyncio.get_running_loop()
    if _calibration_lock is None or _calibration_lock_loop is not loop:
        _calibration_lock = asyncio.Lock()
        _calibration_lock_loop = loop
    return _calibration_lock


def calibration_in_progress() -> bool:
    """True if a tip/scale calibration currently holds the mechanical lock.

    Reads the last-created lock directly (no running loop required) so callers
    like the self-update guard can check it from any context.
    """
    return _calibration_lock is not None and _calibration_lock.locked()


class TipMeasureRequest(BaseModel):
    """Body for ``POST /plotter/tip-calibration/measure``.

    Carries the station config inline (the SPA reads it from the active
    profile) so the backend stays free of profile lookups.
    """

    slot: int = Field(ge=0)
    camera_url: str
    mm_per_pixel: float = Field(gt=0.0)
    reference_slot: int = Field(default=0, ge=0)
    # "dark" tip on a light background (default) or "light" tip on a dark
    # background — the latter inverts the luminance before thresholding.
    tip_style: Literal["dark", "light"] = "dark"
    dark_threshold: int = Field(default=80, ge=0, le=255)
    # Number of frames to grab and average per measurement (noise reduction).
    samples: int = Field(default=1, ge=1, le=20)
    roi: TipCameraRoi | None = None
    # Dry run: detect and report, but do NOT remember the result as this
    # slot's tip. Used by the UI's "Test detection" so tuning lighting /
    # threshold can't silently overwrite the session's reference measurement.
    dry_run: bool = False
    # Detections below this confidence are reported but never stored in the
    # session, so an untrusted reference can't silently become the baseline
    # later offsets are computed against. 0 keeps the permissive behaviour.
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
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
    # Optional camera lighting via a Pi GPIO pin: when ``light`` is set and a
    # ``light_gpio_pin`` is given, the host switches the light on around the
    # measurement and off again. Independent of the plotter connection.
    light: bool = False
    light_gpio_pin: int | None = Field(default=None, ge=0, le=27)
    light_active_high: bool = True


class TipMeasureResponse(BaseModel):
    """Result of one measurement plus the offset it implies."""

    found: bool
    slot: int
    is_reference: bool
    tip_px: Point | None = None
    confidence: float = 0.0
    # Repeatability across averaged frames (mm): how far the farthest sample
    # sat from the aggregated tip. 0 for a single frame; large ⇒ unstable.
    spread_mm: float | None = None
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

    roi = (
        Roi(x=req.roi.x, y=req.roi.y, width=req.roi.width, height=req.roi.height)
        if req.roi
        else None
    )
    light_pin = req.light_gpio_pin if req.light else None

    # Serialise the ENTIRE physical transaction — pen fetch, head travel,
    # lighting and the measurement itself — under one lock (P0.2). The lock
    # used to cover only the grab, so two concurrent calibrations could
    # interleave (A loads slot 1, B loads slot 2, A measures and stores the
    # result as slot 1) and mis-attribute a measurement, or one request's
    # ``finally`` could kill the light mid-measurement for the other. Refuse
    # a second calibration outright rather than silently queueing behind the
    # first, so the operator gets immediate feedback.
    lock = _get_calibration_lock()
    if lock.locked():
        raise HTTPException(status_code=409, detail="A calibration is already in progress.")
    async with lock:
        if req.fetch_pen and profile is not None:
            await _fetch_pen(profile, req.slot)

        if req.move_to_station and profile is not None:
            if req.station_position is None:
                raise HTTPException(
                    status_code=422, detail="move_to_station requires station_position"
                )
            try:
                await controller.goto(
                    req.station_position.x,
                    req.station_position.y,
                    profile,
                    z_mm=req.station_z_mm,
                )
            except RuntimeError as exc:  # disconnected / job in flight
                raise HTTPException(status_code=409, detail=str(exc)) from exc

        if light_pin is not None:
            try:
                gpio_light.set(light_pin, True, req.light_active_high)
            except RuntimeError as exc:  # no GPIO backend on this host
                raise HTTPException(status_code=503, detail=str(exc)) from exc
        cancel_event = threading.Event()
        measure_task = asyncio.create_task(
            asyncio.to_thread(
                _calibrator.measure,
                slot=req.slot,
                reference_slot=req.reference_slot,
                camera_url=req.camera_url,
                mm_per_pixel=req.mm_per_pixel,
                dark_threshold=req.dark_threshold,
                roi=roi,
                samples=req.samples,
                invert=req.tip_style == "light",
                store=not req.dry_run,
                min_confidence=req.min_confidence,
                cancel_event=cancel_event,
            )
        )
        try:
            # ``shield`` so the timeout cancels only our wait, not the worker —
            # a thread can't be killed, so on timeout we ask it to stop and then
            # DRAIN it (below) before releasing the lock / light, so the next
            # calibration can never touch the camera or head while this worker
            # is still reading them (P0.2).
            result = await asyncio.wait_for(
                asyncio.shield(measure_task), timeout=_CALIBRATION_TIMEOUT_S
            )
        except TimeoutError as exc:
            cancel_event.set()  # cooperative stop between samples
            _calibrator.invalidate()  # discard any late store from this worker
            with contextlib.suppress(Exception):
                await measure_task  # wait for the thread to actually finish
            raise HTTPException(status_code=504, detail="Camera measurement timed out.") from exc
        except CameraUrlError as exc:  # SSRF guard rejected the URL — client error
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # frame grab / decode failure
            raise HTTPException(status_code=502, detail=f"Camera read failed: {exc}") from exc
        finally:
            # Always switch the light back off, even if the grab failed — but
            # only after the worker has drained (the drain above completes
            # before this runs on the timeout path), so the light stays on
            # while the camera is still being read.
            if light_pin is not None:
                with contextlib.suppress(RuntimeError):
                    gpio_light.set(light_pin, False, req.light_active_high)

    m = result.measurement
    record(
        "tip_calibration_measure",
        f"slot={req.slot} found={m.found} conf={m.confidence:.2f}"
        + (" dry_run" if req.dry_run else ""),
    )
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
        spread_mm=m.spread_mm,
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


class ScaleCalibrateRequest(BaseModel):
    """Body for ``POST /plotter/tip-calibration/calibrate-scale``.

    The operator presents a target of known physical size at the station; the
    detector measures its pixel extent and we derive ``mm_per_pixel``.
    """

    camera_url: str
    known_mm: float = Field(gt=0.0)
    # Same contrast convention as the tip measurement: a dark target on a
    # light background, or (with "light") a light target on a dark one.
    tip_style: Literal["dark", "light"] = "dark"
    dark_threshold: int = Field(default=80, ge=0, le=255)
    roi: TipCameraRoi | None = None


class ScaleCalibrateResponse(BaseModel):
    """Derived scale plus the measured extent and an annotated preview."""

    found: bool
    mm_per_pixel: float | None = None
    width_px: float | None = None
    height_px: float | None = None
    annotated_image: str | None = None
    message: str = ""


@router.post("/plotter/tip-calibration/calibrate-scale")
async def calibrate_scale(req: ScaleCalibrateRequest) -> ScaleCalibrateResponse:
    """Derive ``mm_per_pixel`` from a known-size target in the frame.

    Uses the target's longest visible edge (max of width/height in pixels) so a
    square or round target of side/diameter ``known_mm`` gives a robust scale.
    """
    roi = (
        Roi(x=req.roi.x, y=req.roi.y, width=req.roi.width, height=req.roi.height)
        if req.roi
        else None
    )
    def _grab_and_measure() -> ScaleMeasurement:
        # Both the HTTP grab and the NumPy extent detection are blocking;
        # run them together in one worker so the event loop never stalls on
        # an unreachable camera (P0.1) — an emergency stop must stay reactive.
        frame = _calibrator.grab(req.camera_url)
        return detect_object_extent(
            frame, req.dark_threshold, roi, invert=req.tip_style == "light"
        )

    # Shares the camera + lock with ``measure`` (P0.2): refuse if a
    # calibration is already running rather than interleaving frame grabs.
    lock = _get_calibration_lock()
    if lock.locked():
        raise HTTPException(status_code=409, detail="A calibration is already in progress.")
    async with lock:
        # Same drain-on-timeout as ``measure`` (P1.1): the worker thread can't
        # be killed, so on timeout we shield + await it to completion before
        # releasing the lock, so a fresh calibration can't grab the camera
        # while this grab is still in flight.
        scale_task = asyncio.create_task(asyncio.to_thread(_grab_and_measure))
        try:
            m = await asyncio.wait_for(
                asyncio.shield(scale_task), timeout=_CALIBRATION_TIMEOUT_S
            )
        except TimeoutError as exc:
            with contextlib.suppress(Exception):
                await scale_task  # drain before releasing the lock
            raise HTTPException(
                status_code=504, detail="Camera measurement timed out."
            ) from exc
        except CameraUrlError as exc:  # SSRF guard rejected the URL — client error
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # frame grab failure
            raise HTTPException(status_code=502, detail=f"Camera read failed: {exc}") from exc
    annotated = (
        "data:image/jpeg;base64," + base64.b64encode(m.annotated_jpeg).decode()
        if m.annotated_jpeg
        else None
    )
    if not m.found or not m.width_px or not m.height_px:
        return ScaleCalibrateResponse(found=False, annotated_image=annotated, message=m.message)

    extent = max(m.width_px, m.height_px)
    mm_per_pixel = req.known_mm / extent
    record("tip_calibration_scale", f"known={req.known_mm}mm extent={extent:.1f}px")
    return ScaleCalibrateResponse(
        found=True,
        mm_per_pixel=mm_per_pixel,
        width_px=m.width_px,
        height_px=m.height_px,
        annotated_image=annotated,
        message="ok",
    )


class GpioInfo(BaseModel):
    """Whether host GPIO is available + the pins the UI can offer."""

    available: bool
    pins: list[int]


@router.get("/plotter/tip-calibration/gpio")
async def gpio() -> GpioInfo:
    """List selectable GPIO pins and whether GPIO control works on this host."""
    return GpioInfo(available=gpio_light.available, pins=list(AVAILABLE_GPIO_PINS))


class LightRequest(BaseModel):
    """Body for ``POST /plotter/tip-calibration/light`` — manual On/Off.

    Drives the chosen Pi GPIO pin so the operator can light the station to aim
    the camera before measuring.
    """

    pin: int = Field(ge=0, le=27)
    on: bool = True
    active_high: bool = True


@router.post("/plotter/tip-calibration/light")
async def light(req: LightRequest) -> dict[str, bool]:
    """Switch the station light on/off via its GPIO pin."""
    try:
        gpio_light.set(req.pin, req.on, req.active_high)
    except RuntimeError as exc:  # no GPIO backend on this host
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    record("tip_calibration_light", f"pin={req.pin} {'on' if req.on else 'off'}")
    return {"on": req.on}

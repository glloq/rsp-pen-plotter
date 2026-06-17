"""Pen-tip detection for camera-assisted offset calibration (ADR 0005, phase 2).

A pen is presented to a fixed measurement *station* — a camera looking at a
small, evenly-lit, high-contrast spot. This module locates the tip in the
frame and converts its position to millimetres, so the per-pen XY offset can
be measured instead of typed by hand.

Design choices that keep this testable and dependency-light:

- **No OpenCV.** The default ``dark_blob`` detector uses Pillow + NumPy
  (both already dependencies). The pen tip is the darkest compact region
  against the light station background; we threshold and take the centroid.
  A future ``aruco`` detector (printed fiducial, sub-pixel) would need
  OpenCV and slots in behind the same :class:`TipMeasurement` contract.
- **Relative, not absolute.** A measurement yields the tip position in mm
  *in the frame's own coordinates*. The actual offset between two pens is the
  difference of their measurements (:func:`offset_between`), so the arbitrary
  choice of frame origin cancels out and no station-to-bed registration is
  needed.
- **Injectable.** Detection and frame-grabbing are plain callables, so the
  API layer and tests can swap in fakes with no camera and no plotter.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from PIL import Image

# A frame grabber maps a camera URL to JPEG bytes (see ``timelapse.grab_jpeg``).
FrameGrabber = Callable[[str], bytes]


@dataclass(frozen=True)
class Roi:
    """Region of interest in pixels: where in the frame the tip will appear."""

    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class TipMeasurement:
    """Result of locating a pen tip in one frame.

    ``tip_mm`` is relative to the frame's top-left in millimetres (x right,
    y down). Only the *difference* between two measurements is meaningful as
    an offset, so the origin choice is irrelevant — see :func:`offset_between`.
    """

    found: bool
    tip_px: tuple[float, float] | None = None
    tip_mm: tuple[float, float] | None = None
    confidence: float = 0.0
    message: str = ""


# A detector maps (frame bytes, mm/pixel, threshold, ROI) to a measurement.
TipDetector = Callable[[bytes, float, int, Roi | None], TipMeasurement]


def offset_between(pen: TipMeasurement, reference: TipMeasurement) -> tuple[float, float] | None:
    """XY offset (mm) of ``pen`` relative to ``reference``.

    ``None`` unless both measurements found a tip. This is the value written
    to a slot's ``xy_offset_mm``: how far this pen's tip sits from the
    reference pen's, which is exactly the translation the generator must add
    to this pen's strokes to make them register.
    """
    if not (pen.found and reference.found and pen.tip_mm and reference.tip_mm):
        return None
    return (pen.tip_mm[0] - reference.tip_mm[0], pen.tip_mm[1] - reference.tip_mm[1])


def _decode_gray(frame: bytes) -> np.ndarray:
    """Decode JPEG/PNG bytes to a 2-D uint8 luminance array."""
    with Image.open(io.BytesIO(frame)) as img:
        return np.asarray(img.convert("L"), dtype=np.uint8)


def detect_tip_dark_blob(
    frame: bytes,
    mm_per_pixel: float,
    dark_threshold: int = 80,
    roi: Roi | None = None,
) -> TipMeasurement:
    """Locate the pen tip as the darkest compact blob in the frame.

    The station presents a dark tip on a light, evenly-lit background. Pixels
    below ``dark_threshold`` are taken as "tip"; the centroid of that mask is
    the tip position. ``confidence`` reflects how much of the (ROI-cropped)
    frame the blob covers — a sane blob is a small fraction; nothing, or
    almost everything (a mis-lit frame), reads as low confidence.

    Coordinates are returned in **full-frame** pixels (the ROI offset is added
    back), so callers can overlay the marker on the original image.
    """
    if mm_per_pixel <= 0:
        return TipMeasurement(found=False, message="mm_per_pixel must be positive")

    gray = _decode_gray(frame)
    off_x, off_y = 0, 0
    if roi is not None:
        x0 = max(0, roi.x)
        y0 = max(0, roi.y)
        x1 = min(gray.shape[1], roi.x + roi.width)
        y1 = min(gray.shape[0], roi.y + roi.height)
        if x1 <= x0 or y1 <= y0:
            return TipMeasurement(found=False, message="ROI is empty or outside the frame")
        gray = gray[y0:y1, x0:x1]
        off_x, off_y = x0, y0

    mask = gray < dark_threshold
    dark = int(mask.sum())
    total = gray.size
    if dark == 0:
        return TipMeasurement(found=False, message="no dark pixels — check lighting / threshold")

    coverage = dark / total
    # A real tip is a small compact blob. If the dark region swamps the frame
    # the threshold/lighting is wrong; report it found but low-confidence so
    # the operator reviews rather than commits a garbage offset.
    if coverage > 0.6:
        return TipMeasurement(
            found=False,
            confidence=0.0,
            message="dark region covers the frame — adjust lighting or threshold",
        )

    ys, xs = np.nonzero(mask)
    cx = float(xs.mean()) + off_x
    cy = float(ys.mean()) + off_y
    # Confidence: peaks for a small, well-defined blob; falls off as the blob
    # vanishes (noise) or grows to fill the frame.
    confidence = float(max(0.0, min(1.0, 1.0 - abs(coverage - 0.02) / 0.3)))

    return TipMeasurement(
        found=True,
        tip_px=(cx, cy),
        tip_mm=(cx * mm_per_pixel, cy * mm_per_pixel),
        confidence=confidence,
        message="ok",
    )


@dataclass
class MeasureResult:
    """One slot's measurement plus the offset it implies (when available)."""

    slot: int
    is_reference: bool
    measurement: TipMeasurement
    reference_measured: bool
    offset_mm: tuple[float, float] | None


class TipCalibrator:
    """Stateful session that measures slots and derives offsets vs a reference.

    Single-host appliance, so one in-memory session is enough (mirrors the
    timelapse recorder). The grabber and detector are injected so the whole
    flow is exercised in tests with no camera.
    """

    def __init__(self, grabber: FrameGrabber, detector: TipDetector = detect_tip_dark_blob) -> None:
        self._grab = grabber
        self._detect = detector
        self._tips: dict[int, TipMeasurement] = {}

    def reset(self) -> None:
        """Forget all measurements (start a fresh calibration run)."""
        self._tips.clear()

    @property
    def measured_slots(self) -> list[int]:
        """Slots measured so far, in ascending order."""
        return sorted(self._tips)

    def measure(
        self,
        *,
        slot: int,
        reference_slot: int,
        camera_url: str,
        mm_per_pixel: float,
        dark_threshold: int = 80,
        roi: Roi | None = None,
    ) -> MeasureResult:
        """Grab a frame for ``slot`` and detect its tip, storing the result.

        Returns the measurement and — once the reference slot has also been
        measured — the offset this slot implies relative to it. Raises
        ``RuntimeError`` only if the frame grab itself fails (propagated from
        the grabber); a frame with no detectable tip is a normal, low/zero
        confidence result, not an error.
        """
        frame = self._grab(camera_url)
        measurement = self._detect(frame, mm_per_pixel, dark_threshold, roi)
        if measurement.found:
            self._tips[slot] = measurement

        reference = self._tips.get(reference_slot)
        offset = None
        if reference is not None:
            offset = offset_between(measurement, reference)
        return MeasureResult(
            slot=slot,
            is_reference=slot == reference_slot,
            measurement=measurement,
            reference_measured=reference is not None,
            offset_mm=offset,
        )

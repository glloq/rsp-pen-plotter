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
from PIL import Image, ImageDraw

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
    # Repeatability across averaged frames (mm): the farthest any contributing
    # sample's tip sat from the aggregated tip. ``0.0`` for a single frame,
    # ``None`` when nothing was found. A large value means the frames disagreed
    # — a sign of an unstable feed / detection.
    spread_mm: float | None = None
    # JPEG of the frame with the detected tip marked (or the plain frame when
    # nothing was found), so the operator can confirm the right blob was
    # picked before trusting the offset. ``None`` when the frame couldn't be
    # decoded (e.g. a config error before any image was read).
    annotated_jpeg: bytes | None = None


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


def _encode_preview(frame: bytes, tip_px: tuple[float, float] | None) -> bytes | None:
    """JPEG preview of ``frame``, with a red marker at ``tip_px`` when given.

    Returns ``None`` if the frame can't be decoded. Re-encodes to JPEG so the
    response content type is consistent regardless of the camera's format.
    """
    try:
        with Image.open(io.BytesIO(frame)) as img:
            rgb = img.convert("RGB")
    except Exception:
        return None
    if tip_px is not None:
        cx, cy = tip_px
        r = max(6, min(rgb.width, rgb.height) // 40)
        draw = ImageDraw.Draw(rgb)
        draw.line([(cx - 2 * r, cy), (cx + 2 * r, cy)], fill=(255, 0, 0), width=2)
        draw.line([(cx, cy - 2 * r), (cx, cy + 2 * r)], fill=(255, 0, 0), width=2)
        draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], outline=(255, 0, 0), width=2)
    buf = io.BytesIO()
    rgb.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


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
        return TipMeasurement(
            found=False,
            message="no dark pixels — check lighting / threshold",
            annotated_jpeg=_encode_preview(frame, None),
        )

    coverage = dark / total
    # A real tip is a small compact blob. If the dark region swamps the frame
    # the threshold/lighting is wrong; report it found but low-confidence so
    # the operator reviews rather than commits a garbage offset.
    if coverage > 0.6:
        return TipMeasurement(
            found=False,
            confidence=0.0,
            message="dark region covers the frame — adjust lighting or threshold",
            annotated_jpeg=_encode_preview(frame, None),
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
        annotated_jpeg=_encode_preview(frame, (cx, cy)),
    )


@dataclass(frozen=True)
class ScaleMeasurement:
    """Pixel extent of a known-size target, for the mm-per-pixel assistant."""

    found: bool
    width_px: float | None = None
    height_px: float | None = None
    annotated_jpeg: bytes | None = None
    message: str = ""


def detect_object_extent(
    frame: bytes,
    dark_threshold: int = 80,
    roi: Roi | None = None,
) -> ScaleMeasurement:
    """Measure the dark target's pixel bounding box, for scale calibration.

    The operator presents an object of *known* physical size (e.g. a 10 mm
    square); this returns its width/height in pixels so ``mm_per_pixel`` can be
    derived as ``known_mm / extent_px``. Same thresholding as the tip detector,
    but it reports the blob's extent (not its centroid) and marks the box.
    """
    gray = _decode_gray(frame)
    off_x, off_y = 0, 0
    if roi is not None:
        x0, y0 = max(0, roi.x), max(0, roi.y)
        x1 = min(gray.shape[1], roi.x + roi.width)
        y1 = min(gray.shape[0], roi.y + roi.height)
        if x1 <= x0 or y1 <= y0:
            return ScaleMeasurement(found=False, message="ROI is empty or outside the frame")
        gray = gray[y0:y1, x0:x1]
        off_x, off_y = x0, y0

    mask = gray < dark_threshold
    if not mask.any():
        return ScaleMeasurement(
            found=False,
            message="no dark target — check lighting / threshold",
            annotated_jpeg=_encode_preview(frame, None),
        )

    ys, xs = np.nonzero(mask)
    x_min, x_max = int(xs.min()) + off_x, int(xs.max()) + off_x
    y_min, y_max = int(ys.min()) + off_y, int(ys.max()) + off_y
    width_px = float(x_max - x_min + 1)
    height_px = float(y_max - y_min + 1)
    return ScaleMeasurement(
        found=True,
        width_px=width_px,
        height_px=height_px,
        annotated_jpeg=_encode_box(frame, (x_min, y_min, x_max, y_max)),
        message="ok",
    )


def _encode_box(frame: bytes, box: tuple[int, int, int, int]) -> bytes | None:
    """JPEG preview with a green bounding box drawn around the target."""
    try:
        with Image.open(io.BytesIO(frame)) as img:
            rgb = img.convert("RGB")
    except Exception:
        return None
    x_min, y_min, x_max, y_max = box
    ImageDraw.Draw(rgb).rectangle([(x_min, y_min), (x_max, y_max)], outline=(0, 200, 0), width=2)
    buf = io.BytesIO()
    rgb.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def average_tips(samples: list[TipMeasurement]) -> TipMeasurement:
    """Aggregate the found tips across repeated samples to cut detector noise.

    Uses the **median** of the found tips (pixels and mm) so a single bad frame
    among ``n`` — a stray dark blob, a momentary glitch — can't drag the result
    off the true tip the way a mean would. The confidence is the median of
    theirs, and ``spread_mm`` reports how far the farthest contributing sample
    sat from the median (a repeatability / stability signal).

    With no found sample, the last (not-found) measurement is returned so its
    message / preview still surface. The annotated frame of the sample closest
    to the median is kept for review.
    """
    found = [m for m in samples if m.found and m.tip_px and m.tip_mm]
    if not found:
        return samples[-1]
    n = len(found)
    px = (
        float(np.median([m.tip_px[0] for m in found])),
        float(np.median([m.tip_px[1] for m in found])),
    )
    mm = (
        float(np.median([m.tip_mm[0] for m in found])),
        float(np.median([m.tip_mm[1] for m in found])),
    )
    confidence = float(np.median([m.confidence for m in found]))
    # Repeatability: farthest contributing sample from the median tip (mm).
    dists = [np.hypot(m.tip_mm[0] - mm[0], m.tip_mm[1] - mm[1]) for m in found]
    spread_mm = float(max(dists))
    # Keep the preview of whichever sample landed closest to the median.
    closest = min(found, key=lambda m: np.hypot(m.tip_mm[0] - mm[0], m.tip_mm[1] - mm[1]))
    return TipMeasurement(
        found=True,
        tip_px=px,
        tip_mm=mm,
        confidence=confidence,
        message=f"median of {n}/{len(samples)}",
        spread_mm=spread_mm,
        annotated_jpeg=closest.annotated_jpeg,
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
        """Store the injected frame grabber and tip detector."""
        self._grab = grabber
        self._detect = detector
        self._tips: dict[int, TipMeasurement] = {}

    def reset(self) -> None:
        """Forget all measurements (start a fresh calibration run)."""
        self._tips.clear()

    def grab(self, camera_url: str) -> bytes:
        """Grab one frame via the injected grabber (used by scale calibration)."""
        return self._grab(camera_url)

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
        samples: int = 1,
    ) -> MeasureResult:
        """Grab ``samples`` frame(s) for ``slot`` and detect its tip, storing it.

        With ``samples > 1`` the tip is averaged across grabs to reduce
        detector noise. Returns the measurement and — once the reference slot
        has also been measured — the offset this slot implies relative to it.
        Raises ``RuntimeError`` only if a frame grab itself fails (propagated
        from the grabber); a frame with no detectable tip is a normal, low/zero
        confidence result, not an error.
        """
        n = max(1, samples)
        shots = [
            self._detect(self._grab(camera_url), mm_per_pixel, dark_threshold, roi)
            for _ in range(n)
        ]
        measurement = average_tips(shots)
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

"""ArUco fiducial tip detector (ADR 0005, optional sub-pixel path).

The ``dark_blob`` detector finds the tip directly but leans on lighting and
contrast. A more robust alternative is to rigidly attach a small printed
**ArUco marker** to the pen (or its holder) and detect *its* centre: ArUco
detection is sub-pixel and largely lighting-independent.

The marker need not sit exactly on the tip. Because pen offsets are measured
*relative* to a reference pen, any constant marker→tip displacement — the same
carriage geometry for every pen — cancels out, exactly like the
station-to-bed registration cancels for the blob detector.

OpenCV (``opencv-contrib-python``, for ``cv2.aruco``) is an **optional** host
dependency, imported lazily here so the rest of the app — and the test suite —
runs without it. Off a host that lacks it the detector returns a clear
"unavailable" measurement instead of raising, mirroring the GPIO backend.
"""

from __future__ import annotations

import numpy as np

from pen_plotter.vision.tip_detect import (
    Roi,
    TipMeasurement,
    _decode_gray,
    _encode_preview,
)

# Supported dictionaries → their ``cv2.aruco`` predefined-constant name. Kept
# small and explicit; extend as printed-marker needs grow.
_DICTS = {
    "4X4_50": "DICT_4X4_50",
    "4X4_100": "DICT_4X4_100",
    "5X5_50": "DICT_5X5_50",
    "6X6_50": "DICT_6X6_50",
    "APRILTAG_36h11": "DICT_APRILTAG_36h11",
}

DEFAULT_DICTIONARY = "4X4_50"


def aruco_available() -> bool:
    """True when OpenCV with the ``aruco`` module is importable on this host."""
    try:
        import cv2

        return hasattr(cv2, "aruco")
    except Exception:
        return False


def _marker_center(corners: object) -> tuple[float, float]:
    """Centre (x, y) of a marker from its 4 corner points.

    Accepts the per-marker corner array OpenCV returns (shape ``(1, 4, 2)`` or
    ``(4, 2)``); the mean of the corners is the marker centre, sub-pixel by
    construction.
    """
    pts = np.asarray(corners, dtype=np.float64).reshape(-1, 2)
    return (float(pts[:, 0].mean()), float(pts[:, 1].mean()))


def detect_tip_aruco(
    frame: bytes,
    mm_per_pixel: float,
    dark_threshold: int = 80,  # unused; kept for the TipDetector contract
    roi: Roi | None = None,
    *,
    dictionary: str = DEFAULT_DICTIONARY,
    marker_id: int | None = None,
) -> TipMeasurement:
    """Locate a pen via a rigidly-attached ArUco marker's sub-pixel centre.

    ``dictionary`` selects the printed-marker family; ``marker_id`` pins a
    specific marker (recommended when more than one is ever in view). Returns a
    normal not-found measurement — never raises — when OpenCV is absent, the
    dictionary is unknown, or no matching marker is detected.
    """
    if mm_per_pixel <= 0:
        return TipMeasurement(found=False, message="mm_per_pixel must be positive")
    try:
        import cv2
    except Exception:
        return TipMeasurement(
            found=False,
            message="ArUco detector needs opencv-contrib-python on the host",
            annotated_jpeg=_encode_preview(frame, None),
        )
    dict_name = _DICTS.get(dictionary)
    if dict_name is None:
        return TipMeasurement(found=False, message=f"unknown ArUco dictionary: {dictionary!r}")

    gray = _decode_gray(frame)
    off_x, off_y = 0, 0
    if roi is not None:
        x0, y0 = max(0, roi.x), max(0, roi.y)
        x1 = min(gray.shape[1], roi.x + roi.width)
        y1 = min(gray.shape[0], roi.y + roi.height)
        if x1 <= x0 or y1 <= y0:
            return TipMeasurement(found=False, message="ROI is empty or outside the frame")
        gray = gray[y0:y1, x0:x1]
        off_x, off_y = x0, y0

    aruco = cv2.aruco
    aruco_dict = aruco.getPredefinedDictionary(getattr(aruco, dict_name))
    # cv2 >= 4.7 exposes ArucoDetector; older releases use the free function.
    try:
        detector = aruco.ArucoDetector(aruco_dict, aruco.DetectorParameters())
        corners, ids, _ = detector.detectMarkers(gray)
    except AttributeError:
        corners, ids, _ = aruco.detectMarkers(gray, aruco_dict)

    if ids is None or len(corners) == 0:
        return TipMeasurement(
            found=False,
            message="no ArUco marker detected",
            annotated_jpeg=_encode_preview(frame, None),
        )
    id_list = [int(i) for i in np.asarray(ids).flatten().tolist()]
    chosen = 0
    if marker_id is not None:
        if marker_id not in id_list:
            return TipMeasurement(
                found=False,
                message=f"marker id {marker_id} not found (saw {id_list})",
                annotated_jpeg=_encode_preview(frame, None),
            )
        chosen = id_list.index(marker_id)

    cx, cy = _marker_center(corners[chosen])
    cx += off_x
    cy += off_y
    # One unambiguous marker (or an explicitly pinned id) is high-confidence;
    # extra markers in view without a pinned id lower it.
    confidence = 1.0 if len(id_list) == 1 or marker_id is not None else 0.6
    return TipMeasurement(
        found=True,
        tip_px=(cx, cy),
        tip_mm=(cx * mm_per_pixel, cy * mm_per_pixel),
        confidence=confidence,
        message="ok",
        annotated_jpeg=_encode_preview(frame, (cx, cy)),
    )

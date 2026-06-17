"""Camera-assisted pen-tip offset measurement (ADR 0005, phase 2).

Exercises the dark-blob detector and the calibration session/API end to end
with synthetic frames — no camera, no plotter. Frames are plain PIL images:
a light background with a dark square standing in for the pen tip.
"""

from __future__ import annotations

import io

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from pen_plotter.hardware.controller import controller
from pen_plotter.hardware.transport import MockTransport
from pen_plotter.main import app
from pen_plotter.vision.tip_detect import (
    Roi,
    TipCalibrator,
    detect_tip_dark_blob,
    offset_between,
)

PROFILE = "Custom CoreXY A3"


def _frame(blob_xy: tuple[int, int] | None, size: tuple[int, int] = (200, 200)) -> bytes:
    """A light frame with an optional 10×10 dark square centred at ``blob_xy``."""
    w, h = size
    arr = np.full((h, w), 240, dtype=np.uint8)
    if blob_xy is not None:
        cx, cy = blob_xy
        arr[cy - 5 : cy + 5, cx - 5 : cx + 5] = 10
    buf = io.BytesIO()
    Image.fromarray(arr, mode="L").save(buf, format="PNG")
    return buf.getvalue()


# ── detector ──────────────────────────────────────────────────────────────


def test_dark_blob_centroid_matches_blob() -> None:
    m = detect_tip_dark_blob(_frame((120, 80)), mm_per_pixel=0.1)
    assert m.found
    assert m.tip_px is not None
    # 10×10 square centred at (120, 80) → centroid ≈ (119.5, 79.5).
    assert abs(m.tip_px[0] - 119.5) < 1.0
    assert abs(m.tip_px[1] - 79.5) < 1.0
    assert m.tip_mm == (pytest.approx(m.tip_px[0] * 0.1), pytest.approx(m.tip_px[1] * 0.1))
    assert m.confidence > 0.5


def test_dark_blob_not_found_on_blank_frame() -> None:
    m = detect_tip_dark_blob(_frame(None), mm_per_pixel=0.1)
    assert not m.found
    assert m.tip_px is None


def test_dark_blob_rejects_swamped_frame() -> None:
    # A frame that is almost entirely dark → lighting/threshold wrong.
    arr = np.full((100, 100), 5, dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr, mode="L").save(buf, format="PNG")
    m = detect_tip_dark_blob(buf.getvalue(), mm_per_pixel=0.1)
    assert not m.found
    assert "lighting" in m.message or "threshold" in m.message


def test_dark_blob_rejects_nonpositive_scale() -> None:
    assert not detect_tip_dark_blob(_frame((50, 50)), mm_per_pixel=0.0).found


def test_roi_offset_is_added_back() -> None:
    # Blob at full-frame (150, 150); ROI starts at (100, 100). The centroid
    # must be reported in full-frame coords, not ROI-local.
    m = detect_tip_dark_blob(
        _frame((150, 150)),
        mm_per_pixel=0.1,
        roi=Roi(x=100, y=100, width=90, height=90),
    )
    assert m.found and m.tip_px is not None
    assert abs(m.tip_px[0] - 149.5) < 1.0
    assert abs(m.tip_px[1] - 149.5) < 1.0


def test_roi_excludes_blob_outside_region() -> None:
    m = detect_tip_dark_blob(
        _frame((20, 20)),  # blob top-left
        mm_per_pixel=0.1,
        roi=Roi(x=100, y=100, width=50, height=50),  # region far from blob
    )
    assert not m.found


# ── offset math ─────────────────────────────────────────────────────────────


def test_offset_between_is_the_difference() -> None:
    ref = detect_tip_dark_blob(_frame((100, 100)), mm_per_pixel=0.1)
    pen = detect_tip_dark_blob(_frame((120, 90)), mm_per_pixel=0.1)
    off = offset_between(pen, ref)
    assert off is not None
    # Δpx = (+20, -10) → Δmm = (+2.0, -1.0).
    assert off[0] == pytest.approx(2.0, abs=0.2)
    assert off[1] == pytest.approx(-1.0, abs=0.2)


def test_offset_none_when_either_missing() -> None:
    found = detect_tip_dark_blob(_frame((50, 50)), mm_per_pixel=0.1)
    missing = detect_tip_dark_blob(_frame(None), mm_per_pixel=0.1)
    assert offset_between(found, missing) is None
    assert offset_between(missing, found) is None


# ── calibrator session ──────────────────────────────────────────────────────


def test_calibrator_derives_offset_after_reference() -> None:
    frames = {0: _frame((100, 100)), 1: _frame((118, 100))}
    calib = TipCalibrator(grabber=lambda url: frames[int(url)])

    # Measure the non-reference slot first: no offset yet (reference unknown).
    r1 = calib.measure(slot=1, reference_slot=0, camera_url="1", mm_per_pixel=0.1)
    assert r1.measurement.found
    assert not r1.reference_measured
    assert r1.offset_mm is None

    # Now the reference itself → offset 0.
    r0 = calib.measure(slot=0, reference_slot=0, camera_url="0", mm_per_pixel=0.1)
    assert r0.is_reference
    assert r0.offset_mm == pytest.approx((0.0, 0.0))

    # Re-measure slot 1 → offset is the +18 px → +1.8 mm in X.
    r1b = calib.measure(slot=1, reference_slot=0, camera_url="1", mm_per_pixel=0.1)
    assert r1b.reference_measured
    assert r1b.offset_mm is not None
    assert r1b.offset_mm[0] == pytest.approx(1.8, abs=0.2)
    assert r1b.offset_mm[1] == pytest.approx(0.0, abs=0.2)
    assert calib.measured_slots == [0, 1]

    calib.reset()
    assert calib.measured_slots == []


# ── API ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # Swap the module-level calibrator's grabber for a fake camera that keys
    # the JPEG by the URL, and start each test from a clean session.
    from pen_plotter.api import tip_calibration as api

    frames = {"cam://ref": _frame((100, 100)), "cam://pen": _frame((130, 100))}
    monkeypatch.setattr(api._calibrator, "_grab", lambda url: frames[url])
    api._calibrator.reset()
    return TestClient(app)


def test_measure_endpoint_returns_offset_after_reference(client: TestClient) -> None:
    # Reference first.
    ref = client.post(
        "/plotter/tip-calibration/measure",
        json={"slot": 0, "camera_url": "cam://ref", "mm_per_pixel": 0.1, "reference_slot": 0},
    )
    assert ref.status_code == 200
    assert ref.json()["found"] is True
    assert ref.json()["is_reference"] is True
    assert ref.json()["offset_mm"] == {"x": pytest.approx(0.0), "y": pytest.approx(0.0)}

    # Then a pen offset +30 px in X → +3.0 mm.
    pen = client.post(
        "/plotter/tip-calibration/measure",
        json={"slot": 1, "camera_url": "cam://pen", "mm_per_pixel": 0.1, "reference_slot": 0},
    )
    body = pen.json()
    assert body["found"] is True
    assert body["reference_measured"] is True
    assert body["offset_mm"]["x"] == pytest.approx(3.0, abs=0.2)
    assert body["offset_mm"]["y"] == pytest.approx(0.0, abs=0.2)


def test_status_and_reset_endpoints(client: TestClient) -> None:
    client.post(
        "/plotter/tip-calibration/measure",
        json={"slot": 0, "camera_url": "cam://ref", "mm_per_pixel": 0.1},
    )
    assert client.get("/plotter/tip-calibration/status").json()["measured_slots"] == [0]
    assert client.post("/plotter/tip-calibration/reset").json()["measured_slots"] == []


def test_measure_surfaces_camera_failure_as_502(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pen_plotter.api import tip_calibration as api

    def boom(url: str) -> bytes:
        raise RuntimeError("stream offline")

    monkeypatch.setattr(api._calibrator, "_grab", boom)
    resp = client.post(
        "/plotter/tip-calibration/measure",
        json={"slot": 0, "camera_url": "cam://x", "mm_per_pixel": 0.1},
    )
    assert resp.status_code == 502
    # The app normalizes HTTPException into the {code, message, details} envelope.
    assert "stream offline" in resp.json()["message"]


# ── guided head travel (phase 2b) ────────────────────────────────────────────


@pytest.fixture
def connected() -> MockTransport:
    """Attach a mock transport to the shared controller and detach afterwards."""
    transport = MockTransport()
    controller.attach(transport)
    yield transport
    controller.abort()
    controller._transport = None
    controller._streamer = None
    controller._task = None


def test_measure_moves_head_to_station(
    client: TestClient, connected: MockTransport, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pen_plotter.api import tip_calibration as api

    monkeypatch.setattr(api._calibrator, "_grab", lambda url: _frame((100, 100)))
    resp = client.post(
        "/plotter/tip-calibration/measure",
        json={
            "slot": 0,
            "camera_url": "cam://x",
            "mm_per_pixel": 0.1,
            "move_to_station": True,
            "profile_name": PROFILE,
            "station_position": {"x": 20, "y": 30},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["found"] is True
    # The head was driven to the station before the frame was grabbed.
    assert any("X20.000 Y30.000" in line for line in connected.written)


def test_move_to_station_requires_position_and_profile(client: TestClient) -> None:
    resp = client.post(
        "/plotter/tip-calibration/measure",
        json={
            "slot": 0,
            "camera_url": "cam://x",
            "mm_per_pixel": 0.1,
            "move_to_station": True,
        },
    )
    assert resp.status_code == 422


def test_move_to_station_when_disconnected_is_409(client: TestClient) -> None:
    # No ``connected`` fixture → the controller has no transport.
    resp = client.post(
        "/plotter/tip-calibration/measure",
        json={
            "slot": 0,
            "camera_url": "cam://x",
            "mm_per_pixel": 0.1,
            "move_to_station": True,
            "profile_name": PROFILE,
            "station_position": {"x": 20, "y": 30},
        },
    )
    assert resp.status_code == 409

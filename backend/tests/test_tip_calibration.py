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
    average_tips,
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


def test_annotated_preview_is_a_valid_jpeg() -> None:
    m = detect_tip_dark_blob(_frame((120, 80)), mm_per_pixel=0.1)
    assert m.found and m.annotated_jpeg is not None
    # Decodes as a JPEG of the same size, and the marker added red where the
    # source was uniformly grey.
    with Image.open(io.BytesIO(m.annotated_jpeg)) as img:
        assert img.format == "JPEG"
        assert img.size == (200, 200)
        px = img.convert("RGB").getpixel((120, 80))
    assert px[0] > px[1] + 40 and px[0] > px[2] + 40  # reddish marker


def test_blank_frame_still_returns_a_preview() -> None:
    # Even with no tip, the operator gets the frame back to check framing.
    m = detect_tip_dark_blob(_frame(None), mm_per_pixel=0.1)
    assert m.annotated_jpeg is not None


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


# ── multi-frame averaging ────────────────────────────────────────────────────


def test_average_tips_averages_found_samples() -> None:
    shots = [
        detect_tip_dark_blob(_frame((100, 100)), mm_per_pixel=0.1),
        detect_tip_dark_blob(_frame((120, 100)), mm_per_pixel=0.1),
    ]
    avg = average_tips(shots)
    assert avg.found and avg.tip_px is not None
    # Mean of x ∈ {99.5, 119.5} ≈ 109.5; y unchanged.
    assert avg.tip_px[0] == pytest.approx(109.5, abs=0.5)
    assert avg.tip_px[1] == pytest.approx(99.5, abs=0.5)
    assert "averaged 2/2" in avg.message


def test_average_tips_skips_not_found_samples() -> None:
    shots = [
        detect_tip_dark_blob(_frame((100, 100)), mm_per_pixel=0.1),
        detect_tip_dark_blob(_frame(None), mm_per_pixel=0.1),  # miss
    ]
    avg = average_tips(shots)
    assert avg.found and avg.tip_px is not None
    # Only the found sample contributes.
    assert avg.tip_px[0] == pytest.approx(99.5, abs=0.5)
    assert "averaged 1/2" in avg.message


def test_average_tips_returns_last_when_none_found() -> None:
    shots = [detect_tip_dark_blob(_frame(None), mm_per_pixel=0.1) for _ in range(2)]
    avg = average_tips(shots)
    assert not avg.found


def test_calibrator_samples_grabs_and_averages() -> None:
    # Two alternating frames; with samples=2 the measured tip is their mean.
    frames = [_frame((100, 100)), _frame((120, 100))]
    calls = {"n": 0}

    def grab(url: str) -> bytes:
        frame = frames[calls["n"] % len(frames)]
        calls["n"] += 1
        return frame

    calib = TipCalibrator(grabber=grab)
    r = calib.measure(slot=0, reference_slot=0, camera_url="x", mm_per_pixel=0.1, samples=2)
    assert calls["n"] == 2  # grabbed twice
    assert r.measurement.found and r.measurement.tip_px is not None
    assert r.measurement.tip_px[0] == pytest.approx(109.5, abs=0.5)


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
    # The response carries a JPEG data URL preview for operator confirmation.
    assert body["annotated_image"].startswith("data:image/jpeg;base64,")


def test_measure_endpoint_honours_samples(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pen_plotter.api import tip_calibration as api

    calls = {"n": 0}

    def grab(url: str) -> bytes:
        calls["n"] += 1
        return _frame((100, 100))

    monkeypatch.setattr(api._calibrator, "_grab", grab)
    resp = client.post(
        "/plotter/tip-calibration/measure",
        json={"slot": 0, "camera_url": "cam://x", "mm_per_pixel": 0.1, "samples": 3},
    )
    assert resp.status_code == 200
    assert resp.json()["found"] is True
    assert calls["n"] == 3  # grabbed three frames and averaged


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


def test_move_to_station_includes_z_when_given(
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
            "station_z_mm": 5,
        },
    )
    assert resp.status_code == 200
    assert any("Z5.000" in line for line in connected.written)


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


# ── automatic pen-fetch (phase 2c) ───────────────────────────────────────────

RACK_PROFILE = "Custom CoreXY A3 (rack)"


def test_fetch_pen_streams_the_swap_then_measures(
    client: TestClient, connected: MockTransport, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pen_plotter.api import tip_calibration as api

    monkeypatch.setattr(api._calibrator, "_grab", lambda url: _frame((100, 100)))
    resp = client.post(
        "/plotter/tip-calibration/measure",
        json={
            "slot": 1,
            "camera_url": "cam://x",
            "mm_per_pixel": 0.1,
            "fetch_pen": True,
            "profile_name": RACK_PROFILE,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["found"] is True
    # The host-macro swap was streamed to the device before measuring.
    assert any("G53 G0 Z5" in line for line in connected.written)
    # The slot index was substituted into the rack travel line.
    assert any("X10" in line for line in connected.written)


def test_fetch_then_move_orders_swap_before_travel(
    client: TestClient, connected: MockTransport, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pen_plotter.api import tip_calibration as api

    monkeypatch.setattr(api._calibrator, "_grab", lambda url: _frame((100, 100)))
    resp = client.post(
        "/plotter/tip-calibration/measure",
        json={
            "slot": 1,
            "camera_url": "cam://x",
            "mm_per_pixel": 0.1,
            "fetch_pen": True,
            "move_to_station": True,
            "station_position": {"x": 20, "y": 30},
            "profile_name": RACK_PROFILE,
        },
    )
    assert resp.status_code == 200
    written = connected.written
    swap_idx = next(i for i, line in enumerate(written) if "G53 G0 Z5" in line)
    station_idx = next(i for i, line in enumerate(written) if "X20.000 Y30.000" in line)
    assert swap_idx < station_idx


def test_fetch_pen_on_manual_profile_is_409(
    client: TestClient, connected: MockTransport
) -> None:
    # A manual-swap profile can't fetch on its own — load by hand.
    resp = client.post(
        "/plotter/tip-calibration/measure",
        json={"slot": 1, "camera_url": "cam://x", "mm_per_pixel": 0.1, "fetch_pen": True,
              "profile_name": PROFILE},
    )
    assert resp.status_code == 409
    assert "by hand" in resp.json()["message"]


# ── camera lighting via GPIO (audit fix) ─────────────────────────────────────


class _FakeGpio:
    """Records GPIO writes so the lighting wiring is testable off-Pi."""

    def __init__(self) -> None:
        self.writes: list[tuple[int, bool]] = []

    def set(self, pin: int, value: bool) -> None:
        self.writes.append((pin, value))


@pytest.fixture
def gpio(monkeypatch: pytest.MonkeyPatch) -> _FakeGpio:
    from pen_plotter.hardware import gpio as gpio_mod

    fake = _FakeGpio()
    monkeypatch.setattr(gpio_mod.light, "_backend", fake)
    return fake


def test_measure_toggles_gpio_light_around_grab(
    client: TestClient, gpio: _FakeGpio, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pen_plotter.api import tip_calibration as api

    monkeypatch.setattr(api._calibrator, "_grab", lambda url: _frame((100, 100)))
    resp = client.post(
        "/plotter/tip-calibration/measure",
        json={
            "slot": 0,
            "camera_url": "cam://x",
            "mm_per_pixel": 0.1,
            "light": True,
            "light_gpio_pin": 17,
        },
    )
    assert resp.status_code == 200
    # On (True) before off (False), both on pin 17.
    assert gpio.writes == [(17, True), (17, False)]


def test_measure_light_active_low_inverts_levels(
    client: TestClient, gpio: _FakeGpio, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pen_plotter.api import tip_calibration as api

    monkeypatch.setattr(api._calibrator, "_grab", lambda url: _frame((100, 100)))
    client.post(
        "/plotter/tip-calibration/measure",
        json={
            "slot": 0,
            "camera_url": "cam://x",
            "mm_per_pixel": 0.1,
            "light": True,
            "light_gpio_pin": 17,
            "light_active_high": False,
        },
    )
    # Active-low: "on" drives the pin LOW, "off" drives it HIGH.
    assert gpio.writes == [(17, False), (17, True)]


def test_light_endpoint_drives_pin(client: TestClient, gpio: _FakeGpio) -> None:
    resp = client.post("/plotter/tip-calibration/light", json={"pin": 17, "on": True})
    assert resp.status_code == 200
    assert resp.json() == {"on": True}
    assert gpio.writes == [(17, True)]


def test_light_endpoint_without_gpio_backend_is_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pen_plotter.hardware import gpio as gpio_mod

    monkeypatch.setattr(gpio_mod.light, "_backend", None)
    resp = client.post("/plotter/tip-calibration/light", json={"pin": 17, "on": True})
    assert resp.status_code == 503


def test_gpio_endpoint_lists_pins(client: TestClient, gpio: _FakeGpio) -> None:
    body = client.get("/plotter/tip-calibration/gpio").json()
    assert body["available"] is True
    assert 17 in body["pins"]


# ── mm-per-pixel scale assistant ─────────────────────────────────────────────


def test_calibrate_scale_derives_mm_per_pixel(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pen_plotter.api import tip_calibration as api

    # A 40 px wide / 40 px tall dark square (the _frame blob is 10 px; use a
    # bigger one by stacking). Build a 40 px square target directly.
    arr = np.full((200, 200), 240, dtype=np.uint8)
    arr[80:120, 60:100] = 10  # 40×40 px dark square
    buf = io.BytesIO()
    Image.fromarray(arr, mode="L").save(buf, format="PNG")
    monkeypatch.setattr(api._calibrator, "_grab", lambda url: buf.getvalue())

    resp = client.post(
        "/plotter/tip-calibration/calibrate-scale",
        json={"camera_url": "cam://x", "known_mm": 20.0},
    )
    body = resp.json()
    assert body["found"] is True
    # 40 px extent for a 20 mm target → 0.5 mm/px.
    assert body["mm_per_pixel"] == pytest.approx(0.5, abs=0.02)
    assert body["annotated_image"].startswith("data:image/jpeg;base64,")


def test_calibrate_scale_not_found_on_blank(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pen_plotter.api import tip_calibration as api

    monkeypatch.setattr(api._calibrator, "_grab", lambda url: _frame(None))
    resp = client.post(
        "/plotter/tip-calibration/calibrate-scale",
        json={"camera_url": "cam://x", "known_mm": 20.0},
    )
    assert resp.json()["found"] is False


def test_fetch_pen_requires_profile(client: TestClient) -> None:
    resp = client.post(
        "/plotter/tip-calibration/measure",
        json={"slot": 1, "camera_url": "cam://x", "mm_per_pixel": 0.1, "fetch_pen": True},
    )
    assert resp.status_code == 422


def test_fetch_pen_when_disconnected_is_409(client: TestClient) -> None:
    resp = client.post(
        "/plotter/tip-calibration/measure",
        json={"slot": 1, "camera_url": "cam://x", "mm_per_pixel": 0.1, "fetch_pen": True,
              "profile_name": RACK_PROFILE},
    )
    assert resp.status_code == 409

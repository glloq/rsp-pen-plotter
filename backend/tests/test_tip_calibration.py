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


def _light_frame(blob_xy: tuple[int, int] | None, size: tuple[int, int] = (200, 200)) -> bytes:
    """A dark frame with an optional 10×10 *light* square (light-tip station)."""
    w, h = size
    arr = np.full((h, w), 15, dtype=np.uint8)
    if blob_xy is not None:
        cx, cy = blob_xy
        arr[cy - 5 : cy + 5, cx - 5 : cx + 5] = 245
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


def test_light_tip_found_with_invert() -> None:
    # A light tip on a dark background is invisible to the default detector…
    plain = detect_tip_dark_blob(_light_frame((120, 80)), mm_per_pixel=0.1)
    assert not plain.found
    # …and found once the luminance is inverted (tip_style: light).
    m = detect_tip_dark_blob(_light_frame((120, 80)), mm_per_pixel=0.1, invert=True)
    assert m.found and m.tip_px is not None
    assert abs(m.tip_px[0] - 119.5) < 1.0
    assert abs(m.tip_px[1] - 79.5) < 1.0
    assert m.confidence > 0.5


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


def test_average_tips_takes_the_median() -> None:
    shots = [
        detect_tip_dark_blob(_frame((100, 100)), mm_per_pixel=0.1),
        detect_tip_dark_blob(_frame((120, 100)), mm_per_pixel=0.1),
    ]
    avg = average_tips(shots)
    assert avg.found and avg.tip_px is not None
    # Median of x ∈ {99.5, 119.5} ≈ 109.5; y unchanged.
    assert avg.tip_px[0] == pytest.approx(109.5, abs=0.5)
    assert avg.tip_px[1] == pytest.approx(99.5, abs=0.5)
    assert "median of 2/2" in avg.message
    # spread = farthest sample from the median ≈ |119.5-109.5|*0.1 = 1.0 mm.
    assert avg.spread_mm == pytest.approx(1.0, abs=0.1)


def test_average_tips_is_robust_to_one_outlier() -> None:
    # Two tight samples + one wildly off frame. The median ignores the outlier
    # where a mean would be dragged ~6 px (0.6 mm) toward it.
    shots = [
        detect_tip_dark_blob(_frame((100, 100)), mm_per_pixel=0.1),
        detect_tip_dark_blob(_frame((101, 100)), mm_per_pixel=0.1),
        detect_tip_dark_blob(_frame((180, 100)), mm_per_pixel=0.1),  # outlier
    ]
    avg = average_tips(shots)
    assert avg.found and avg.tip_px is not None
    # Median x ≈ 100.5 px (the middle sample), not pulled toward 180.
    assert avg.tip_px[0] == pytest.approx(100.5, abs=1.0)


def test_average_tips_skips_not_found_samples() -> None:
    shots = [
        detect_tip_dark_blob(_frame((100, 100)), mm_per_pixel=0.1),
        detect_tip_dark_blob(_frame(None), mm_per_pixel=0.1),  # miss
    ]
    avg = average_tips(shots)
    assert avg.found and avg.tip_px is not None
    # Only the found sample contributes.
    assert avg.tip_px[0] == pytest.approx(99.5, abs=0.5)
    assert "median of 1/2" in avg.message
    assert avg.spread_mm == pytest.approx(0.0, abs=0.01)


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
    body = resp.json()
    assert body["found"] is True
    assert calls["n"] == 3  # grabbed three frames and averaged
    # Identical frames → perfect repeatability.
    assert body["spread_mm"] == pytest.approx(0.0, abs=0.01)


def test_measure_endpoint_light_tip_style(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pen_plotter.api import tip_calibration as api

    monkeypatch.setattr(api._calibrator, "_grab", lambda url: _light_frame((100, 100)))
    # Default (dark) style misses the light tip…
    miss = client.post(
        "/plotter/tip-calibration/measure",
        json={"slot": 0, "camera_url": "cam://x", "mm_per_pixel": 0.1},
    )
    assert miss.json()["found"] is False
    # …the light style finds it.
    hit = client.post(
        "/plotter/tip-calibration/measure",
        json={"slot": 0, "camera_url": "cam://x", "mm_per_pixel": 0.1, "tip_style": "light"},
    )
    assert hit.json()["found"] is True


def test_dry_run_does_not_store_the_measurement(client: TestClient) -> None:
    # A dry run (the UI's "Test detection") reports the tip…
    resp = client.post(
        "/plotter/tip-calibration/measure",
        json={"slot": 0, "camera_url": "cam://ref", "mm_per_pixel": 0.1, "dry_run": True},
    )
    assert resp.status_code == 200
    assert resp.json()["found"] is True
    # …but is NOT remembered as the slot's measurement.
    assert client.get("/plotter/tip-calibration/status").json()["measured_slots"] == []


def test_dry_run_does_not_overwrite_the_reference(client: TestClient) -> None:
    # Reference measured for real at x=100 px…
    client.post(
        "/plotter/tip-calibration/measure",
        json={"slot": 0, "camera_url": "cam://ref", "mm_per_pixel": 0.1},
    )
    # …then a dry-run detection on the reference slot sees a different frame
    # (x=130 px) — e.g. the operator tuning lighting with a random object.
    client.post(
        "/plotter/tip-calibration/measure",
        json={"slot": 0, "camera_url": "cam://pen", "mm_per_pixel": 0.1, "dry_run": True},
    )
    # Measuring a pen at the same x=130 px must still yield +3.0 mm vs the
    # REAL reference, proving the dry run didn't replace it.
    pen = client.post(
        "/plotter/tip-calibration/measure",
        json={"slot": 1, "camera_url": "cam://pen", "mm_per_pixel": 0.1},
    )
    assert pen.json()["offset_mm"]["x"] == pytest.approx(3.0, abs=0.2)


def _low_confidence_frame(size: tuple[int, int] = (200, 200)) -> bytes:
    """A frame whose dark blob swamps ~25% of it → found, but low confidence."""
    w, h = size
    arr = np.full((h, w), 240, dtype=np.uint8)
    arr[50:150, 50:150] = 10  # 100×100 of 200×200 = 25% coverage
    buf = io.BytesIO()
    Image.fromarray(arr, mode="L").save(buf, format="PNG")
    return buf.getvalue()


def test_min_confidence_gates_session_storage(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pen_plotter.api import tip_calibration as api

    monkeypatch.setattr(api._calibrator, "_grab", lambda url: _low_confidence_frame())
    # Below the gate: reported (found, low confidence) but NOT stored, so an
    # untrusted reference can't become the baseline for later offsets.
    resp = client.post(
        "/plotter/tip-calibration/measure",
        json={"slot": 0, "camera_url": "cam://x", "mm_per_pixel": 0.1, "min_confidence": 0.35},
    )
    body = resp.json()
    assert body["found"] is True
    assert body["confidence"] < 0.35
    assert client.get("/plotter/tip-calibration/status").json()["measured_slots"] == []

    # Without a gate (the default) the same frame is stored.
    client.post(
        "/plotter/tip-calibration/measure",
        json={"slot": 0, "camera_url": "cam://x", "mm_per_pixel": 0.1},
    )
    assert client.get("/plotter/tip-calibration/status").json()["measured_slots"] == [0]


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


def test_fetch_pen_on_manual_profile_is_409(client: TestClient, connected: MockTransport) -> None:
    # A manual-swap profile can't fetch on its own — load by hand.
    resp = client.post(
        "/plotter/tip-calibration/measure",
        json={
            "slot": 1,
            "camera_url": "cam://x",
            "mm_per_pixel": 0.1,
            "fetch_pen": True,
            "profile_name": PROFILE,
        },
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


def test_calibrate_scale_light_target(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from pen_plotter.api import tip_calibration as api

    # A 40×40 px light square on a dark background.
    arr = np.full((200, 200), 15, dtype=np.uint8)
    arr[80:120, 60:100] = 245
    buf = io.BytesIO()
    Image.fromarray(arr, mode="L").save(buf, format="PNG")
    monkeypatch.setattr(api._calibrator, "_grab", lambda url: buf.getvalue())

    resp = client.post(
        "/plotter/tip-calibration/calibrate-scale",
        json={"camera_url": "cam://x", "known_mm": 20.0, "tip_style": "light"},
    )
    body = resp.json()
    assert body["found"] is True
    assert body["mm_per_pixel"] == pytest.approx(0.5, abs=0.02)


def test_fetch_pen_requires_profile(client: TestClient) -> None:
    resp = client.post(
        "/plotter/tip-calibration/measure",
        json={"slot": 1, "camera_url": "cam://x", "mm_per_pixel": 0.1, "fetch_pen": True},
    )
    assert resp.status_code == 422


def test_fetch_pen_when_disconnected_is_409(client: TestClient) -> None:
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
    assert resp.status_code == 409


# ── P0.1: camera work must not block the event loop ──────────────────────────


@pytest.mark.asyncio
async def test_slow_camera_does_not_block_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """A wedged camera can make ``measure`` sit for tens of seconds. That work
    must run in a worker thread so other routes (an emergency stop, status)
    keep responding — the loop must never be parked on the blocking grab."""
    import asyncio
    import time

    import httpx
    from httpx import ASGITransport

    from pen_plotter.api import tip_calibration as api

    def slow_grab(_url: str) -> bytes:
        time.sleep(1.0)  # a stalled camera, blocking the calling *thread*
        return _frame((100, 100))

    monkeypatch.setattr(api._calibrator, "_grab", slow_grab)
    api._calibrator.reset()

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        measure = asyncio.create_task(
            client.post(
                "/plotter/tip-calibration/measure",
                json={"slot": 0, "camera_url": "cam://x", "mm_per_pixel": 0.1},
            )
        )
        await asyncio.sleep(0.05)  # let the grab get underway in its thread
        # An unrelated route must answer promptly while the grab is in flight.
        start = time.monotonic()
        status = await client.get("/plotter/tip-calibration/status")
        elapsed = time.monotonic() - start
        assert status.status_code == 200
        assert elapsed < 0.5, f"event loop blocked for {elapsed:.2f}s during camera grab"

        resp = await measure
        assert resp.status_code == 200
        assert resp.json()["found"] is True


# ── P2: robustness to a second dark region in the ROI ────────────────────────


def _frame_two_blobs(
    tip_xy: tuple[int, int],
    tip_half: int,
    stray_xy: tuple[int, int],
    stray_half: int,
    size: tuple[int, int] = (200, 200),
) -> bytes:
    """Light frame with a large 'tip' square and a smaller stray dark square."""
    w, h = size
    arr = np.full((h, w), 240, dtype=np.uint8)
    for (cx, cy), half in ((tip_xy, tip_half), (stray_xy, stray_half)):
        arr[cy - half : cy + half, cx - half : cx + half] = 10
    buf = io.BytesIO()
    Image.fromarray(arr, mode="L").save(buf, format="PNG")
    return buf.getvalue()


def test_stray_dark_patch_does_not_shift_centroid() -> None:
    """A shadow / stray mark elsewhere in the ROI must not pull the measured
    tip off the real (largest) blob (P2)."""
    # Tip: 20×20 square at (60, 100); stray: 6×6 speck far away at (160, 40).
    frame = _frame_two_blobs((60, 100), 10, (160, 40), 3)
    m = detect_tip_dark_blob(frame, mm_per_pixel=0.1)
    assert m.found and m.tip_px is not None
    # Centroid stays on the tip (~59.5, 99.5), not dragged toward the speck.
    assert abs(m.tip_px[0] - 59.5) < 2.0
    assert abs(m.tip_px[1] - 99.5) < 2.0


def test_single_blob_detection_is_unchanged() -> None:
    """The largest-component logic is a no-op for a clean single-blob frame."""
    m = detect_tip_dark_blob(_frame((120, 80)), mm_per_pixel=0.1)
    assert m.found and m.tip_px is not None
    assert abs(m.tip_px[0] - 119.5) < 1.0
    assert abs(m.tip_px[1] - 79.5) < 1.0
    assert m.confidence > 0.5


# ── P0.2 / P0.3: calibration concurrency + session safety ────────────────────


def test_measure_storing_is_discarded_after_reset() -> None:
    """A measurement whose worker outlives a reset (e.g. after a timeout) must
    NOT write its result back into the fresh session (P0.3)."""
    import threading
    import time

    from pen_plotter.vision.tip_detect import TipCalibrator

    release = threading.Event()

    def slow_grab(_url: str) -> bytes:
        release.wait(2.0)
        return _frame((100, 100))

    calib = TipCalibrator(grabber=slow_grab)
    box: dict[str, object] = {}

    def run() -> None:
        box["result"] = calib.measure(
            slot=0, reference_slot=0, camera_url="x", mm_per_pixel=0.1
        )

    worker = threading.Thread(target=run)
    worker.start()
    time.sleep(0.05)  # let the worker claim its generation, then reset under it
    calib.reset()
    release.set()
    worker.join(2.0)

    # The straggler's store was dropped — the reset session stays empty.
    assert calib.measured_slots == []


def test_reset_does_not_corrupt_a_later_measurement() -> None:
    """After a reset, a fresh measurement stores normally (generation bump is
    per-operation, not a permanent lock-out)."""
    from pen_plotter.vision.tip_detect import TipCalibrator

    calib = TipCalibrator(grabber=lambda _u: _frame((100, 100)))
    calib.measure(slot=0, reference_slot=0, camera_url="x", mm_per_pixel=0.1)
    assert calib.measured_slots == [0]
    calib.reset()
    assert calib.measured_slots == []
    calib.measure(slot=1, reference_slot=1, camera_url="x", mm_per_pixel=0.1)
    assert calib.measured_slots == [1]


@pytest.mark.asyncio
async def test_second_calibration_while_busy_returns_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A whole calibration is one physical transaction; a second one arriving
    mid-flight is refused with 409 rather than interleaving (P0.2)."""
    import asyncio
    import time

    import httpx
    from httpx import ASGITransport

    from pen_plotter.api import tip_calibration as api

    def slow_grab(_url: str) -> bytes:
        time.sleep(0.5)  # hold the lock for the whole measurement
        return _frame((100, 100))

    monkeypatch.setattr(api._calibrator, "_grab", slow_grab)
    api._calibrator.reset()

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        body = {"slot": 0, "camera_url": "x", "mm_per_pixel": 0.1}
        first = asyncio.create_task(client.post("/plotter/tip-calibration/measure", json=body))
        await asyncio.sleep(0.1)  # let the first calibration acquire the lock
        second = await client.post(
            "/plotter/tip-calibration/measure",
            json={"slot": 1, "camera_url": "x", "mm_per_pixel": 0.1},
        )
        assert second.status_code == 409
        assert "in progress" in second.json()["message"]

        done = await first
        assert done.status_code == 200


def test_measure_cancel_event_stops_before_grab_and_stores_nothing() -> None:
    """A pre-set cancel flag aborts the measurement before any grab and never
    stores a result (P0.2)."""
    import threading

    from pen_plotter.vision.tip_detect import TipCalibrator

    ev = threading.Event()
    ev.set()
    calib = TipCalibrator(grabber=lambda _u: _frame((100, 100)))
    result = calib.measure(
        slot=0, reference_slot=0, camera_url="x", mm_per_pixel=0.1, cancel_event=ev
    )
    assert result.measurement.found is False
    assert calib.measured_slots == []


@pytest.mark.asyncio
async def test_calibration_timeout_drains_worker_and_discards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On timeout the route returns 504, the straggler worker's store is
    discarded (generation invalidated), and the lock is released only after
    the worker drains — so the next calibration succeeds (P0.2)."""
    import time

    import httpx
    from httpx import ASGITransport

    from pen_plotter.api import tip_calibration as api

    monkeypatch.setattr(api, "_CALIBRATION_TIMEOUT_S", 0.1)
    slow = {"grab": True}

    def maybe_slow_grab(_url: str) -> bytes:
        if slow["grab"]:
            time.sleep(0.4)  # exceeds the 0.1 s timeout
        return _frame((100, 100))

    monkeypatch.setattr(api._calibrator, "_grab", maybe_slow_grab)
    api._calibrator.reset()

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        timed_out = await client.post(
            "/plotter/tip-calibration/measure",
            json={"slot": 0, "camera_url": "x", "mm_per_pixel": 0.1},
        )
        assert timed_out.status_code == 504
        # The timed-out worker stored nothing.
        status = await client.get("/plotter/tip-calibration/status")
        assert status.json()["measured_slots"] == []

        # The lock was released after the drain: a fast measurement now works.
        slow["grab"] = False
        ok = await client.post(
            "/plotter/tip-calibration/measure",
            json={"slot": 0, "camera_url": "x", "mm_per_pixel": 0.1},
        )
        assert ok.status_code == 200
        assert ok.json()["found"] is True

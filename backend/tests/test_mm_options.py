"""Millimetre algorithm options adapt the rendering to the page format.

Length knobs (``spacing_mm``, ``cell_size_mm``, …) are physical: the
frontend ships the placement's footprint with each ``/rerender`` and the
backend converts every ``*_mm`` option into its ``*_px`` twin at the
raster's px-per-mm scale (:func:`convert_mm_options`). The same knob
value therefore keeps the same on-paper pitch on every page format — a
bigger sheet gets proportionally more lines instead of the same geometry
scaled up.
"""

from __future__ import annotations

import io
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from pen_plotter.api import rerender as rerender_module
from pen_plotter.converters.algorithms._style import convert_mm_options
from pen_plotter.converters.bitmap import BitmapConverter, BitmapOptions, SegmentationResult
from pen_plotter.converters.bitmap.render import render_from_segmentation
from pen_plotter.main import app

# ── convert_mm_options unit behaviour ────────────────────────────────


def test_convert_mm_options_scales_and_renames() -> None:
    out = convert_mm_options({"spacing_mm": 2.0, "angle_deg": 45}, px_per_mm=3.0)
    assert out == {"spacing_px": 6.0, "angle_deg": 45}


def test_convert_mm_options_mm_wins_over_explicit_px_twin() -> None:
    out = convert_mm_options({"spacing_mm": 2.0, "spacing_px": 99}, px_per_mm=2.0)
    assert out["spacing_px"] == 4.0


def test_convert_mm_options_passthrough_cases() -> None:
    assert convert_mm_options(None, 2.0) == {}
    assert convert_mm_options({}, 2.0) == {}
    # Non-numeric and boolean ``*_mm`` keys are left untouched (they are
    # not lengths) and the input dict itself is never mutated.
    options = {"label_mm": "x", "flag_mm": True, "spacing_px": 5}
    out = convert_mm_options(options, 2.0)
    assert out == {"label_mm": "x", "flag_mm": True, "spacing_px": 5}
    assert options == {"label_mm": "x", "flag_mm": True, "spacing_px": 5}


# ── render-level physical adaptation ─────────────────────────────────


def _solid_seg(size: int = 120) -> SegmentationResult:
    labels = np.zeros((size, size), dtype=np.intp)
    palette = np.array([[0, 0, 0]], dtype=np.uint8)
    return SegmentationResult(labels=labels, palette=palette, width=size, height=size)


def _render_scanlines(px_per_mm: float | None) -> str:
    svg, warnings = render_from_segmentation(
        _solid_seg(),
        algorithm="scanlines",
        algorithm_options={"spacing_mm": 2.0},
        mono_ink_color=None,
        drop_background=False,
        background_luminance=0.92,
        px_per_mm=px_per_mm,
    )
    assert not warnings
    return svg


def test_same_mm_spacing_yields_more_lines_on_a_bigger_page() -> None:
    # Identical raster + identical knob; only the physical footprint
    # changes. 120 px mapped to an A6 width (105 mm) vs an A2 width
    # (420 mm): the 2 mm pitch must produce ~4× the scan lines on A2.
    a6 = _render_scanlines(120 / 105.0)
    a2 = _render_scanlines(120 / 420.0)
    assert a2.count("<polyline") > a6.count("<polyline")


def test_mm_options_fall_back_to_a4_reference_without_a_scale() -> None:
    # No px_per_mm → the raster long side maps onto an A4 long side
    # (297 mm), so a 2 mm pitch on a 120 px raster ≈ 0.808 px → floored
    # to 1 px steps. The render must succeed, not require the scale.
    svg = _render_scanlines(None)
    assert "<polyline" in svg


# ── /rerender endpoint plumbing ──────────────────────────────────────


@pytest.fixture()
def client():
    yield TestClient(app)


@pytest.fixture(autouse=True)
def _reset_cache():
    rerender_module._clear_cache_for_tests()
    yield
    rerender_module._clear_cache_for_tests()


def _seed_scanlines_cache(job_id: str = "mm-job") -> str:
    labels = np.zeros((64, 64), dtype=np.intp)
    palette = np.array([[0, 0, 0]], dtype=np.uint8)
    seg = SegmentationResult(labels=labels, palette=palette, width=64, height=64)
    opts = BitmapOptions.model_validate(
        {
            "algorithm": "scanlines",
            "drop_background": False,
            "num_colors": 1,
            # 8 mm pitch so the 64 px test raster stays above the 1 px
            # spacing floor on the small format (A6: 8 mm ≈ 3.5 px) and
            # the density difference vs A2 (≈ 0.9 px → floored to 1) is
            # observable in the line count.
            "algorithm_options": {"spacing_mm": 8.0},
        }
    )
    rerender_module.remember_job(job_id, seg, opts)
    return job_id


def test_rerender_target_size_drives_line_density(client: TestClient) -> None:
    job_id = _seed_scanlines_cache()
    a6 = client.post(
        "/rerender",
        json={"job_id": job_id, "layers": [], "target_width_mm": 105, "target_height_mm": 148},
    )
    a2 = client.post(
        "/rerender",
        json={"job_id": job_id, "layers": [], "target_width_mm": 420, "target_height_mm": 594},
    )
    assert a6.status_code == 200
    assert a2.status_code == 200
    assert a2.json()["svg"].count("<polyline") > a6.json()["svg"].count("<polyline")


def test_rerender_without_target_size_keeps_working(client: TestClient) -> None:
    job_id = _seed_scanlines_cache()
    response = client.post("/rerender", json={"job_id": job_id, "layers": []})
    assert response.status_code == 200
    assert "<svg" in response.json()["svg"]


# ── /upload-time footprint stored on BitmapOptions ───────────────────


def test_options_target_size_feeds_the_scale_when_request_omits_it() -> None:
    # /upload and /preview persist the placement footprint on the options;
    # the classmethod wrapper falls back to it when no explicit px_per_mm
    # is given — so the very first render is already page-adapted.
    def render(target_w: float, target_h: float) -> str:
        opts = BitmapOptions.model_validate(
            {
                "algorithm": "scanlines",
                "drop_background": False,
                "num_colors": 1,
                "algorithm_options": {"spacing_mm": 8.0},
                "target_width_mm": target_w,
                "target_height_mm": target_h,
            }
        )
        svg, _ = BitmapConverter.render_from_segmentation(_solid_seg(64), opts)
        return svg

    a6 = render(105, 148)
    a2 = render(420, 594)
    assert a2.count("<polyline") > a6.count("<polyline")


def _png_bytes(width: int = 48, height: int = 48) -> bytes:
    image = Image.new("RGB", (width, height), (0, 0, 0))
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _reset_preview_cache():
    from pen_plotter.api import preview as preview_module

    preview_module._cache.clear()
    yield
    preview_module._cache.clear()


def test_preview_target_size_drives_line_density(client: TestClient) -> None:
    payload = _png_bytes()

    def line_count(target_w: float, target_h: float) -> int:
        response = client.post(
            "/preview",
            data={
                "algorithm": "scanlines",
                "options": json.dumps(
                    {
                        "num_colors": 1,
                        "drop_background": False,
                        "algorithm_options": {"spacing_mm": 8.0},
                        "target_width_mm": target_w,
                        "target_height_mm": target_h,
                    }
                ),
            },
            files={"file": ("solid.png", payload, "image/png")},
        )
        assert response.status_code == 200, response.text
        return response.json()["svg"].count("<polyline")

    assert line_count(420, 594) > line_count(105, 148)

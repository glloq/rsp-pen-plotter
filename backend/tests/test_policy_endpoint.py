"""HTTP smoke tests for /policy/resolve (roadmap C.2)."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport

from pen_plotter.main import app


@pytest.mark.asyncio
async def test_policy_resolve_returns_decision_for_fast_photo() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/policy/resolve",
            json={
                "source_kind": "bitmap_photo",
                "goal": "fast",
                "palette_mode": "machine_only",
                "available_colors_count": 4,
                "image_megapixels": 1.0,
                "layer_count_estimate": 4,
                "is_mono_pen_machine": False,
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["default_algorithm"] == "scanlines"
    assert body["quality_tier"] == "draft"
    assert body["segmentation_method"] == "fixed_palette"
    assert any(r["rule"] == "bitmap_photo.fast" for r in body["reasoning"])


@pytest.mark.asyncio
async def test_policy_resolve_validates_payload() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/policy/resolve",
            json={"source_kind": "not_a_real_kind"},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_policy_resolve_applies_hard_constraint_for_large_image() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/policy/resolve",
            json={
                "source_kind": "bitmap_illustration",
                "goal": "quality",
                "palette_mode": "machine_only",
                "available_colors_count": 2,
                "image_megapixels": 1.0,
                "layer_count_estimate": 4,
                "is_mono_pen_machine": False,
            },
        )
    body = response.json()
    # illustration/quality → centerline; available_colors_count=2 forces
    # the sparse-palette override down to scanlines. (bitmap_photo/quality
    # is now palette-friendly crosshatch and would not trip this.)
    assert body["default_algorithm"] == "scanlines"
    assert any(
        c["constraint"] == "sparse_palette" for c in body["hard_constraints_applied"]
    )

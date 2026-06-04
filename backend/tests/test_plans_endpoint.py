"""Tests for the resolved-plan traceability endpoint.

Generating G-code archives the resolved plan keyed by its hash. The
endpoint lets an operator (or a test) replay exactly what the engine
saw — useful for diagnosing "why did this layer come out wrong?".
"""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport

from pen_plotter.main import app

NS = (
    'xmlns="http://www.w3.org/2000/svg" '
    'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"'
)
SVG = (
    f'<svg {NS} viewBox="0 0 100 100">'
    '<g inkscape:label="red" stroke="#ff0000"><path d="M0 0 L50 0 L50 50"/></g></svg>'
)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_generate_returns_plan_hash_and_resolved_plan() -> None:
    """Every successful generate carries the snapshot back to the client."""
    async with _client() as client:
        response = await client.post(
            "/generate",
            json={
                "svg": SVG,
                "profile_name": "Custom CoreXY A3",
                "layers": [
                    {
                        "layer_id": "red",
                        "target_pen_slot": 0,
                        "drawing_speed_mm_s": 50.0,
                        "source_color": "#ff0000",
                        "color_label": "Red",
                        "pause_before": "auto",
                    }
                ],
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["plan_hash"], str)
    assert len(body["plan_hash"]) == 64  # SHA-256 hex
    assert body["resolved_plan"]["plan_hash"] == body["plan_hash"]
    assert body["resolved_plan"]["layers"][0]["drawing_speed_mm_s"] == 50.0


@pytest.mark.asyncio
async def test_preflight_returns_same_hash_as_generate() -> None:
    """Equal plans submitted to both endpoints MUST yield equal hashes.

    This is the contract that makes "did preflight and generate agree?"
    a one-liner to check (compare two strings) instead of inspecting
    the entire layer list.
    """
    plan = {
        "svg": SVG,
        "profile_name": "Custom CoreXY A3",
        "layers": [
            {
                "layer_id": "red",
                "target_pen_slot": 0,
                "drawing_speed_mm_s": 75.0,
                "source_color": "#ff0000",
                "color_label": "Red",
                "pause_before": "always",
            }
        ],
    }
    async with _client() as client:
        pre = await client.post("/preflight", json=plan)
        gen = await client.post("/generate", json=plan)
    assert pre.status_code == 200
    assert gen.status_code == 200
    assert pre.json()["plan_hash"] == gen.json()["plan_hash"]


@pytest.mark.asyncio
async def test_plans_endpoint_returns_archived_snapshot() -> None:
    """After generate, the snapshot is retrievable by its hash."""
    plan = {
        "svg": SVG,
        "profile_name": "Custom CoreXY A3",
        "layers": [{"layer_id": "red", "target_pen_slot": 0}],
    }
    async with _client() as client:
        gen = await client.post("/generate", json=plan)
        assert gen.status_code == 200
        plan_hash = gen.json()["plan_hash"]
        archived = await client.get(f"/plans/{plan_hash}")
    assert archived.status_code == 200
    body = archived.json()
    assert body["plan_hash"] == plan_hash
    assert body["layers"][0]["layer_id"] == "red"


@pytest.mark.asyncio
async def test_plans_endpoint_404_on_unknown_hash() -> None:
    async with _client() as client:
        response = await client.get("/plans/" + "0" * 64)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_generate_rejects_invalid_speed_with_400() -> None:
    """The application validator surfaces a clean 400 instead of a 500."""
    async with _client() as client:
        response = await client.post(
            "/generate",
            json={
                "svg": SVG,
                "profile_name": "Custom CoreXY A3",
                "layers": [
                    {"layer_id": "red", "drawing_speed_mm_s": -1.0},
                ],
            },
        )
    assert response.status_code == 400
    assert "drawing_speed_mm_s" in response.json()["message"]

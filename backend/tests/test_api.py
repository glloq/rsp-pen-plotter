import httpx
import pytest
from fastapi.testclient import TestClient
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
async def test_optimize_endpoint() -> None:
    async with _client() as client:
        response = await client.post("/optimize", json={"svg": SVG, "layers": []})
    assert response.status_code == 200
    body = response.json()
    assert "metrics" in body
    assert body["layers"][0]["layer_id"] == "red"


@pytest.mark.asyncio
async def test_optimize_invalid_svg_returns_400() -> None:
    async with _client() as client:
        response = await client.post("/optimize", json={"svg": "<svg><g></svg>"})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_generate_endpoint() -> None:
    async with _client() as client:
        response = await client.post(
            "/generate", json={"svg": SVG, "profile_name": "Custom CoreXY A3"}
        )
    assert response.status_code == 200
    assert "G21" in response.json()["gcode"]


@pytest.mark.asyncio
async def test_generate_unknown_profile_returns_404() -> None:
    async with _client() as client:
        response = await client.post("/generate", json={"svg": SVG, "profile_name": "nope"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_plotter_status_and_jog_guard() -> None:
    async with _client() as client:
        status = await client.get("/plotter/status")
        jog = await client.post(
            "/plotter/jog",
            json={"dx_mm": 5, "dy_mm": 0, "profile_name": "Custom CoreXY A3"},
        )
    assert status.status_code == 200
    assert status.json()["connected"] is False
    assert jog.status_code == 409  # not connected


def test_plotter_websocket_sends_initial_status() -> None:
    with TestClient(app) as client, client.websocket_connect("/ws/plotter") as ws:
        message = ws.receive_json()
        assert "state" in message
        assert "connected" in message

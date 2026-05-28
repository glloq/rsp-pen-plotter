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
async def test_generate_routes_through_ir_when_flag_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``/generate`` routes via ``generate_gcode_from_geometry`` when
    ``OMNIPLOT_IR_ENABLED=1`` for GRBL/Marlin dialects."""
    monkeypatch.setenv("OMNIPLOT_IR_ENABLED", "1")
    calls: list[str] = []
    from pen_plotter.application import generate_service
    from pen_plotter.core import gcode as gcode_mod

    original = gcode_mod.generate_gcode_from_geometry

    def _spy(*args: object, **kwargs: object) -> object:
        calls.append("ir-generate")
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(gcode_mod, "generate_gcode_from_geometry", _spy)
    monkeypatch.setattr(
        generate_service, "generate_gcode_from_geometry", _spy, raising=False
    )

    async with _client() as client:
        response = await client.post(
            "/generate", json={"svg": SVG, "profile_name": "Custom CoreXY A3"}
        )
    assert response.status_code == 200
    assert calls == ["ir-generate"], f"expected IR generate path, got {calls!r}"


@pytest.mark.asyncio
async def test_optimize_routes_through_ir_when_flag_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With ``OMNIPLOT_IR_ENABLED=1`` the endpoint calls
    :func:`optimize_geometry_ir` instead of the legacy SVG path."""
    monkeypatch.setenv("OMNIPLOT_IR_ENABLED", "1")
    calls: list[str] = []
    from pen_plotter.api import optimize as optimize_mod

    original_ir = optimize_mod.optimize_geometry_ir
    original_svg = optimize_mod.optimize_svg

    def _spy_ir(*args: object, **kwargs: object) -> object:
        calls.append("ir")
        return original_ir(*args, **kwargs)  # type: ignore[arg-type]

    def _spy_svg(*args: object, **kwargs: object) -> object:
        calls.append("svg")
        return original_svg(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(optimize_mod, "optimize_geometry_ir", _spy_ir)
    monkeypatch.setattr(optimize_mod, "optimize_svg", _spy_svg)

    async with _client() as client:
        response = await client.post("/optimize", json={"svg": SVG, "layers": []})
    assert response.status_code == 200
    assert calls == ["ir"], (
        f"expected IR path under OMNIPLOT_IR_ENABLED=1, got {calls!r}"
    )


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
async def test_generate_refuses_missing_pen_slot_by_default() -> None:
    """/generate must refuse to ship G-code that asks for an absent pen.

    The response surfaces the missing slot list in a machine-readable
    shape so the UI can prompt the operator instead of letting the
    plotter stall on an M0 that nobody can satisfy.
    """
    async with _client() as client:
        response = await client.post(
            "/generate",
            json={
                "svg": SVG,
                "profile_name": "Custom CoreXY A3",
                "layers": [{"layer_id": "red", "target_pen_slot": 99}],
            },
        )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["reason"] == "missing_pen_slots"
    assert detail["slots"] == [99]
    assert "99" in detail["message"]


@pytest.mark.asyncio
async def test_generate_allows_missing_pen_slot_with_override() -> None:
    """``allow_missing_slots=True`` is the deliberate operator override."""
    async with _client() as client:
        response = await client.post(
            "/generate",
            json={
                "svg": SVG,
                "profile_name": "Custom CoreXY A3",
                "layers": [{"layer_id": "red", "target_pen_slot": 99}],
                "allow_missing_slots": True,
            },
        )
    assert response.status_code == 200
    assert "G21" in response.json()["gcode"]


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

import httpx
import pytest
from httpx import ASGITransport

from pen_plotter.hardware.controller import controller
from pen_plotter.hardware.transport import MockTransport
from pen_plotter.main import app


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_macro_crud_roundtrip() -> None:
    async with _client() as client:
        created = await client.post(
            "/macros",
            json={"name": "Park", "description": "go home", "commands": ["$H", "M280 P0 S40"]},
        )
        assert created.status_code == 200
        assert created.json()["commands"] == ["$H", "M280 P0 S40"]

        listed = await client.get("/macros")
        assert "Park" in {m["name"] for m in listed.json()}

        deleted = await client.request("DELETE", "/macros/Park")
        assert deleted.status_code == 200
        assert deleted.json() == {"deleted": "Park"}

        missing = await client.request("DELETE", "/macros/Park")
        assert missing.status_code == 404


@pytest.mark.asyncio
async def test_run_macro_sends_commands_when_connected() -> None:
    transport = MockTransport()
    controller.attach(transport)
    try:
        async with _client() as client:
            await client.post("/macros", json={"name": "Wiggle", "commands": ["G91", "G90"]})
            response = await client.post("/macros/Wiggle/run")
        assert response.status_code == 200
        assert "G91" in transport.written
        assert "G90" in transport.written
    finally:
        controller.abort()
        controller._transport = None
        controller._streamer = None
        controller._task = None


@pytest.mark.asyncio
async def test_run_macro_when_disconnected_returns_409() -> None:
    async with _client() as client:
        await client.post("/macros", json={"name": "Solo", "commands": ["$H"]})
        response = await client.post("/macros/Solo/run")
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_run_unknown_macro_returns_404() -> None:
    async with _client() as client:
        response = await client.post("/macros/nope/run")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_macro_name_with_slash_is_rejected() -> None:
    async with _client() as client:
        response = await client.post(
            "/macros", json={"name": "home/park", "commands": ["$H"]}
        )
    assert response.status_code == 422

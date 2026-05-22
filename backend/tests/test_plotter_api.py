import httpx
import pytest
from httpx import ASGITransport

from pen_plotter.hardware.controller import controller
from pen_plotter.hardware.transport import MockTransport
from pen_plotter.main import app

PROFILE = "Custom CoreXY A3"


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


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


@pytest.mark.asyncio
async def test_jog_when_connected_returns_200(connected: MockTransport) -> None:
    async with _client() as client:
        response = await client.post(
            "/plotter/jog", json={"dx_mm": 5, "dy_mm": -2, "profile_name": PROFILE}
        )
    assert response.status_code == 200
    assert response.json()["connected"] is True
    assert any("X5.000 Y-2.000" in line for line in connected.written)


@pytest.mark.asyncio
async def test_jog_unknown_profile_returns_404(connected: MockTransport) -> None:
    async with _client() as client:
        response = await client.post(
            "/plotter/jog", json={"dx_mm": 1, "dy_mm": 1, "profile_name": "nope"}
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_goto_when_connected_returns_200(connected: MockTransport) -> None:
    async with _client() as client:
        response = await client.post(
            "/plotter/goto", json={"x_mm": 20, "y_mm": 30, "profile_name": PROFILE}
        )
    assert response.status_code == 200
    assert any("X20.000 Y30.000" in line for line in connected.written)


@pytest.mark.asyncio
async def test_home_when_connected_returns_200(connected: MockTransport) -> None:
    async with _client() as client:
        response = await client.post("/plotter/home", params={"profile_name": PROFILE})
    assert response.status_code == 200
    assert "$H" in connected.written


@pytest.mark.asyncio
async def test_run_then_pause_resume_abort(connected: MockTransport) -> None:
    async with _client() as client:
        run = await client.post("/plotter/run", json={"gcode": "G0 X1\nG0 X2\n"})
        pause = await client.post("/plotter/pause")
        resume = await client.post("/plotter/resume")
        abort = await client.post("/plotter/abort")
    for response in (run, pause, resume, abort):
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_disconnect_clears_connection(connected: MockTransport) -> None:
    async with _client() as client:
        response = await client.post("/plotter/disconnect")
    assert response.status_code == 200
    assert response.json()["connected"] is False
    assert connected.closed is True

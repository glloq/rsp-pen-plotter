import httpx
import pytest
from httpx import ASGITransport

from pen_plotter.auth import API_KEY_ENV
from pen_plotter.hardware.controller import controller
from pen_plotter.hardware.transport import MockTransport
from pen_plotter.main import app

PROFILE = "Custom CoreXY A3"


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def connected() -> MockTransport:
    transport = MockTransport()
    controller.attach(transport)
    yield transport
    controller.abort()
    controller._transport = None
    controller._streamer = None
    controller._task = None


@pytest.fixture
def api_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = "secret-key"
    monkeypatch.setenv(API_KEY_ENV, key)
    return key


@pytest.mark.asyncio
async def test_machine_endpoint_open_without_configured_key(connected: MockTransport) -> None:
    async with _client() as client:
        response = await client.post("/plotter/home", params={"profile_name": PROFILE})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_machine_endpoint_rejects_missing_key(api_key: str, connected: MockTransport) -> None:
    async with _client() as client:
        response = await client.post("/plotter/home", params={"profile_name": PROFILE})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_machine_endpoint_accepts_header_key(api_key: str, connected: MockTransport) -> None:
    async with _client() as client:
        response = await client.post(
            "/plotter/home",
            params={"profile_name": PROFILE},
            headers={"X-API-Key": api_key},
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_machine_endpoint_accepts_token_query(api_key: str, connected: MockTransport) -> None:
    async with _client() as client:
        response = await client.post(
            "/plotter/home",
            params={"profile_name": PROFILE, "token": api_key},
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_preflight_not_guarded(api_key: str) -> None:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" viewBox="0 0 100 100">'
        '<g inkscape:label="red" stroke="#ff0000"><path d="M10 10 L90 90"/></g></svg>'
    )
    async with _client() as client:
        response = await client.post(
            "/preflight", json={"svg": svg, "profile_name": PROFILE}
        )
    assert response.status_code == 200

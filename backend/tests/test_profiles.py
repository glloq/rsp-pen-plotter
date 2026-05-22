import httpx
import pytest
from httpx import ASGITransport

from pen_plotter.main import app
from pen_plotter.profiles import get_profile, load_profiles


def test_load_profiles_includes_custom() -> None:
    names = {p.name for p in load_profiles()}
    assert "Custom CoreXY A3" in names


def test_get_profile_by_name() -> None:
    profile = get_profile("Custom CoreXY A3")
    assert profile is not None
    assert profile.pen_slot_count == 6
    assert profile.drawing_speed_mm_s == 60.0


def test_get_unknown_profile_returns_none() -> None:
    assert get_profile("does-not-exist") is None


@pytest.mark.asyncio
async def test_profiles_endpoint() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/profiles")
    assert response.status_code == 200
    names = {p["name"] for p in response.json()}
    assert "Custom CoreXY A3" in names

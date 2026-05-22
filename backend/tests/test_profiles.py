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


@pytest.mark.asyncio
async def test_get_export_and_import_roundtrip() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        single = await client.get("/profiles/Custom CoreXY A3")
        assert single.status_code == 200
        assert single.json()["pen_slot_count"] == 6

        exported = await client.get("/profiles/Custom CoreXY A3/export")
        assert exported.status_code == 200
        yaml_text = exported.text.replace("Custom CoreXY A3", "Imported Test Plotter")

        imported = await client.post("/profiles/import", json={"yaml": yaml_text})
        assert imported.status_code == 200
        assert imported.json()["name"] == "Imported Test Plotter"

        listed = await client.get("/profiles")
        assert "Imported Test Plotter" in {p["name"] for p in listed.json()}

        missing = await client.get("/profiles/nope")
        assert missing.status_code == 404


@pytest.mark.asyncio
async def test_import_invalid_returns_422() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/profiles/import", json={"yaml": "name: x\nunits: bogus"})
    assert response.status_code == 422

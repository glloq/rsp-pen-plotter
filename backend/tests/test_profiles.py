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


def _sample_profile(name: str) -> dict[str, object]:
    return {
        "name": name,
        "units": "mm",
        "workspace": {"x_min": 0.0, "y_min": 0.0, "x_max": 200.0, "y_max": 200.0},
        "origin": "bottom_left",
        "gcode_dialect": "grbl",
        "pen_up_command": "M280 P0 S40",
        "pen_down_command": "M280 P0 S90",
        "tool_change_method": "manual_pause",
        "tool_change_command": "M0",
        "drawing_speed_mm_s": 50.0,
        "travel_speed_mm_s": 100.0,
        "acceleration_mm_s2": 1000.0,
        "pen_slot_count": 3,
    }


@pytest.mark.asyncio
async def test_create_get_and_delete_roundtrip() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/profiles", json=_sample_profile("UI Test Plotter"))
        assert created.status_code == 200
        assert created.json()["pen_slot_count"] == 3

        fetched = await client.get("/profiles/UI Test Plotter")
        assert fetched.status_code == 200

        deleted = await client.request("DELETE", "/profiles/UI Test Plotter")
        assert deleted.status_code == 200
        assert deleted.json() == {"deleted": "UI Test Plotter"}

        missing = await client.get("/profiles/UI Test Plotter")
        assert missing.status_code == 404


@pytest.mark.asyncio
async def test_create_invalid_returns_422() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        bad = _sample_profile("Bad Plotter")
        bad["units"] = "bogus"
        response = await client.post("/profiles", json=bad)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_delete_unknown_returns_404() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.request("DELETE", "/profiles/does-not-exist")
    assert response.status_code == 404


def test_slug_colliding_names_do_not_clobber(tmp_path: object) -> None:
    from pathlib import Path

    from pen_plotter.models import MachineProfile
    from pen_plotter.profiles import delete_profile, load_profiles, save_profile

    directory = Path(str(tmp_path))
    base = _sample_profile("My Plotter")
    other = {**base, "name": "my-plotter"}  # same slug as "My Plotter"

    save_profile(MachineProfile.model_validate(base), directory=directory)
    save_profile(MachineProfile.model_validate(other), directory=directory)

    names = {p.name for p in load_profiles(directory=directory)}
    assert names == {"My Plotter", "my-plotter"}  # neither overwrote the other

    # Deleting one leaves the slug-colliding sibling intact.
    assert delete_profile("My Plotter", directory=directory) is True
    remaining = {p.name for p in load_profiles(directory=directory)}
    assert remaining == {"my-plotter"}


def test_delete_unicode_named_user_profile(tmp_path: object) -> None:
    from pathlib import Path

    from pen_plotter.models import MachineProfile
    from pen_plotter.profiles import delete_profile, save_profile

    directory = Path(str(tmp_path))
    save_profile(MachineProfile.model_validate(_sample_profile("日本語")), directory=directory)
    assert delete_profile("日本語", directory=directory) is True

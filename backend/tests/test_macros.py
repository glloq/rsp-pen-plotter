import httpx
import pytest
from httpx import ASGITransport

from pen_plotter.hardware.controller import controller
from pen_plotter.hardware.transport import MockTransport
from pen_plotter.macros import load_macros, save_macro
from pen_plotter.main import app
from pen_plotter.models import Macro


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
        response = await client.post("/macros", json={"name": "home/park", "commands": ["$H"]})
    assert response.status_code == 422


def test_corrupt_macros_file_is_quarantined_not_wiped(tmp_path) -> None:
    """Regression: a corrupt store used to silently read as ``{}``, so
    the very next save rewrote the file with one macro — destroying the
    operator's whole library. Now the broken file is moved aside (and a
    loud error logged) so the data stays recoverable."""
    path = tmp_path / "macros.json"
    corrupt = '{"definitely": "not a macro list'
    path.write_text(corrupt)

    assert load_macros(path) == []
    # The corrupt file was quarantined, not left in place / deleted.
    assert not path.exists()
    backups = list(tmp_path.glob("macros.json.corrupt-*"))
    assert len(backups) == 1
    assert backups[0].read_text() == corrupt

    # A subsequent save starts a fresh store without touching the backup.
    save_macro(Macro(name="Park", commands=["$H"]), path)
    assert [m.name for m in load_macros(path)] == ["Park"]
    assert backups[0].exists()
    assert backups[0].read_text() == corrupt


def test_write_all_is_atomic_and_leaves_no_temp_files(tmp_path) -> None:
    """Saves go through tempfile + os.replace (atomic swap); the temp
    file must not linger after a successful write."""
    path = tmp_path / "macros.json"
    save_macro(Macro(name="A", commands=["G90"]), path)
    save_macro(Macro(name="B", commands=["G91"]), path)

    assert sorted(m.name for m in load_macros(path)) == ["A", "B"]
    leftovers = [p for p in tmp_path.iterdir() if p != path]
    assert leftovers == [], f"temp files left behind: {leftovers}"

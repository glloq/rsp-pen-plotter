"""User-preset persistence + HTTP endpoint coverage."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

import pen_plotter.presets as presets_mod
from pen_plotter.main import app
from pen_plotter.presets import (
    PresetExistsError,
    PresetLimitError,
    PresetNotFoundError,
    delete_user_preset,
    list_presets,
    save_user_preset,
)


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test gets its own JSON store so they don't bleed into each other."""
    monkeypatch.setattr(presets_mod, "_STORE_PATH", tmp_path / "user_presets.json")


def test_save_then_list_includes_user_preset() -> None:
    save_user_preset("My fav", "personal", {"algorithm": "stippling"})
    names = [p.name for p in list_presets()]
    assert "My fav" in names
    mine = next(p for p in list_presets() if p.name == "My fav")
    assert mine.kind == "user"
    assert mine.options == {"algorithm": "stippling"}


def test_save_replaces_same_name() -> None:
    save_user_preset("X", "v1", {"algorithm": "a"})
    save_user_preset("X", "v2", {"algorithm": "b"})
    rows = [p for p in list_presets() if p.name == "X"]
    assert len(rows) == 1
    assert rows[0].description == "v2"
    assert rows[0].options == {"algorithm": "b"}


def test_cannot_overwrite_builtin() -> None:
    with pytest.raises(PresetExistsError):
        save_user_preset("Halftone", "no", {"algorithm": "x"})


def test_invalid_name_rejected() -> None:
    with pytest.raises(ValueError):
        save_user_preset("", "", {"a": 1})
    with pytest.raises(ValueError):
        save_user_preset("bad/<>", "", {"a": 1})


def test_delete_user_preset_removes_row() -> None:
    save_user_preset("Y", "", {"a": 1})
    delete_user_preset("Y")
    assert "Y" not in [p.name for p in list_presets()]


def test_delete_unknown_raises() -> None:
    with pytest.raises(PresetNotFoundError):
        delete_user_preset("nope")


def test_user_preset_limit_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(presets_mod, "_MAX_PRESETS", 2)
    save_user_preset("a", "", {"x": 1})
    save_user_preset("b", "", {"x": 2})
    with pytest.raises(PresetLimitError):
        save_user_preset("c", "", {"x": 3})


@pytest.mark.asyncio
async def test_http_save_and_delete_round_trip() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/presets",
            json={"name": "Roundtrip", "description": "via http", "options": {"algorithm": "x"}},
        )
        assert created.status_code == 201
        body = created.json()
        assert body["name"] == "Roundtrip"
        assert body["kind"] == "user"

        listed = await client.get("/presets")
        assert any(p["name"] == "Roundtrip" for p in listed.json())

        removed = await client.delete("/presets/Roundtrip")
        assert removed.status_code == 204

        listed2 = await client.get("/presets")
        assert not any(p["name"] == "Roundtrip" for p in listed2.json())


@pytest.mark.asyncio
async def test_http_overwrite_builtin_rejected() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/presets",
            json={"name": "Halftone", "description": "", "options": {}},
        )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_http_delete_unknown_returns_404() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.delete("/presets/nope")
    assert r.status_code == 404

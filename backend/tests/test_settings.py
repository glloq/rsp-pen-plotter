"""Tests for ``/settings/palette-source``.

Covers the default-on-empty path, round-trip via PUT, the validator
that rejects unknown source values, and the graceful-default behaviour
when the stored value is corrupt / out-of-enum.
"""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport

from pen_plotter.main import app
from pen_plotter.persistence import set_setting


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture(autouse=True)
def _reset_palette_source() -> None:
    """Wipe the stored palette source before each test so order doesn't matter."""
    set_setting("palette_source", "pens")
    yield


@pytest.mark.asyncio
async def test_default_palette_source_is_pens() -> None:
    """An unset / never-written setting reads back as the default ``pens``."""
    async with _client() as client:
        resp = await client.get("/settings/palette-source")
        assert resp.status_code == 200
        assert resp.json() == {"source": "pens"}


@pytest.mark.asyncio
async def test_put_persists_each_enum_value() -> None:
    """Every valid source can be written and read back identically."""
    async with _client() as client:
        for source in ("available", "union", "pens"):
            put = await client.put("/settings/palette-source", json={"source": source})
            assert put.status_code == 200
            assert put.json() == {"source": source}
            roundtrip = await client.get("/settings/palette-source")
            assert roundtrip.json() == {"source": source}


@pytest.mark.asyncio
async def test_put_rejects_unknown_source() -> None:
    """Pydantic Literal rejects anything outside the enum at validation time."""
    async with _client() as client:
        resp = await client.put(
            "/settings/palette-source", json={"source": "magazine"}
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_corrupt_stored_value_degrades_to_default() -> None:
    """A non-enum stored value reads back as the default rather than crashing.

    Lets a manual DB edit or a schema migration that retired a source
    fail gracefully — the UI gets a sane default, the operator can pick
    a real source from there.
    """
    set_setting("palette_source", "something-old-and-removed")
    async with _client() as client:
        resp = await client.get("/settings/palette-source")
        assert resp.status_code == 200
        assert resp.json() == {"source": "pens"}

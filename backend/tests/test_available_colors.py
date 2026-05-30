"""Tests for ``/available-colors`` CRUD.

Covers the wire shape (response keys), hex canonicalisation, dedup on
re-add, the rename-via-re-add path, position auto-assignment + reorder,
the 404 paths for unknown ids, and the 409 conflict when a PATCH would
move a row onto an existing hex.
"""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport

from pen_plotter.main import app
from pen_plotter.persistence import (
    delete_available_color,
    list_available_colors,
)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture(autouse=True)
def _clear_table() -> None:
    """Drop every row before each test so the shared SQLite DB stays isolated.

    The session-scoped ``_app_setup`` fixture creates the table once at
    session start; the autouse here ensures each test sees a fresh
    inventory regardless of run order.
    """
    for record in list_available_colors():
        delete_available_color(record.color_id)
    yield


@pytest.mark.asyncio
async def test_lifecycle_create_list_patch_delete() -> None:
    """Happy path: a colour can be created, listed, renamed, reordered, deleted."""
    async with _client() as client:
        created = await client.post(
            "/available-colors", json={"hex": "#e91e63", "name": "Crimson"}
        )
        assert created.status_code == 200
        payload = created.json()
        assert payload["hex"] == "#e91e63"
        assert payload["name"] == "Crimson"
        assert payload["position"] == 0
        color_id = payload["color_id"]

        listed = await client.get("/available-colors")
        assert listed.status_code == 200
        assert [c["color_id"] for c in listed.json()] == [color_id]

        renamed = await client.patch(
            f"/available-colors/{color_id}", json={"name": "Cherry Red"}
        )
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "Cherry Red"
        # Hex is unchanged when the patch only touches name.
        assert renamed.json()["hex"] == "#e91e63"

        moved = await client.patch(
            f"/available-colors/{color_id}", json={"position": 7}
        )
        assert moved.status_code == 200
        assert moved.json()["position"] == 7

        removed = await client.delete(f"/available-colors/{color_id}")
        assert removed.status_code == 200
        assert removed.json() == {"deleted": True}

        final = await client.get("/available-colors")
        assert final.json() == []


@pytest.mark.asyncio
async def test_hex_canonicalisation_and_dedup() -> None:
    """Re-adding the same colour via shorthand / mixed case returns the original.

    ``#ABC``, ``ABCABC``, ``#aabbcc`` must all collapse to ``#aabbcc`` so
    the unique index can't be fooled into accepting near-duplicates that
    would later confuse the picker.
    """
    async with _client() as client:
        first = await client.post(
            "/available-colors", json={"hex": "#ABC", "name": "Sky"}
        )
        assert first.status_code == 200
        first_id = first.json()["color_id"]
        assert first.json()["hex"] == "#aabbcc"

        # Shorthand + uppercase + missing-hash all dedup onto the first row.
        for shape in ("aabbcc", "#AABBCC", "#abc"):
            again = await client.post(
                "/available-colors", json={"hex": shape, "name": ""}
            )
            assert again.status_code == 200
            assert again.json()["color_id"] == first_id

        listed = await client.get("/available-colors")
        assert len(listed.json()) == 1


@pytest.mark.asyncio
async def test_dedup_updates_name_when_supplied() -> None:
    """Re-adding with a new non-empty name rewrites the human label.

    Lets the operator fix a typo without going through PATCH: re-submit
    the same hex with the corrected label and the row updates in place.
    """
    async with _client() as client:
        original = await client.post(
            "/available-colors", json={"hex": "#222222", "name": "Blakk"}
        )
        original_id = original.json()["color_id"]

        corrected = await client.post(
            "/available-colors", json={"hex": "#222222", "name": "Black"}
        )
        assert corrected.json()["color_id"] == original_id
        assert corrected.json()["name"] == "Black"


@pytest.mark.asyncio
async def test_dedup_preserves_name_when_empty() -> None:
    """Re-adding with ``name=""`` must NOT wipe the existing label.

    The picker defaults to ``#000000`` with an empty name; if the
    operator happens to ``POST`` it against an inventory that already
    contains black, the existing row's name must stay intact — clearing
    a name needs to go through ``PATCH`` explicitly. Regression guard
    for the "ajouter une couleur supprime la première" bug.
    """
    async with _client() as client:
        original = await client.post(
            "/available-colors", json={"hex": "#000000", "name": "Black"}
        )
        original_id = original.json()["color_id"]

        echo = await client.post(
            "/available-colors", json={"hex": "#000000", "name": ""}
        )
        assert echo.json()["color_id"] == original_id
        assert echo.json()["name"] == "Black"


@pytest.mark.asyncio
async def test_invalid_hex_returns_422() -> None:
    """Pydantic validation rejects payloads that aren't ``#rgb`` / ``#rrggbb``."""
    async with _client() as client:
        # Wrong length, garbage characters, none of these should reach
        # the DB layer — they'd violate the unique-index canonical shape.
        for bad in ("not a colour", "#12", "#12345", "#xyz", "#1234567"):
            resp = await client.post(
                "/available-colors", json={"hex": bad, "name": ""}
            )
            assert resp.status_code == 422, f"expected 422 for hex={bad!r}, got {resp.status_code}"


@pytest.mark.asyncio
async def test_stroke_width_default_create_and_patch() -> None:
    """stroke_width_mm defaults to a fineliner, round-trips on create, and PATCHes."""
    async with _client() as client:
        # Default applied when the create body omits the width.
        defaulted = await client.post("/available-colors", json={"hex": "#111111"})
        assert defaulted.status_code == 200
        assert defaulted.json()["stroke_width_mm"] == 0.5

        # Explicit width on create round-trips.
        created = await client.post(
            "/available-colors", json={"hex": "#222222", "stroke_width_mm": 0.7}
        )
        assert created.status_code == 200
        color_id = created.json()["color_id"]
        assert created.json()["stroke_width_mm"] == 0.7

        # PATCH updates only the width, leaving the rest untouched.
        patched = await client.patch(
            f"/available-colors/{color_id}", json={"stroke_width_mm": 1.2}
        )
        assert patched.status_code == 200
        assert patched.json()["stroke_width_mm"] == 1.2
        assert patched.json()["hex"] == "#222222"

        # Re-posting an existing hex with a different width updates it.
        repost = await client.post(
            "/available-colors", json={"hex": "#222222", "stroke_width_mm": 0.3}
        )
        assert repost.status_code == 200
        assert repost.json()["stroke_width_mm"] == pytest.approx(0.3)

        # A non-positive width is rejected at the boundary.
        bad = await client.post(
            "/available-colors", json={"hex": "#333333", "stroke_width_mm": 0}
        )
        assert bad.status_code == 422


@pytest.mark.asyncio
async def test_odometer_defaults_increments_and_resets() -> None:
    """odometer_mm starts at 0, can be set via PATCH, and resets to 0."""
    async with _client() as client:
        created = await client.post("/available-colors", json={"hex": "#aabbcc"})
        assert created.status_code == 200
        color_id = created.json()["color_id"]
        assert created.json()["odometer_mm"] == 0.0

        # Accumulate some distance.
        acc = await client.patch(f"/available-colors/{color_id}", json={"odometer_mm": 1234.5})
        assert acc.status_code == 200
        assert acc.json()["odometer_mm"] == pytest.approx(1234.5)

        # Add more (frontend computes old + delta then sends the total).
        acc2 = await client.patch(
            f"/available-colors/{color_id}", json={"odometer_mm": 1234.5 + 500.0}
        )
        assert acc2.json()["odometer_mm"] == pytest.approx(1734.5)

        # Reset to zero.
        reset = await client.patch(f"/available-colors/{color_id}", json={"odometer_mm": 0})
        assert reset.status_code == 200
        assert reset.json()["odometer_mm"] == 0.0

        # Negative value rejected.
        bad = await client.patch(f"/available-colors/{color_id}", json={"odometer_mm": -1})
        assert bad.status_code == 422


@pytest.mark.asyncio
async def test_position_auto_increments() -> None:
    """Successive inserts get position 0, 1, 2, … so the swatch strip orders chronologically."""
    async with _client() as client:
        positions: list[int] = []
        for i, hex_value in enumerate(("#111111", "#222222", "#333333")):
            resp = await client.post(
                "/available-colors", json={"hex": hex_value, "name": f"chip{i}"}
            )
            positions.append(resp.json()["position"])
        assert positions == [0, 1, 2]


@pytest.mark.asyncio
async def test_patch_hex_to_existing_value_409s() -> None:
    """Moving entry A's hex onto entry B's hex must refuse with 409.

    Without this guard, the SQLite UNIQUE constraint on ``hex`` would
    fire as a 500. The endpoint detects the clash up front and returns
    a structured 409 the UI can branch on.
    """
    async with _client() as client:
        a = await client.post(
            "/available-colors", json={"hex": "#111111", "name": "A"}
        )
        b = await client.post(
            "/available-colors", json={"hex": "#222222", "name": "B"}
        )
        conflict = await client.patch(
            f"/available-colors/{a.json()['color_id']}",
            json={"hex": b.json()["hex"]},
        )
        assert conflict.status_code == 409
        assert "already used" in conflict.json()["detail"].lower()


@pytest.mark.asyncio
async def test_patch_unknown_id_returns_404() -> None:
    async with _client() as client:
        resp = await client.patch(
            "/available-colors/does-not-exist", json={"name": "nope"}
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_unknown_id_returns_404() -> None:
    async with _client() as client:
        resp = await client.delete("/available-colors/does-not-exist")
        assert resp.status_code == 404

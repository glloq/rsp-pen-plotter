"""Tests for the ``/gcode-files`` library CRUD + print launch.

Covers the wire shape, the save/list/rename/delete lifecycle, the 404
paths for unknown ids, the 422 on empty G-code, and that printing a
saved file enqueues a run linked back to the file via ``gcode_file_id``.
"""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport

from pen_plotter import queue as q
from pen_plotter.gcode_library import delete_gcode_file, list_gcode_files
from pen_plotter.main import app

# A profile seeded by the test environment (see ``tests/test_queue.py``).
PROFILE = "Custom CoreXY A3"
GCODE = "G21\nG90\nM3 S0\nG1 X10 Y10\nM3 S1000\nG1 X20 Y20\nM5\n"


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture(autouse=True)
def _clear_library() -> None:
    """Drop every saved file before each test so the shared DB stays isolated."""
    for record in list_gcode_files():
        delete_gcode_file(record.id)
    yield
    for record in list_gcode_files():
        delete_gcode_file(record.id)


@pytest.mark.asyncio
async def test_save_list_rename_delete() -> None:
    """Happy path: a program can be saved, listed, renamed and deleted."""
    async with _client() as client:
        created = await client.post(
            "/gcode-files",
            json={"name": "mon-dessin", "profile_name": PROFILE, "gcode": GCODE},
        )
        assert created.status_code == 200, created.text
        payload = created.json()
        assert payload["name"] == "mon-dessin"
        assert payload["profile_name"] == PROFILE
        assert payload["line_count"] == len(GCODE.splitlines())
        assert payload["size_bytes"] == len(GCODE.encode())
        # The list projection must not leak the (potentially huge) payload.
        assert "gcode" not in payload
        file_id = payload["id"]

        listed = await client.get("/gcode-files")
        assert listed.status_code == 200
        assert [f["id"] for f in listed.json()] == [file_id]

        renamed = await client.patch(f"/gcode-files/{file_id}", json={"name": "logo final"})
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "logo final"

        removed = await client.delete(f"/gcode-files/{file_id}")
        assert removed.status_code == 200
        assert removed.json() == {"deleted": True}
        assert (await client.get("/gcode-files")).json() == []


@pytest.mark.asyncio
async def test_length_by_color_round_trips() -> None:
    """Per-colour lengths sent at save time survive into the list projection."""
    lengths = {"#ff0000": 120.5, "#0000ff": 30.0}
    async with _client() as client:
        created = await client.post(
            "/gcode-files",
            json={
                "name": "inked",
                "profile_name": PROFILE,
                "gcode": GCODE,
                "length_mm_by_color": lengths,
            },
        )
        assert created.status_code == 200, created.text
        assert created.json()["length_mm_by_color"] == lengths

        listed = await client.get("/gcode-files")
        assert listed.json()[0]["length_mm_by_color"] == lengths


@pytest.mark.asyncio
async def test_length_by_color_defaults_to_empty() -> None:
    """Omitting the per-colour lengths stores an empty mapping, not null."""
    async with _client() as client:
        created = await client.post(
            "/gcode-files",
            json={"name": "plain", "profile_name": PROFILE, "gcode": GCODE},
        )
        assert created.status_code == 200, created.text
        assert created.json()["length_mm_by_color"] == {}


@pytest.mark.asyncio
async def test_empty_gcode_is_rejected() -> None:
    """Saving a blank program is a 422, not a useless empty row."""
    async with _client() as client:
        resp = await client.post(
            "/gcode-files",
            json={"name": "x", "profile_name": PROFILE, "gcode": "   \n  "},
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_unknown_ids_404() -> None:
    """Rename / delete / print of an unknown id all 404."""
    async with _client() as client:
        assert (await client.patch("/gcode-files/nope", json={"name": "x"})).status_code == 404
        assert (await client.delete("/gcode-files/nope")).status_code == 404
        assert (await client.post("/gcode-files/nope/print")).status_code == 404


@pytest.mark.asyncio
async def test_print_enqueues_a_linked_run() -> None:
    """Printing a saved file enqueues a run tagged with ``gcode_file_id``."""
    async with _client() as client:
        created = await client.post(
            "/gcode-files",
            json={"name": "to-print", "profile_name": PROFILE, "gcode": GCODE},
        )
        file_id = created.json()["id"]

        launched = await client.post(f"/gcode-files/{file_id}/print")
        assert launched.status_code == 200, launched.text
        run = launched.json()
        assert run["gcode_file_id"] == file_id
        assert run["name"] == "to-print"
        assert run["state"] == "queued"

        # The run is visible in the queue, still carrying the file link.
        queued = await client.get("/queue")
        match = [r for r in queued.json() if r["id"] == run["id"]]
        assert match and match[0]["gcode_file_id"] == file_id

        # Clean up the run we created in the shared queue DB.
        q.delete_run(run["id"])

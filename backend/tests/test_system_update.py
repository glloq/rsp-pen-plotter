"""Self-update safety: serialization, maintenance guard, process-group kill.

Covers the P1.9 / P1.10 / P1.11 guards on ``POST /system/update`` without
actually running ``update.sh`` — the guards fire before the script is spawned.
"""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport

from pen_plotter.api import system
from pen_plotter.main import app


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_version_endpoint_returns_200() -> None:
    async with _client() as client:
        resp = await client.get("/system/version")
    assert resp.status_code == 200
    assert "version" in resp.json()


@pytest.mark.asyncio
async def test_update_refused_while_machine_busy(monkeypatch: pytest.MonkeyPatch) -> None:
    """P1.10 — no rebuild/restart while a physical or disk op is in flight."""
    monkeypatch.setattr(system, "_machine_busy_reason", lambda: "a print is running")
    async with _client() as client:
        resp = await client.post("/system/update", json={})
    assert resp.status_code == 409
    assert "a print is running" in resp.json()["message"]


@pytest.mark.asyncio
async def test_update_refused_when_already_running(monkeypatch: pytest.MonkeyPatch) -> None:
    """P1.9 — a second concurrent update request is refused, not run twice."""
    monkeypatch.setattr(system, "_machine_busy_reason", lambda: None)
    lock = system._get_update_lock()
    await lock.acquire()
    try:
        async with _client() as client:
            resp = await client.post("/system/update", json={})
        assert resp.status_code == 409
        assert "already running" in resp.json()["message"]
    finally:
        lock.release()


def test_update_flock_is_exclusive(tmp_path) -> None:
    """P1.9 — the cross-process flock only lets one holder in at a time."""
    first = system._try_acquire_update_flock(tmp_path)
    assert first is not None
    try:
        assert system._try_acquire_update_flock(tmp_path) is None  # already held
    finally:
        system._release_update_flock(first)
    # Released → acquirable again.
    again = system._try_acquire_update_flock(tmp_path)
    assert again is not None
    system._release_update_flock(again)


def test_machine_busy_reason_flags_running_print(monkeypatch: pytest.MonkeyPatch) -> None:
    from pen_plotter.api.queue import print_queue

    monkeypatch.setattr(print_queue, "_current_id", "run-x")
    assert system._machine_busy_reason() == "a print is running"



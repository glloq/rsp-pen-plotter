"""Tests for the SSE progressive-preview endpoint (roadmap C.7)."""

from __future__ import annotations

import json

import httpx
import pytest
from httpx import ASGITransport

from pen_plotter.main import app


def _parse_sse(text: str) -> list[dict[str, object]]:
    """Tokenize an SSE response into individual events."""
    out: list[dict[str, object]] = []
    current_event: str | None = None
    current_data: str | None = None
    for raw in text.splitlines():
        if raw.startswith("event:"):
            current_event = raw.split(":", 1)[1].strip()
        elif raw.startswith("data:"):
            current_data = raw.split(":", 1)[1].strip()
        elif raw == "" and current_event is not None and current_data is not None:
            out.append({"event": current_event, "data": json.loads(current_data)})
            current_event = current_data = None
    return out


@pytest.mark.asyncio
async def test_preview_stream_emits_start_progress_done() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/preview/stream?layer_count=3")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = _parse_sse(response.text)
    kinds = [e["event"] for e in events]
    assert kinds == ["start", "progress", "progress", "progress", "done"]


@pytest.mark.asyncio
async def test_preview_stream_payload_shape() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/preview/stream?layer_count=2")
        events = _parse_sse(response.text)
    # start carries layer_count.
    start = events[0]["data"]
    assert isinstance(start, dict)
    assert start["payload"]["layer_count"] == 2  # type: ignore[index]
    assert start["sequence"] == 0  # type: ignore[index]
    # progress events carry layer_index + percent.
    progress = events[1]["data"]
    assert isinstance(progress, dict)
    assert progress["payload"]["layer_index"] == 0  # type: ignore[index]
    assert progress["payload"]["percent"] == 50  # type: ignore[index]
    # sequence is monotonic.
    seqs = [e["data"]["sequence"] for e in events]  # type: ignore[index]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)


@pytest.mark.asyncio
async def test_preview_stream_validates_layer_count() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/preview/stream?layer_count=0")
    assert response.status_code == 422

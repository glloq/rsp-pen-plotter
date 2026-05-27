"""Server-Sent Events surface for progressive previews (roadmap C.7).

Audit #1 §6 + audit #7 §4 call out the v0.1 "request-response" preview
as a UX bottleneck: a heavy algorithm freezes the UI until the final
SVG is ready. C.7 introduces the **streaming contract** the v0.2
modal will consume — chunked progress events with a stable schema,
so the frontend can render a progress bar, partial previews, and
metric updates without waiting for the final result.

This commit ships the **endpoint scaffolding + event schema**, with
a synthetic emitter that demonstrates the protocol end to end (the
real `convert_file → segmentation → render` integration lands in a
follow-up that refactors the bitmap pipeline to yield progress as it
goes). The SSE protocol is stable; the upstream code path can be
swapped out without touching the frontend.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter()


class PreviewProgressEvent(BaseModel):
    """One event in the preview stream."""

    kind: Literal["start", "progress", "partial", "done", "error"]
    sequence: int = Field(ge=0)
    """Monotonic per-stream counter; the client uses it to detect drops."""

    elapsed_ms: int = Field(ge=0)
    """Wall-clock ms since the stream started."""

    payload: dict[str, Any] = Field(default_factory=dict)
    """Event-specific payload (layer index, percent, metric snapshot, …)."""


def _sse(event: PreviewProgressEvent) -> str:
    """Format one event as an SSE frame."""
    data = json.dumps(event.model_dump(mode="json"), separators=(",", ":"))
    return f"event: {event.kind}\ndata: {data}\n\n"


async def _synthetic_stream(layer_count: int) -> AsyncIterator[bytes]:
    """Yield a deterministic synthetic stream — one event per layer + bookends.

    Replaced by the real pipeline emitter in a follow-up PR; the shape
    of the events is the contract the frontend depends on.
    """
    seq = 0
    start_ms = 0
    yield _sse(
        PreviewProgressEvent(
            kind="start",
            sequence=seq,
            elapsed_ms=start_ms,
            payload={"layer_count": layer_count},
        )
    ).encode()
    seq += 1

    for i in range(layer_count):
        await asyncio.sleep(0)  # cooperative yield so the test harness can step
        yield _sse(
            PreviewProgressEvent(
                kind="progress",
                sequence=seq,
                elapsed_ms=10 * (i + 1),
                payload={
                    "layer_index": i,
                    "percent": int(((i + 1) / layer_count) * 100),
                },
            )
        ).encode()
        seq += 1

    yield _sse(
        PreviewProgressEvent(
            kind="done",
            sequence=seq,
            elapsed_ms=10 * (layer_count + 1),
            payload={"layer_count": layer_count},
        )
    ).encode()


@router.get("/preview/stream")
async def preview_stream(
    layer_count: int = Query(default=4, ge=1, le=64),
) -> StreamingResponse:
    """Open a Server-Sent Events stream emitting progress events.

    The v0.2 modal will subscribe to this endpoint when the operator
    leaves the Intent step; the events drive a per-layer progress bar
    and the partial preview frame. The synthetic emitter is a
    placeholder until the bitmap pipeline yields directly.
    """
    return StreamingResponse(
        _synthetic_stream(layer_count),
        media_type="text/event-stream",
        headers={
            # Disable proxies' buffering so events land promptly.
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

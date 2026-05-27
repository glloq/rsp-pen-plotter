"""Server-Sent Events surface for progressive previews (roadmap C.7).

Audit #1 §6 + audit #7 §4 call out the v0.1 "request-response" preview
as a UX bottleneck: a heavy algorithm freezes the UI until the final
SVG is ready. C.7 introduces the **streaming contract** the v0.2
modal will consume — chunked progress events with a stable schema,
so the frontend can render a progress bar, partial previews, and
metric updates without waiting for the final result.

When ``file_id`` is provided, the endpoint runs the **real** pipeline
(``convert_file → segmentation → render``) and yields one progress
event per rendered layer, plus a final ``done`` event carrying the
sanitized SVG. When no ``file_id`` is given, the endpoint falls back
to a deterministic synthetic emitter — useful for the frontend test
harness and for showcasing the protocol without a real upload.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from queue import Queue
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
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


async def _real_stream(file_id: str) -> AsyncIterator[bytes]:
    """Run the real pipeline in a worker thread, bridging progress to SSE.

    The bitmap pipeline is synchronous and CPU-bound, so we run it on
    a thread and use a bounded queue as the bridge: the pipeline
    pushes ``(index, total, label)`` tuples from its
    ``progress_callback``, while the async generator drains them and
    formats SSE frames. A sentinel ``None`` signals completion (or
    error) and lets the loop drain any final state without polling.
    """
    from pen_plotter.application import file_library
    from pen_plotter.persistence import get_file_record

    record = get_file_record(file_id)
    raw = file_library.read_original_bytes(file_id)
    if record is None or raw is None:
        raise HTTPException(status_code=404, detail=f"unknown file_id {file_id!r}")

    loop = asyncio.get_event_loop()
    start_ts = loop.time()
    queue: Queue[tuple[str, dict[str, Any]] | None] = Queue()

    def progress(i: int, total: int, label: str) -> None:
        queue.put(
            (
                "progress",
                {
                    "layer_index": i - 1,
                    "layer_label": label,
                    "percent": int((i / max(total, 1)) * 100),
                },
            )
        )

    def run() -> None:
        # Re-import inside the worker thread to avoid import-time cost
        # on the event loop. ``convert_file`` raises HTTPException on
        # converter failures; we relay them as `error` events.
        try:
            from pen_plotter.converters import pipeline

            result = pipeline.convert_file(
                raw,
                record.source_file,
                record.source_mime,
                progress_callback=progress,
            )
            queue.put(
                (
                    "done",
                    {
                        "svg": result.svg,
                        "layer_count": len(result.layers),
                        "warnings": result.warnings,
                    },
                )
            )
        except Exception as exc:  # noqa: BLE001 — relay to SSE client
            queue.put(("error", {"message": str(exc)}))
        finally:
            queue.put(None)

    seq = 0
    yield _sse(
        PreviewProgressEvent(
            kind="start",
            sequence=seq,
            elapsed_ms=0,
            payload={"file_id": file_id, "source_mime": record.source_mime},
        )
    ).encode()
    seq += 1

    task = asyncio.create_task(asyncio.to_thread(run))
    try:
        while True:
            item = await loop.run_in_executor(None, queue.get)
            if item is None:
                break
            kind, payload = item
            elapsed = int((loop.time() - start_ts) * 1000)
            yield _sse(
                PreviewProgressEvent(
                    kind=kind,  # type: ignore[arg-type]
                    sequence=seq,
                    elapsed_ms=elapsed,
                    payload=payload,
                )
            ).encode()
            seq += 1
    finally:
        await task


@router.get("/preview/stream")
async def preview_stream(
    layer_count: int = Query(default=4, ge=1, le=64),
    file_id: str | None = Query(default=None),
) -> StreamingResponse:
    """Open a Server-Sent Events stream emitting progress events.

    When ``file_id`` is set, runs the real pipeline against the
    matching library entry; otherwise falls back to the synthetic
    emitter (useful for tests and frontend smoke).
    """
    if file_id:
        body: AsyncIterator[bytes] = _real_stream(file_id)
    else:
        body = _synthetic_stream(layer_count)
    return StreamingResponse(
        body,
        media_type="text/event-stream",
        headers={
            # Disable proxies' buffering so events land promptly.
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

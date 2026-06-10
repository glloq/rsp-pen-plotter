import pytest
from sqlmodel import create_engine

from pen_plotter.core.resume import build_resume_program
from pen_plotter.hardware.controller import PlotterController
from pen_plotter.hardware.streamer import executable_lines
from pen_plotter.hardware.transport import MockTransport
from pen_plotter.persistence import init_db
from pen_plotter.profiles import get_profile
from pen_plotter.queue import (
    PrintQueue,
    RunState,
    _update,
    enqueue,
    get_run,
    list_runs,
    next_queued,
    recover_interrupted,
)

PROFILE = "Custom CoreXY A3"
GCODE = "G21\nG90\nG0 X1\nG1 X2 Y3 F600\nG1 X4 Y5\n"


def _engine():
    engine = create_engine("sqlite://")
    init_db(engine)
    return engine


def _queue(engine) -> tuple[PrintQueue, MockTransport]:
    controller = PlotterController()
    transport = MockTransport()
    controller.attach(transport)
    return PrintQueue(controller, engine), transport


class _StuckTransport:
    """Acks ``ok_budget`` lines then goes silent, simulating a wedged firmware."""

    def __init__(self, ok_budget: int = 2) -> None:
        self.written: list[str] = []
        self.raw: list[bytes] = []
        self._budget = ok_budget

    async def write_line(self, line: str) -> None:
        self.written.append(line)

    async def read_line(self) -> str:
        if self._budget > 0:
            self._budget -= 1
            return "ok"
        import asyncio as _asyncio

        await _asyncio.sleep(3600)
        return "ok"

    async def write_raw(self, data: bytes) -> None:
        self.raw.append(data)

    async def drain_input(self, idle_timeout_s: float = 0.2) -> None:
        return

    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_emergency_stop_during_queued_run_does_not_kill_worker() -> None:
    """Regression: ``emergency_stop`` cancels the streaming task; the
    cancel must NOT propagate as ``CancelledError`` (a BaseException)
    through ``controller.stream`` and kill the queue worker — its
    ``except Exception`` would not catch it."""
    import asyncio

    engine = _engine()
    controller = PlotterController()
    transport = _StuckTransport(ok_budget=2)
    controller.attach(transport)
    queue = PrintQueue(controller, engine)

    gcode = "\n".join(f"G1 X{i}" for i in range(100))
    enqueue("job", PROFILE, gcode, target=engine)

    queue.start()
    # Let the queue pick up the run and get stuck on the 3rd line.
    await asyncio.sleep(0.1)
    assert queue._current_id is not None

    await controller.emergency_stop(get_profile(PROFILE))
    await asyncio.sleep(0.1)

    assert queue._loop_task is not None
    assert not queue._loop_task.done(), "Queue worker died after emergency_stop"
    assert transport.raw == [b"\x18"]
    await queue.stop()


def test_enqueue_records_total_lines() -> None:
    engine = _engine()
    run = enqueue("job", PROFILE, GCODE, target=engine)
    assert run.state == RunState.QUEUED
    assert run.total_lines == len(executable_lines(GCODE))


def test_next_queued_orders_by_priority() -> None:
    engine = _engine()
    enqueue("low", PROFILE, GCODE, priority=0, target=engine)
    high = enqueue("high", PROFILE, GCODE, priority=5, target=engine)
    assert next_queued(engine).id == high.id


@pytest.mark.asyncio
async def test_run_next_streams_to_completion() -> None:
    engine = _engine()
    run = enqueue("job", PROFILE, GCODE, target=engine)
    queue, transport = _queue(engine)

    ran = await queue.run_next()
    assert ran is True

    updated = get_run(run.id, engine)
    assert updated.state == RunState.COMPLETED
    assert updated.acked_lines == run.total_lines
    assert transport.written == executable_lines(GCODE)


@pytest.mark.asyncio
async def test_run_next_resumes_from_checkpoint() -> None:
    engine = _engine()
    run = enqueue("job", PROFILE, GCODE, target=engine)
    _update(run.id, engine, acked_lines=3, state=RunState.QUEUED)
    queue, transport = _queue(engine)

    await queue.run_next()

    expected = build_resume_program(GCODE, 3, get_profile(PROFILE))
    assert transport.written == expected
    assert get_run(run.id, engine).state == RunState.COMPLETED


@pytest.mark.asyncio
async def test_run_next_idle_when_disconnected() -> None:
    engine = _engine()
    enqueue("job", PROFILE, GCODE, target=engine)
    queue = PrintQueue(PlotterController(), engine)  # not connected
    assert await queue.run_next() is False


def test_recover_interrupted_marks_running_as_paused() -> None:
    engine = _engine()
    run = enqueue("job", PROFILE, GCODE, target=engine)
    _update(run.id, engine, state=RunState.RUNNING, acked_lines=2)

    assert recover_interrupted(engine) == 1
    recovered = get_run(run.id, engine)
    assert recovered.state == RunState.PAUSED
    assert recovered.acked_lines == 2


def test_resume_requeues_paused_run() -> None:
    engine = _engine()
    run = enqueue("job", PROFILE, GCODE, target=engine)
    _update(run.id, engine, state=RunState.PAUSED, acked_lines=2)
    queue, _ = _queue(engine)

    queue.resume(run.id)
    assert get_run(run.id, engine).state == RunState.QUEUED


@pytest.mark.asyncio
async def test_swap_pause_surfaces_as_paused_with_prompt() -> None:
    """A guided operator-confirm swap parks the streamer in WAITING; the
    queue must mirror that as a durable ``paused`` run carrying the prompt
    so the cockpit can show it and offer Resume."""
    import asyncio

    engine = _engine()
    gcode = "G21\nG90\n; Change to pen slot 1 (Red)\nM0\nG1 X2 Y3 F600\n"
    run = enqueue("job", PROFILE, gcode, target=engine)
    queue, transport = _queue(engine)

    task = asyncio.create_task(queue.run_next())
    # Wait until the streamer parks for the swap and the queue reflects it.
    for _ in range(50):
        await asyncio.sleep(0)
        current = get_run(run.id, engine)
        if current.state == RunState.PAUSED and current.swap_prompt:
            break
    paused = get_run(run.id, engine)
    assert paused.state == RunState.PAUSED
    assert paused.swap_prompt == "Insert pen slot 1: Red"

    # Resuming routes back through the controller and lets streaming finish;
    # the prompt is cleared once the run completes.
    queue.resume(run.id)
    await asyncio.wait_for(task, timeout=2.0)
    done = get_run(run.id, engine)
    assert done.state == RunState.COMPLETED
    assert done.swap_prompt is None


def test_enqueue_computes_guided_pause_points() -> None:
    engine = _engine()
    # A program with a tool-change comment + M0 yields one guided pause.
    gcode = "G21\nG90\n; Change to pen slot 1 (Red)\nM0\nG1 X2 Y3 F600\n"
    run = enqueue("job", PROFILE, gcode, target=engine)
    # The M0 is the 3rd executable line (index 2).
    assert run.pause_points == {"2": "Insert pen slot 1: Red"}


def test_enqueue_is_idempotent_with_key() -> None:
    engine = _engine()
    a = enqueue("job", PROFILE, GCODE, idempotency_key="k1", target=engine)
    b = enqueue("job", PROFILE, GCODE, idempotency_key="k1", target=engine)
    assert a.id == b.id
    assert len(list_runs(engine)) == 1


def test_enqueue_without_key_allows_duplicates() -> None:
    engine = _engine()
    enqueue("job", PROFILE, GCODE, target=engine)
    enqueue("job", PROFILE, GCODE, target=engine)
    assert len(list_runs(engine)) == 2


def test_cancel_queued_run() -> None:
    engine = _engine()
    run = enqueue("job", PROFILE, GCODE, target=engine)
    queue, _ = _queue(engine)

    queue.cancel(run.id)
    assert get_run(run.id, engine).state == RunState.CANCELED


def test_next_layer_boundary_finds_change_comment() -> None:
    """Skip-layer recovery: ``_next_layer_boundary`` locates the
    executable index of the line that starts the next layer."""
    from pen_plotter.queue import _next_layer_boundary

    gcode = (
        "G21\nG90\n"
        "; layer-red\n"
        "G1 X1 Y1\nG1 X2 Y2\n"
        "; Change to pen slot 1 (Blue)\nM0\n"
        "G1 X3 Y3\n"
        "; Change pen: Green (#00ff00)\nM0\n"
        "G1 X4 Y4\n"
    )
    # Before any layer comment was seen → first boundary is at index 2
    # ("red" layer body starts at executable line 2).
    assert _next_layer_boundary(gcode, 0) == (2, "red")
    # From inside the red layer (exec=2) → next is the slot-1 swap at
    # executable line 4.
    assert _next_layer_boundary(gcode, 2) == (4, "1")
    # No further boundary past the last layer.
    assert _next_layer_boundary(gcode, 10) is None


@pytest.mark.asyncio
async def test_run_next_skips_layer_on_recoverable_failure(monkeypatch) -> None:
    """When the profile's ``recovery_policy=skip_layer`` and the
    streamer raises ``StreamError``, the run is re-queued past the
    next layer boundary and the skipped label is recorded."""
    from pen_plotter import queue as queue_module
    from pen_plotter.domain.capability import (
        MachineCapabilities,
        RecoveryPolicy,
        ToolChangeStrategy,
        ToolingMode,
    )
    from pen_plotter.hardware.streamer import StreamError
    from pen_plotter.queue import _update

    engine = _engine()
    multi_layer = (
        "G21\nG90\n"
        "; layer-A\n"
        "G1 X1 Y1\n"
        "; layer-B\n"
        "G1 X2 Y2\n"
        "; layer-C\n"
        "G1 X3 Y3\n"
    )
    run = enqueue("job", PROFILE, multi_layer, target=engine)

    base = get_profile(PROFILE)
    assert base is not None
    base.capabilities = MachineCapabilities(
        tool_change=ToolChangeStrategy(
            mode=ToolingMode.MANUAL,
            command_source="operator",
            recovery_policy=RecoveryPolicy.SKIP_LAYER,
            manual_prompt=None,
            host_macro=[],
        ),
    )
    monkeypatch.setattr(queue_module, "get_profile", lambda name: base)

    queue, _transport = _queue(engine)

    async def _boom(*_args: object, **_kwargs: object) -> object:
        raise StreamError("simulated firmware reject")

    queue._controller.stream = _boom  # type: ignore[assignment]
    _update(run.id, engine, acked_lines=2)

    await queue.run_next()

    updated = get_run(run.id, engine)
    assert updated is not None
    assert updated.state == RunState.QUEUED
    assert updated.acked_lines > 2
    assert updated.skipped_layers
    assert "simulated firmware reject" in (updated.error or "")


def _skip_layer_profile(monkeypatch):
    """Patch the queue module's profile lookup to a skip_layer policy."""
    from pen_plotter import queue as queue_module
    from pen_plotter.domain.capability import (
        MachineCapabilities,
        RecoveryPolicy,
        ToolChangeStrategy,
        ToolingMode,
    )

    base = get_profile(PROFILE)
    assert base is not None
    base.capabilities = MachineCapabilities(
        tool_change=ToolChangeStrategy(
            mode=ToolingMode.MANUAL,
            command_source="operator",
            recovery_policy=RecoveryPolicy.SKIP_LAYER,
            manual_prompt=None,
            host_macro=[],
        ),
    )
    monkeypatch.setattr(queue_module, "get_profile", lambda name: base)
    return base


@pytest.mark.asyncio
async def test_skip_layer_uses_live_checkpoint_not_stale_snapshot(monkeypatch) -> None:
    """Regression: when ``StreamError`` fires mid-run, the skip-layer
    boundary must be computed from the LIVE acked count reported by the
    streamer's progress callbacks — not from the ``run`` row snapshot
    loaded before streaming started. The stale snapshot would re-queue
    the run at a too-early boundary, physically re-plotting layers that
    are already inked (and recording the wrong skipped label)."""
    from pen_plotter.hardware.streamer import StreamError, StreamProgress, StreamState

    engine = _engine()
    multi_layer = (
        "G21\nG90\n"  # exec 0, 1
        "; layer-A\n"
        "G1 X1 Y1\n"  # exec 2
        "; layer-B\n"
        "G1 X2 Y2\n"  # exec 3
        "; layer-C\n"
        "G1 X3 Y3\n"  # exec 4
    )
    run = enqueue("job", PROFILE, multi_layer, target=engine)
    assert run.acked_lines == 0  # the stale snapshot the bug acted on

    _skip_layer_profile(monkeypatch)
    queue, _transport = _queue(engine)

    async def _stream_then_fail(gcode, on_progress=None, **_kwargs):
        # Simulate the firmware acking 3 lines (into layer-B) before the
        # reject; the queue's checkpoint callback sees the live progress.
        assert on_progress is not None
        await on_progress(StreamProgress(total=5, sent=3, acked=3, state=StreamState.RUNNING))
        raise StreamError("reject mid layer-B")

    queue._controller.stream = _stream_then_fail  # type: ignore[assignment]

    await queue.run_next()

    updated = get_run(run.id, engine)
    assert updated is not None
    assert updated.state == RunState.QUEUED
    # Live checkpoint was exec 3 (inside layer-B) → next boundary is
    # layer-C at exec 4. The stale snapshot (acked_lines=0) would have
    # re-queued at exec 2 and recorded layer "A" as skipped.
    assert updated.acked_lines == 4
    assert updated.skipped_layers == ["C"]


@pytest.mark.asyncio
async def test_checkpoints_are_throttled_not_per_line(monkeypatch) -> None:
    """One SQLite commit per acked line stalls the event loop; the
    checkpoint callback must batch writes (every N lines / T seconds /
    state flips) while still persisting the final completion state."""
    from pen_plotter import queue as queue_module

    engine = _engine()
    gcode = "\n".join(f"G1 X{i}" for i in range(30))
    run = enqueue("job", PROFILE, gcode, target=engine)
    queue, _transport = _queue(engine)

    calls: list[dict] = []
    real_update = queue_module._update

    def counting_update(run_id, target, **fields):
        calls.append(fields)
        return real_update(run_id, target, **fields)

    monkeypatch.setattr(queue_module, "_update", counting_update)

    await queue.run_next()

    updated = get_run(run.id, engine)
    assert updated is not None
    assert updated.state == RunState.COMPLETED
    assert updated.acked_lines == run.total_lines
    # 30 acked lines must NOT produce ~30 row updates. Expected writes:
    # RUNNING flip, initial progress emit, DONE flip, final COMPLETED —
    # comfortably under 10 even with margin for time-based flushes.
    assert len(calls) < 10, f"checkpointing not throttled: {len(calls)} writes"


@pytest.mark.asyncio
async def test_run_next_requeues_on_runtime_error(monkeypatch) -> None:
    """``controller.stream`` can raise RuntimeError ("A job is already
    running" / "Not connected") after the run was flipped RUNNING — it
    must go back to QUEUED, not stay stranded (``next_queued`` only
    selects QUEUED rows)."""
    engine = _engine()
    run = enqueue("job", PROFILE, GCODE, target=engine)
    queue, _transport = _queue(engine)

    async def _busy(*_args, **_kwargs):
        raise RuntimeError("A job is already running.")

    queue._controller.stream = _busy  # type: ignore[assignment]

    assert await queue.run_next() is True
    updated = get_run(run.id, engine)
    assert updated is not None
    assert updated.state == RunState.QUEUED


@pytest.mark.asyncio
async def test_run_next_fails_run_on_unexpected_error(monkeypatch) -> None:
    """A non-StreamError, non-RuntimeError failure marks the run FAILED
    with the error message instead of leaving it RUNNING forever."""
    engine = _engine()
    run = enqueue("job", PROFILE, GCODE, target=engine)
    queue, _transport = _queue(engine)

    async def _boom(*_args, **_kwargs):
        raise ValueError("unexpected kaboom")

    queue._controller.stream = _boom  # type: ignore[assignment]

    assert await queue.run_next() is True
    updated = get_run(run.id, engine)
    assert updated is not None
    assert updated.state == RunState.FAILED
    assert "unexpected kaboom" in (updated.error or "")


@pytest.mark.asyncio
async def test_queue_list_endpoint_returns_summaries_without_gcode() -> None:
    """GET /queue is polled every 3 s by the frontend — it must NOT ship
    the full ``gcode`` / ``pause_points`` / ``swap_actions`` payloads.
    The detail route keeps the full row for callers that need it."""
    import httpx
    from httpx import ASGITransport

    from pen_plotter.main import app

    client = httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    big_gcode = "\n".join(f"G1 X{i}" for i in range(200))
    async with client:
        created = await client.post(
            "/queue",
            json={"name": "shape-test", "profile_name": PROFILE, "gcode": big_gcode},
        )
        assert created.status_code == 200
        run_id = created.json()["id"]
        try:
            listed = await client.get("/queue")
            assert listed.status_code == 200
            items = [r for r in listed.json() if r["id"] == run_id]
            assert len(items) == 1
            item = items[0]
            assert "gcode" not in item
            assert "pause_points" not in item
            assert "swap_actions" not in item
            # Everything the queue store / cockpit consumes is present.
            for key in (
                "id",
                "name",
                "profile_name",
                "state",
                "priority",
                "total_lines",
                "acked_lines",
                "error",
                "swap_prompt",
                "skipped_layers",
                "created_at",
                "updated_at",
            ):
                assert key in item, f"summary missing {key!r}"

            detail = await client.get(f"/queue/{run_id}")
            assert detail.status_code == 200
            assert detail.json()["gcode"] == big_gcode
        finally:
            await client.delete(f"/queue/{run_id}")

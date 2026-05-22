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

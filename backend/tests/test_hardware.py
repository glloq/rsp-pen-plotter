import asyncio

import pytest

from pen_plotter.hardware.commands import goto_command, home_command, jog_command
from pen_plotter.hardware.controller import PlotterController
from pen_plotter.hardware.streamer import (
    GcodeStreamer,
    StreamError,
    StreamState,
    executable_lines,
)
from pen_plotter.hardware.transport import MockTransport
from pen_plotter.profiles import get_profile

GCODE = """; header
G21
G90
M280 P0 S40
G0 X10 Y10 ; move
M280 P0 S90
G1 X20 Y20 F3600

"""


def _profile():
    profile = get_profile("Custom CoreXY A3")
    assert profile is not None
    return profile


def test_executable_lines_strips_comments_and_blanks() -> None:
    lines = executable_lines(GCODE)
    assert lines == ["G21", "G90", "M280 P0 S40", "G0 X10 Y10", "M280 P0 S90", "G1 X20 Y20 F3600"]


@pytest.mark.asyncio
async def test_streamer_sends_all_lines_and_completes() -> None:
    transport = MockTransport()
    streamer = GcodeStreamer(transport)
    progress = await streamer.run(GCODE)
    assert progress.state == StreamState.DONE
    assert progress.total == 6
    assert progress.acked == 6
    assert transport.written == executable_lines(GCODE)


@pytest.mark.asyncio
async def test_streamer_reports_progress() -> None:
    transport = MockTransport()
    states: list[tuple[int, str]] = []

    async def on_progress(p):  # type: ignore[no-untyped-def]
        states.append((p.acked, p.state.value))

    await GcodeStreamer(transport, on_progress=on_progress).run("G0 X1\nG0 X2\n")
    assert states[-1] == (2, "done")


def test_jog_command_is_relative() -> None:
    lines = jog_command(5.0, -3.0, _profile())
    assert lines[0] == "G91"
    assert lines[-1] == "G90"
    assert "X5.000 Y-3.000" in lines[1]


def test_home_command_grbl() -> None:
    assert home_command(_profile()) == ["$H"]


def test_goto_command_is_absolute_and_lifts_pen() -> None:
    profile = _profile()
    lines = goto_command(12.5, 34.0, profile)
    assert lines[0] == "G90"
    assert profile.pen_up_command in lines
    assert "X12.500 Y34.000" in lines[-1]


@pytest.mark.asyncio
async def test_controller_runs_job_with_mock_transport() -> None:
    controller = PlotterController()
    transport = MockTransport()
    controller.attach(transport)
    assert controller.connected
    await controller.run("G0 X1\nG0 X2\n")
    await asyncio.sleep(0.05)
    assert controller.progress.state == StreamState.DONE
    assert transport.written == ["G0 X1", "G0 X2"]


@pytest.mark.asyncio
async def test_controller_jog_requires_connection() -> None:
    controller = PlotterController()
    with pytest.raises(RuntimeError):
        await controller.jog(1.0, 1.0, _profile())


class _SilentTransport:
    """Transport that records writes but never acknowledges, to test timeouts."""

    def __init__(self) -> None:
        self.written: list[str] = []
        self.raw: list[bytes] = []

    async def write_line(self, line: str) -> None:
        self.written.append(line)

    async def read_line(self) -> str:
        await asyncio.sleep(3600)
        return "ok"

    async def write_raw(self, data: bytes) -> None:
        self.raw.append(data)

    async def drain_input(self, idle_timeout_s: float = 0.2) -> None:
        return

    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_streamer_times_out_without_ack() -> None:
    streamer = GcodeStreamer(_SilentTransport(), ack_timeout_s=0.05)
    with pytest.raises(StreamError):
        await streamer.run("G0 X1\n")
    assert streamer.progress.state == StreamState.ERROR


@pytest.mark.asyncio
async def test_controller_rejects_jog_during_job() -> None:
    controller = PlotterController()
    controller.attach(_SilentTransport())  # never acks, so the job stays running
    await controller.run("G0 X1\nG0 X2\n")
    await asyncio.sleep(0.01)
    with pytest.raises(RuntimeError):
        await controller.jog(1.0, 1.0, _profile())
    controller.abort()


@pytest.mark.asyncio
async def test_send_immediate_serialises_concurrent_callers() -> None:
    """Two concurrent jog/goto callers must NOT interleave their writes
    or ack reads — ``_send_lock`` keeps each ``_send_immediate`` atomic."""
    from pen_plotter.hardware.transport import MockTransport

    controller = PlotterController()
    transport = MockTransport()
    controller.attach(transport)
    profile = _profile()

    # Fire two jogs in parallel — each emits 3 lines (G91, G1, G90).
    await asyncio.gather(
        controller.jog(1.0, 0.0, profile),
        controller.jog(2.0, 0.0, profile),
    )
    # The 6 writes must come out as two contiguous 3-line groups, not
    # interleaved. Look at the X coordinates of the G1 lines: they
    # bracket the G91/G90 of the same caller.
    assert len(transport.written) == 6
    # Each caller's triple is (G91, G1 X*, G90); the two triples are
    # contiguous when ordered, which means index 0 and 3 are G91.
    assert transport.written[0] == "G91"
    assert transport.written[2] == "G90"
    assert transport.written[3] == "G91"
    assert transport.written[5] == "G90"


@pytest.mark.asyncio
async def test_emergency_stop_writes_realtime_byte_and_cancels_task() -> None:
    """A long G1 that never acks cannot be cut short by ``abort()`` alone —
    ``emergency_stop`` writes the dialect byte directly and cancels the task."""
    controller = PlotterController()
    transport = _SilentTransport()
    controller.attach(transport)
    await controller.run("G1 X1000\n")
    await asyncio.sleep(0.01)

    await controller.emergency_stop(_profile())

    # The profile is grbl-dialect → ``0x18``.
    assert transport.raw == [b"\x18"]
    assert controller._task is None or controller._task.done()


@pytest.mark.asyncio
async def test_emergency_stop_marlin_sends_m112() -> None:
    """Dialect-aware payload: a Marlin profile must get ``M112\\n``."""
    from pen_plotter.models import MachineProfile

    profile = _profile()
    # Patch the dialect for this call (don't mutate the registry).
    marlin: MachineProfile = profile.model_copy(update={"gcode_dialect": "marlin"})

    controller = PlotterController()
    transport = _SilentTransport()
    controller.attach(transport)
    await controller.run("G1 X1000\n")
    await asyncio.sleep(0.01)
    await controller.emergency_stop(marlin)
    assert transport.raw == [b"M112\n"]


@pytest.mark.asyncio
async def test_pause_during_inline_swap_blocks_next_command() -> None:
    """Pausing while a host_timed swap is mid-sequence must halt before
    the next inline command, not silently continue."""
    from pen_plotter.hardware.streamer import SwapAction, SwapCommandLine
    from pen_plotter.hardware.transport import MockTransport

    transport = MockTransport()
    # Each command has a dwell so pause()/abort() have a chance to land
    # between iterations of the inline loop (with MockTransport's instant
    # ack, the loop would otherwise complete in one tick).
    swap = SwapAction(
        kind="host_timed",
        commands=[
            SwapCommandLine(send="M0_A", wait_ms=50),
            SwapCommandLine(send="M0_B", wait_ms=50),
            SwapCommandLine(send="M0_C", wait_ms=50),
        ],
    )
    streamer = GcodeStreamer(transport, swap_actions={0: swap})
    task = asyncio.create_task(streamer.run("G0 X1\n"))
    # Let the first swap command go out, then pause before the next.
    await asyncio.sleep(0.02)
    streamer.pause()
    await asyncio.sleep(0.2)
    # The swap shouldn't have completed — at least one of B/C is missing.
    assert "M0_C" not in transport.written
    streamer.resume()
    await asyncio.wait_for(task, timeout=1.0)
    assert "M0_A" in transport.written
    assert "M0_B" in transport.written
    assert "M0_C" in transport.written


@pytest.mark.asyncio
async def test_abort_preempts_swap_wait_ms() -> None:
    """A long inline ``wait_ms`` dwell must be cut by ``abort`` rather than
    blocking the whole sleep."""
    from pen_plotter.hardware.streamer import StreamState, SwapAction, SwapCommandLine
    from pen_plotter.hardware.transport import MockTransport

    transport = MockTransport()
    swap = SwapAction(
        kind="host_timed",
        commands=[SwapCommandLine(send="HOLD", wait_ms=10000)],
    )
    streamer = GcodeStreamer(transport, swap_actions={0: swap})
    task = asyncio.create_task(streamer.run("G0 X1\n"))
    await asyncio.sleep(0.02)
    t0 = asyncio.get_event_loop().time()
    streamer.abort()
    result = await asyncio.wait_for(task, timeout=1.0)
    # Should return well before the full 10s dwell.
    assert asyncio.get_event_loop().time() - t0 < 0.5
    assert result.state == StreamState.ABORTED


@pytest.mark.asyncio
async def test_run_with_profile_inserts_swap_actions() -> None:
    """A direct ``controller.run(gcode, profile=...)`` on a multi-pen G-code
    must halt at the swap boundary (operator_confirm), not blindly send the
    firmware pause."""
    from pen_plotter.hardware.streamer import StreamState
    from pen_plotter.hardware.transport import MockTransport

    controller = PlotterController()
    transport = MockTransport()
    controller.attach(transport)
    gcode = "G21\nG90\n; Change to pen slot 1 (Red)\nM0\nG1 X2 Y3 F600\n"
    await controller.run(gcode, profile=_profile())
    # Wait until the streamer parks for the swap (WAITING) or finishes.
    for _ in range(200):
        await asyncio.sleep(0)
        if controller.progress.state in (StreamState.WAITING, StreamState.DONE):
            break
    assert controller.progress.state == StreamState.WAITING
    # The firmware pause M0 was replaced by the operator-confirm action —
    # it must NOT have been sent to the transport.
    assert "M0" not in transport.written
    controller.abort()


@pytest.mark.asyncio
async def test_disconnect_does_not_block_on_unresponsive_firmware() -> None:
    """``disconnect`` must not wait for the streamer's ack timeout when
    the firmware never replies — it cancels the task instead."""
    controller = PlotterController()
    controller.attach(_SilentTransport())
    await controller.run("G1 X1\n")
    await asyncio.sleep(0.01)
    t0 = asyncio.get_event_loop().time()
    await controller.disconnect()
    # Well under the 30s ack_timeout_s.
    assert asyncio.get_event_loop().time() - t0 < 2.0
    assert controller.connected is False


@pytest.mark.asyncio
async def test_run_holds_send_lock_so_jog_cannot_race() -> None:
    """A ``run`` arriving while a jog is mid-flight must wait for the jog
    to finish before installing the streamer task — closes the TOCTOU
    between ``_require_idle`` and the first write."""
    from pen_plotter.hardware.transport import MockTransport

    controller = PlotterController()
    transport = MockTransport()
    controller.attach(transport)
    profile = _profile()

    # Issue a jog and a run together. The jog produces 3 lines; the run
    # adds 1 line. Order: jog's three (G91, G1, G90) MUST appear as a
    # contiguous block before the run's "G0 X9" — or after, but never
    # interleaved.
    await asyncio.gather(
        controller.jog(7.0, 0.0, profile),
        controller.run("G0 X9\n"),
    )
    # Wait for the streamer to drain.
    for _ in range(100):
        await asyncio.sleep(0)
        if controller.progress.state == StreamState.DONE:
            break
    assert "G0 X9" in transport.written
    # Find the indices of the jog's bookends and the streamer line.
    g91 = transport.written.index("G91")
    g90 = transport.written.index("G90")
    g0 = transport.written.index("G0 X9")
    # The jog triple is contiguous AND does not bracket the G0 X9 line.
    assert g91 + 2 == g90
    assert not (g91 < g0 < g90)


@pytest.mark.asyncio
async def test_broadcast_drops_oldest_when_subscriber_is_slow() -> None:
    """An overflowing subscriber queue must drop the oldest snapshot
    rather than blocking ``_broadcast``."""
    from pen_plotter.hardware import controller as ctrl_mod
    from pen_plotter.hardware.streamer import StreamProgress, StreamState

    controller = PlotterController()
    queue = controller.subscribe()
    # Fill past capacity. The bounded queue evicts the oldest each time.
    for i in range(ctrl_mod._SUBSCRIBER_QUEUE_MAXSIZE + 5):
        await controller._broadcast(
            StreamProgress(total=10, sent=i, acked=i, state=StreamState.RUNNING)
        )
    # Drained size equals capacity (latest snapshots retained).
    assert queue.qsize() == ctrl_mod._SUBSCRIBER_QUEUE_MAXSIZE
    # The very last broadcast must be readable.
    drained = []
    while not queue.empty():
        drained.append(queue.get_nowait())
    assert drained[-1].sent == ctrl_mod._SUBSCRIBER_QUEUE_MAXSIZE + 4

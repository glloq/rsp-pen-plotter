import asyncio

import pytest

from pen_plotter.hardware.commands import home_command, jog_command
from pen_plotter.hardware.controller import PlotterController
from pen_plotter.hardware.streamer import GcodeStreamer, StreamState, executable_lines
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

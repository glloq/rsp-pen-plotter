import pytest

from pen_plotter.core.gcode import LayerGeneration, generate_gcode
from pen_plotter.core.toolchange import guided_pause_points
from pen_plotter.hardware.streamer import GcodeStreamer, StreamState, executable_lines
from pen_plotter.hardware.transport import MockTransport
from pen_plotter.profiles import get_profile

NS = (
    'xmlns="http://www.w3.org/2000/svg" '
    'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"'
)
TWO_LAYERS = (
    f'<svg {NS} viewBox="0 0 100 100">'
    '<g inkscape:label="red" stroke="#ff0000"><path d="M10 10 L90 10 L90 90"/></g>'
    '<g inkscape:label="blue" stroke="#0000ff"><path d="M10 50 L90 50"/></g>'
    "</svg>"
)


def _profile():
    profile = get_profile("Custom CoreXY A3")
    assert profile is not None
    return profile


def test_pause_points_mark_each_tool_change() -> None:
    profile = _profile()
    gcode = generate_gcode(
        TWO_LAYERS,
        profile,
        layers=[
            LayerGeneration(layer_id="red", target_pen_slot=0),
            LayerGeneration(layer_id="blue", target_pen_slot=3),
        ],
    )
    points = guided_pause_points(gcode, profile)
    # Two distinct slots -> two guided pauses, and each indexed line is "M0".
    assert len(points) == 2
    lines = executable_lines(gcode)
    for index, prompt in points.items():
        assert lines[index] == "M0"
        assert prompt.startswith("Insert pen slot")


def test_no_pause_points_without_tool_changes() -> None:
    profile = _profile()
    gcode = generate_gcode(TWO_LAYERS, profile)  # no pen slots assigned
    assert guided_pause_points(gcode, profile) == {}


@pytest.mark.asyncio
async def test_streamer_waits_at_pause_point_and_skips_the_line() -> None:
    import asyncio

    # Lines: A, M0 (pause point 1), B. The M0 must be skipped, not sent.
    transport = MockTransport()
    streamer = GcodeStreamer(transport, pause_points={1: "Insert pen slot 1: Red"})
    task = asyncio.create_task(streamer.run("G0 X1\nM0\nG1 X2 Y2 F600\n"))

    # Let it stream A and reach the guided pause.
    for _ in range(20):
        await asyncio.sleep(0)
        if streamer.progress.state == StreamState.WAITING:
            break
    assert streamer.progress.state == StreamState.WAITING
    assert streamer.progress.message == "Insert pen slot 1: Red"
    assert transport.written == ["G0 X1"]

    streamer.resume()
    final = await task
    assert final.state == StreamState.DONE
    assert final.message is None
    assert transport.written == ["G0 X1", "G1 X2 Y2 F600"]  # M0 skipped
    assert final.acked == 3

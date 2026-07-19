from pen_plotter.core.resume import build_resume_program
from pen_plotter.hardware.streamer import executable_lines
from pen_plotter.profiles import get_profile

GCODE = "G21\nG90\nM280 P0 S40\nG0 X10 Y20\nM280 P0 S90\nG1 X30 Y40 F1800\nG1 X50 Y60\n"


def _profile():
    profile = get_profile("Custom CoreXY A3")
    assert profile is not None
    return profile


def test_resume_from_start_returns_full_program() -> None:
    assert build_resume_program(GCODE, 0, _profile()) == executable_lines(GCODE)


def test_resume_past_end_is_empty() -> None:
    assert build_resume_program(GCODE, 99, _profile()) == []


def test_resume_reinitializes_modal_state_and_position() -> None:
    profile = _profile()
    # Acknowledge through "G1 X30 Y40 F1800" (6 executable lines), resume at the last move.
    program = build_resume_program(GCODE, 6, profile)
    # Units restored, pen lifted, and a travel back to the last known position.
    assert program[0] == "G21"
    assert profile.pen_up_command in program
    assert any("X30.000 Y40.000" in line for line in program)
    # The remaining original line is appended last.
    assert program[-1] == "G1 X50 Y60"


def test_resume_remainder_matches_checkpoint() -> None:
    program = build_resume_program(GCODE, 6, _profile())
    assert program[-1:] == executable_lines(GCODE)[6:]


def test_resume_mid_stroke_relowers_the_pen() -> None:
    """A checkpoint that falls mid-polyline (pen down, next line keeps
    drawing) must re-issue the pen-down after travelling back, or the
    rest of the interrupted path is air-drawn with the pen up."""
    profile = _profile()
    # Checkpoint 6 acked through the first draw move; the pen was left
    # down and the remainder opens on another G1 draw move.
    program = build_resume_program(GCODE, 6, profile)
    down = program.index(profile.pen_down_command)
    travel = next(i for i, line in enumerate(program) if "X30.000 Y40.000" in line)
    # Pen down comes after the travel back and before the remaining draw move.
    assert travel < down < len(program) - 1
    assert program[-1] == "G1 X50 Y60"


def test_resume_at_polyline_boundary_keeps_pen_up() -> None:
    """When the remainder opens on a new polyline (pen-up first), no
    pen-down is re-issued — the program re-establishes its own state,
    and lowering the pen first would stamp a stray dot."""
    profile = _profile()
    gcode = (
        "G21\nG90\n"
        f"{profile.pen_up_command}\nG0 X10 Y20\n{profile.pen_down_command}\n"
        "G1 X30 Y40 F1800\n"
        f"{profile.pen_up_command}\nG0 X50 Y60\n{profile.pen_down_command}\n"
        "G1 X70 Y80\n"
    )
    # Checkpoint 6 = acked through the first polyline's last draw move;
    # the remainder opens on the second polyline's pen-up.
    program = build_resume_program(gcode, 6, profile)
    preamble_len = len(program) - len(executable_lines(gcode)[6:])
    assert profile.pen_down_command not in program[:preamble_len]

import pytest

from pen_plotter.core.resume import build_resume_program
from pen_plotter.hardware.streamer import executable_lines
from pen_plotter.profiles import get_profile

GCODE = "G21\nG90\nM280 P0 S40\nG0 X10 Y20\nM280 P0 S90\nG1 X30 Y40 F1800\nG1 X50 Y60\n"


@pytest.fixture(autouse=True)
def _exact_resume(monkeypatch: pytest.MonkeyPatch) -> None:
    """Most tests here validate the exact-resume preamble mechanics, so pin
    OMNIPLOT_RESUME_CONSERVATIVE=0. Conservative-mode tests override it."""
    monkeypatch.setenv("OMNIPLOT_RESUME_CONSERVATIVE", "0")


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


def test_resume_after_arc_recovers_the_arc_endpoint() -> None:
    """A checkpoint taken after a G2/G3 arc must travel back to the arc's
    endpoint, not the position before the arc (P0.4)."""
    profile = _profile()
    # G0 travels to (10,20); the arc ENDS at (30,40). Ack through the arc.
    gcode = "G21\nG90\nG0 X10 Y20\nG2 X30 Y40 I5 J5 F1800\nG1 X50 Y60\n"
    program = build_resume_program(gcode, 4, profile)  # G21,G90,G0,G2 acked
    # Travel back targets the ARC endpoint, never the pre-arc G0 point.
    assert any("X30.000 Y40.000" in line for line in program)
    assert not any("X10.000 Y20.000" in line for line in program)
    assert program[-1] == "G1 X50 Y60"


def test_resume_after_g3_arc_recovers_endpoint() -> None:
    profile = _profile()
    gcode = "G21\nG90\nG0 X0 Y0\nG3 X12 Y8 I2 J2 F1800\nG1 X20 Y20\n"
    program = build_resume_program(gcode, 4, profile)
    assert any("X12.000 Y8.000" in line for line in program)


def test_resume_lifts_with_active_pens_pen_up_override() -> None:
    """The resume travel must lift with the loaded pen's own pen_up_command
    override, not the profile default (P0.4)."""
    from pen_plotter.models import PenSlot

    profile = _profile().model_copy(deep=True)
    profile.pens = [
        PenSlot(index=0, name="A", pen_down_command="DOWN_A", pen_up_command="UP_A")
    ]
    # Pen A lowered, then a draw move; checkpoint mid-stroke.
    gcode = "G21\nG90\nDOWN_A\nG1 X30 Y40 F1800\nG1 X50 Y60\n"
    program = build_resume_program(gcode, 4, profile)
    # Travel back lifts with UP_A (the pen's override), not the profile default.
    assert "UP_A" in program
    assert profile.pen_up_command not in program
    # Mid-stroke resume re-lowers with the same override.
    assert "DOWN_A" in program
    assert program[-1] == "G1 X50 Y60"


def test_conservative_resume_rewinds_to_last_pen_up(monkeypatch) -> None:
    """With OMNIPLOT_RESUME_CONSERVATIVE=1 the resume point rewinds to the last
    pen-up so an acked-but-unexecuted move is re-drawn, not skipped (P0.3)."""
    monkeypatch.setenv("OMNIPLOT_RESUME_CONSERVATIVE", "1")
    profile = _profile()
    up = profile.pen_up_command
    down = profile.pen_down_command
    # Two strokes; checkpoint lands mid second stroke (exec index 7).
    gcode = "\n".join(
        [
            "G21",  # 0
            "G90",  # 1
            up,  # 2
            "G0 X10 Y10",  # 3  travel to stroke 1
            down,  # 4
            "G1 X20 Y20 F1800",  # 5  stroke 1
            up,  # 6  <-- last pen-up before the checkpoint
            "G0 X30 Y30",  # 7  travel to stroke 2
            down,  # 8
            "G1 X40 Y40 F1800",  # 9  stroke 2 (interrupted here)
            "G1 X50 Y50",  # 10
        ]
    )
    # Default (exact) resume at checkpoint 10 would skip line 9's move if the
    # firmware hadn't executed it. Conservative rewinds to the pen-up at 6.
    program = build_resume_program(gcode, 10, profile)
    # The remainder starts at the rewound pen-up (line 6), re-doing stroke 2.
    assert up in program
    assert "G0 X30 Y30" in program
    assert down in program
    assert "G1 X40 Y40 F1800" in program  # the interrupted move is re-drawn
    assert program[-1] == "G1 X50 Y50"


def test_resume_is_conservative_by_default(monkeypatch) -> None:
    """With the flag unset, resume now defaults to conservative so an
    acked-but-unexecuted move is never skipped (P0.1)."""
    monkeypatch.delenv("OMNIPLOT_RESUME_CONSERVATIVE", raising=False)
    profile = _profile()
    up = profile.pen_up_command
    down = profile.pen_down_command
    gcode = "\n".join(
        ["G21", "G90", up, "G0 X10 Y10", down, "G1 X20 Y20 F1800", up, "G0 X30 Y30",
         down, "G1 X40 Y40 F1800", "G1 X50 Y50"]
    )
    # Interrupted mid stroke-2 at checkpoint 10; the default rewinds to the
    # pen-up at index 6 and re-draws the interrupted move rather than skipping.
    program = build_resume_program(gcode, 10, profile)
    assert "G1 X40 Y40 F1800" in program
    assert program[-1] == "G1 X50 Y50"


def test_conservative_resume_does_not_rewind_past_tool_change(monkeypatch) -> None:
    """Conservative rewind must stop at a completed tool change: crossing it
    would redraw the previous layer with the newly loaded pen and re-emit the
    swap's firmware pause as a raw M0 (P0.5)."""
    monkeypatch.setenv("OMNIPLOT_RESUME_CONSERVATIVE", "1")
    profile = _profile()
    up = profile.pen_up_command
    down = profile.pen_down_command
    m0 = profile.tool_change_command  # firmware pause staged at every swap
    assert m0.strip() == "M0"
    gcode = "\n".join(
        [
            "G21",  # 0
            "G90",  # 1
            up,  # 2
            "G0 X10 Y10",  # 3
            down,  # 4
            "G1 X20 Y20 F1800",  # 5  layer 1 stroke (pen A)
            up,  # 6  layer 1 last pen-up
            m0,  # 7  tool change — operator swapped to pen B
            "G0 X30 Y30",  # 8  travel with pen B
            down,  # 9
            "G1 X40 Y40 F1800",  # 10 layer 2 stroke (interrupted here)
            "G1 X50 Y50",  # 11
        ]
    )
    # Checkpoint 10 falls just after the swap, before pen B's first pen-up — the
    # exact spot where the old rewind walked back past the M0 into layer 1.
    program = build_resume_program(gcode, 10, profile)
    # The completed swap is not re-run as a raw firmware pause...
    assert m0 not in program
    # ...and layer 1's stroke is not redrawn with pen B...
    assert "G1 X20 Y20 F1800" not in program
    # ...the remainder resumes from just after the swap.
    assert "G0 X30 Y30" in program
    assert program[-1] == "G1 X50 Y50"


def test_exact_resume_when_opted_out(monkeypatch) -> None:
    """OMNIPLOT_RESUME_CONSERVATIVE=0 opts back into exact-checkpoint resume."""
    monkeypatch.setenv("OMNIPLOT_RESUME_CONSERVATIVE", "0")
    program = build_resume_program(GCODE, 6, _profile())
    assert program[-1:] == executable_lines(GCODE)[6:]


def test_resume_in_inch_mode_travels_in_metric_then_restores_g20(monkeypatch) -> None:
    """A G20 (inch) job must have its re-init travel done in G21 with mm-scaled
    coordinates, then G20 restored — otherwise the head travels ~25.4x too fast
    to the wrong spot (P2.3)."""
    monkeypatch.setenv("OMNIPLOT_RESUME_CONSERVATIVE", "0")  # exact, for clarity
    profile = _profile()
    gcode = "G20\nG90\nG0 X4 Y2\nG1 X6 Y3 F60\nG1 X8 Y4\n"
    program = build_resume_program(gcode, 4, profile)  # acked G20,G90,G0,G1
    assert "G21" in program
    assert any("X152.400 Y76.200" in line for line in program)  # 6in,3in -> mm
    assert "G20" in program
    assert program.index("G21") < program.index("G20")
    assert program[-1] == "G1 X8 Y4"


def test_ambiguous_pen_down_falls_back_to_default_up(monkeypatch) -> None:
    """Two slots sharing a pen-down command but differing pen-up commands make
    the down line ambiguous — resume must lift with the profile default, not an
    arbitrary slot's override (P2.4)."""
    monkeypatch.setenv("OMNIPLOT_RESUME_CONSERVATIVE", "0")
    from pen_plotter.models import PenSlot

    profile = _profile().model_copy(deep=True)
    profile.pens = [
        PenSlot(index=0, name="A", pen_down_command="DOWN", pen_up_command="UP_A"),
        PenSlot(index=1, name="B", pen_down_command="DOWN", pen_up_command="UP_B"),
    ]
    gcode = "G21\nG90\nDOWN\nG1 X30 Y40 F1800\nG1 X50 Y60\n"
    program = build_resume_program(gcode, 4, profile)
    assert profile.pen_up_command in program
    assert "UP_A" not in program
    assert "UP_B" not in program

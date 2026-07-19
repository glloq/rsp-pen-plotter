"""Tests for the structured, G-code-free host-magazine swap builder.

A host magazine (a rack bolted onto a machine with no native tool
change) is configured with high-level steps — move to slot, grab,
release, head up/down, dwell — plus per-pen positions. The
``HostMacroStrategy`` compiles those to concrete commands at plan time,
filling each pen's calibrated coordinates and tracking the outgoing slot
so a full swap can deposit the old pen before fetching the new one.
"""

from __future__ import annotations

from pen_plotter.core.gcode import LayerGeneration, generate_gcode
from pen_plotter.core.toolchange import guided_swap_actions
from pen_plotter.domain.capability import (
    HostSwapPlan,
    HostSwapStep,
    MachineCapabilities,
    ToolChangeStrategy,
)
from pen_plotter.domain.toolchange.orchestrator import (
    SwapContext,
    ToolChangeOrchestrator,
)
from pen_plotter.models import MachineProfile, PenSlot, Point, WorkspaceBounds

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

_DEFAULT_STEPS = [
    HostSwapStep(kind="head_up"),
    HostSwapStep(kind="move_to_old_slot"),
    HostSwapStep(kind="release", wait_ms=200),
    HostSwapStep(kind="move_to_new_slot"),
    HostSwapStep(kind="grab", wait_ms=200),
    HostSwapStep(kind="head_down"),
]


def _host_profile(steps: list[HostSwapStep] | None = None) -> MachineProfile:
    caps = MachineCapabilities(
        tool_change=ToolChangeStrategy(
            mode="host_macro",
            command_source="host",
            host_swap=HostSwapPlan(
                grab_command="M280 P1 S90",
                drop_command="M280 P1 S20",
                steps=steps if steps is not None else list(_DEFAULT_STEPS),
            ),
        ),
        max_pens_in_magazine=2,
    )
    return MachineProfile(
        name="Rack A3",
        units="mm",
        workspace=WorkspaceBounds(x_min=0.0, y_min=0.0, x_max=300.0, y_max=420.0),
        origin="bottom_left",
        gcode_dialect="grbl",
        pen_up_command="M280 P0 S40",
        pen_down_command="M280 P0 S90",
        tool_change_method="rack",
        tool_change_command="",
        drawing_speed_mm_s=60.0,
        travel_speed_mm_s=120.0,
        acceleration_mm_s2=1500.0,
        pen_slot_count=2,
        pens=[
            PenSlot(index=0, name="Red", color="#ff0000", position=Point(x=10.0, y=200.0)),
            PenSlot(index=1, name="Blue", color="#0000ff", position=Point(x=40.0, y=200.0)),
        ],
        capabilities=caps,
    )


def _layers() -> list[LayerGeneration]:
    return [
        LayerGeneration(layer_id="red", target_pen_slot=0),
        LayerGeneration(layer_id="blue", target_pen_slot=1),
    ]


def test_orchestrator_compiles_full_swap_with_positions() -> None:
    profile = _host_profile()
    orch = ToolChangeOrchestrator(profile)
    # Swap from slot 0 (in hand) to slot 1.
    plan = orch.plan(SwapContext(slot_index=1, from_slot_index=0))
    sends = [c.send for c in plan.commands]
    assert sends == [
        "M280 P0 S40",  # head up
        "G0 X10.000 Y200.000 F7200.0",  # move to OLD slot (0)
        "M280 P1 S20",  # release
        "G0 X40.000 Y200.000 F7200.0",  # move to NEW slot (1)
        "M280 P1 S90",  # grab
        "M280 P0 S90",  # head down
    ]
    # Settle dwell folds onto the release / grab commands.
    waits = {c.send: c.wait_ms for c in plan.commands}
    assert waits["M280 P1 S20"] == 200
    assert waits["M280 P1 S90"] == 200


def test_first_swap_has_no_old_slot_move() -> None:
    profile = _host_profile()
    orch = ToolChangeOrchestrator(profile)
    # First swap: nothing in hand → the "old slot" move is skipped.
    plan = orch.plan(SwapContext(slot_index=0, from_slot_index=None))
    sends = [c.send for c in plan.commands]
    assert sends == [
        "M280 P0 S40",
        "M280 P1 S20",  # release (skipped move folds nothing)
        "G0 X10.000 Y200.000 F7200.0",  # move to NEW slot (0)
        "M280 P1 S90",
        "M280 P0 S90",
    ]


def test_guided_swap_actions_tracks_previous_slot() -> None:
    profile = _host_profile()
    gcode = generate_gcode(TWO_LAYERS, profile, layers=_layers())
    actions = guided_swap_actions(gcode, profile)
    # Two host-driven swaps, both streamed inline (host_timed).
    assert len(actions) == 2
    plans = list(actions.values())
    assert all(a.kind == "host_timed" for a in plans)
    # The second swap (→ slot 1) deposits the old pen at slot 0's position.
    second = plans[1]
    sends = [c.send for c in second.commands]
    assert "G0 X10.000 Y200.000 F7200.0" in sends  # old slot 0
    assert "G0 X40.000 Y200.000 F7200.0" in sends  # new slot 1


def test_raw_step_is_escape_hatch() -> None:
    steps = [HostSwapStep(kind="raw", send="G4 P0.5"), HostSwapStep(kind="grab")]
    profile = _host_profile(steps)
    orch = ToolChangeOrchestrator(profile)
    plan = orch.plan(SwapContext(slot_index=1, from_slot_index=0))
    sends = [c.send for c in plan.commands]
    assert sends == ["G4 P0.5", "M280 P1 S90"]


def test_dwell_only_adds_host_side_wait_no_line() -> None:
    steps = [HostSwapStep(kind="grab"), HostSwapStep(kind="dwell", wait_ms=500)]
    profile = _host_profile(steps)
    orch = ToolChangeOrchestrator(profile)
    plan = orch.plan(SwapContext(slot_index=1, from_slot_index=0))
    assert [c.send for c in plan.commands] == ["M280 P1 S90"]
    assert plan.commands[0].wait_ms == 500


def test_legacy_raw_host_macro_still_works() -> None:
    """Profiles authored before the builder keep their raw macro."""
    caps = MachineCapabilities(
        tool_change=ToolChangeStrategy(
            mode="host_macro",
            command_source="host",
            host_macro=[{"send": "M6 T{slot}", "wait_ms": 0}],  # type: ignore[list-item]
        ),
    )
    profile = _host_profile()
    profile.capabilities = caps
    orch = ToolChangeOrchestrator(profile)
    plan = orch.plan(SwapContext(slot_index=2))
    assert [c.send for c in plan.commands] == ["M6 T2"]


def test_host_swap_skips_uncalibrated_slot_keeps_settle() -> None:
    """A move to an uncalibrated slot is dropped, but its settle time is
    preserved on the previous command so timings don't collapse."""
    steps = [HostSwapStep(kind="grab"), HostSwapStep(kind="move_to_new_slot", wait_ms=300)]
    profile = _host_profile(steps)
    profile.pens[1].position = None  # type: ignore[index]
    orch = ToolChangeOrchestrator(profile)
    plan = orch.plan(SwapContext(slot_index=1, from_slot_index=0))
    assert [c.send for c in plan.commands] == ["M280 P1 S90"]
    assert plan.commands[0].wait_ms == 300


def test_head_steps_use_z_axis_when_heights_set() -> None:
    """With a real Z axis configured, head_up/head_down emit G0 Z moves
    at the safe / engage heights instead of the servo commands."""
    steps = [HostSwapStep(kind="head_up"), HostSwapStep(kind="head_down")]
    profile = _host_profile(steps)
    swap = profile.capabilities.tool_change.host_swap  # type: ignore[union-attr]
    swap.safe_z_mm = 5.0
    swap.engage_z_mm = -2.0
    orch = ToolChangeOrchestrator(profile)
    plan = orch.plan(SwapContext(slot_index=1, from_slot_index=0))
    sends = [c.send for c in plan.commands]
    assert sends == ["G0 Z5.000 F7200.0", "G0 Z-2.000 F7200.0"]


def test_head_steps_fall_back_to_servo_without_z() -> None:
    """Servo machines (no Z heights) keep emitting the pen-up/-down commands."""
    steps = [HostSwapStep(kind="head_up"), HostSwapStep(kind="head_down")]
    profile = _host_profile(steps)  # no safe_z / engage_z set
    orch = ToolChangeOrchestrator(profile)
    plan = orch.plan(SwapContext(slot_index=1, from_slot_index=0))
    sends = [c.send for c in plan.commands]
    assert sends == ["M280 P0 S40", "M280 P0 S90"]


def test_head_steps_use_magazine_servo_override() -> None:
    """A servo machine whose magazine sits higher than the paper uses the
    dedicated magazine head-up/-down servo commands, not the profile's."""
    steps = [HostSwapStep(kind="head_up"), HostSwapStep(kind="head_down")]
    profile = _host_profile(steps)
    swap = profile.capabilities.tool_change.host_swap  # type: ignore[union-attr]
    swap.head_up_command = "M280 P0 S10"
    swap.head_down_command = "M280 P0 S70"
    orch = ToolChangeOrchestrator(profile)
    plan = orch.plan(SwapContext(slot_index=1, from_slot_index=0))
    sends = [c.send for c in plan.commands]
    assert sends == ["M280 P0 S10", "M280 P0 S70"]


def test_z_axis_wins_over_servo_override() -> None:
    """When both a Z height and a servo override are set, the real Z axis
    takes precedence (the machine has a Z axis)."""
    steps = [HostSwapStep(kind="head_up")]
    profile = _host_profile(steps)
    swap = profile.capabilities.tool_change.host_swap  # type: ignore[union-attr]
    swap.head_up_command = "M280 P0 S10"
    swap.safe_z_mm = 5.0
    orch = ToolChangeOrchestrator(profile)
    plan = orch.plan(SwapContext(slot_index=1, from_slot_index=0))
    assert [c.send for c in plan.commands] == ["G0 Z5.000 F7200.0"]


def test_clearance_approach_then_advance_retract() -> None:
    """With a clearance vector, move_to_slot lands at the approach point
    (engagement + clearance) and advance/retract hop in and out."""
    steps = [
        HostSwapStep(kind="move_to_new_slot"),  # → approach
        HostSwapStep(kind="advance_to_slot"),  # → engagement
        HostSwapStep(kind="grab"),
        HostSwapStep(kind="retract_from_slot"),  # → approach
    ]
    profile = _host_profile(steps)
    swap = profile.capabilities.tool_change.host_swap  # type: ignore[union-attr]
    swap.clearance_axis = "y"
    swap.clearance_dir = "+"
    swap.clearance_mm = 15.0
    orch = ToolChangeOrchestrator(profile)
    # Slot 1 engagement is (40, 200); approach = (40, 215).
    plan = orch.plan(SwapContext(slot_index=1, from_slot_index=0))
    sends = [c.send for c in plan.commands]
    assert sends == [
        "G0 X40.000 Y215.000 F7200.0",  # move to approach
        "G0 X40.000 Y200.000 F7200.0",  # advance to engagement
        "M280 P1 S90",  # grab
        "G0 X40.000 Y215.000 F7200.0",  # retract to approach
    ]


def test_clearance_negative_x_direction() -> None:
    steps = [HostSwapStep(kind="move_to_new_slot"), HostSwapStep(kind="advance_to_slot")]
    profile = _host_profile(steps)
    swap = profile.capabilities.tool_change.host_swap  # type: ignore[union-attr]
    swap.clearance_axis = "x"
    swap.clearance_dir = "-"
    swap.clearance_mm = 20.0
    orch = ToolChangeOrchestrator(profile)
    # Slot 1 engagement (40, 200); approach = (40 - 20, 200) = (20, 200).
    plan = orch.plan(SwapContext(slot_index=1, from_slot_index=0))
    sends = [c.send for c in plan.commands]
    assert sends == ["G0 X20.000 Y200.000 F7200.0", "G0 X40.000 Y200.000 F7200.0"]


def test_zero_clearance_keeps_approach_equal_to_engagement() -> None:
    """Default clearance (0) → approach == engagement (no insertion hop)."""
    steps = [HostSwapStep(kind="move_to_new_slot"), HostSwapStep(kind="advance_to_slot")]
    profile = _host_profile(steps)  # clearance_mm defaults to 0
    orch = ToolChangeOrchestrator(profile)
    plan = orch.plan(SwapContext(slot_index=1, from_slot_index=0))
    sends = [c.send for c in plan.commands]
    assert sends == ["G0 X40.000 Y200.000 F7200.0", "G0 X40.000 Y200.000 F7200.0"]


def test_advance_without_prior_move_is_skipped() -> None:
    """advance_to_slot before any move_to_slot has no current slot → no-op."""
    steps = [HostSwapStep(kind="advance_to_slot"), HostSwapStep(kind="grab")]
    profile = _host_profile(steps)
    swap = profile.capabilities.tool_change.host_swap  # type: ignore[union-attr]
    swap.clearance_mm = 15.0
    orch = ToolChangeOrchestrator(profile)
    plan = orch.plan(SwapContext(slot_index=1, from_slot_index=0))
    assert [c.send for c in plan.commands] == ["M280 P1 S90"]


# ── kinematic dock mechanism ─────────────────────────────────────────


def test_dock_motion_lock_emits_no_latch_command() -> None:
    """A dock with a motion (magnetic / kinematic) lock couples by the
    advance/retract motion alone — grab/release send nothing, even if a
    stale command is left on the plan."""
    steps = [
        HostSwapStep(kind="move_to_old_slot"),  # approach old dock
        HostSwapStep(kind="advance_to_slot"),  # slide tool into dock
        HostSwapStep(kind="release", wait_ms=200),  # unlock (motion → no cmd)
        HostSwapStep(kind="retract_from_slot"),  # back out, tool stays
        HostSwapStep(kind="move_to_new_slot"),  # approach new dock
        HostSwapStep(kind="advance_to_slot"),  # slide onto the new tool
        HostSwapStep(kind="grab", wait_ms=200),  # lock (motion → no cmd)
        HostSwapStep(kind="retract_from_slot"),  # pull tool out
    ]
    profile = _host_profile(steps)
    swap = profile.capabilities.tool_change.host_swap  # type: ignore[union-attr]
    swap.mechanism = "dock"
    swap.lock_mode = "motion"
    swap.clearance_mm = 30.0
    orch = ToolChangeOrchestrator(profile)
    plan = orch.plan(SwapContext(slot_index=1, from_slot_index=0))
    sends = [c.send for c in plan.commands]
    # Slots: 0 → (10, 200), 1 → (40, 200); +Y clearance 30 → approach +30.
    # Pure motion: every command is a move, no latch line is emitted.
    assert sends == [
        "G0 X10.000 Y230.000 F7200.0",  # approach old dock (0)
        "G0 X10.000 Y200.000 F7200.0",  # advance into old dock
        "G0 X10.000 Y230.000 F7200.0",  # retract from old dock
        "G0 X40.000 Y230.000 F7200.0",  # approach new dock (1)
        "G0 X40.000 Y200.000 F7200.0",  # advance into new dock
        "G0 X40.000 Y230.000 F7200.0",  # retract with the new tool
    ]
    # The unlock/lock settle time survives onto the advance it folds into.
    assert plan.commands[1].wait_ms == 200  # release dwell → advance into old dock
    assert plan.commands[4].wait_ms == 200  # grab dwell → advance into new dock


def test_dock_command_lock_emits_lock_unlock() -> None:
    """A dock with a command lock (servo / motorised latch) emits the
    grab/drop commands as the lock / unlock primitives."""
    steps = [HostSwapStep(kind="release"), HostSwapStep(kind="grab")]
    profile = _host_profile(steps)
    swap = profile.capabilities.tool_change.host_swap  # type: ignore[union-attr]
    swap.mechanism = "dock"
    swap.lock_mode = "command"
    orch = ToolChangeOrchestrator(profile)
    plan = orch.plan(SwapContext(slot_index=1, from_slot_index=0))
    assert [c.send for c in plan.commands] == ["M280 P1 S20", "M280 P1 S90"]


def test_dock_defaults_to_rack_mechanism() -> None:
    """An unset mechanism keeps the legacy rack behaviour (grab emits)."""
    plan = HostSwapPlan()
    assert plan.mechanism == "rack"
    assert plan.lock_mode == "command"


def test_rack_motion_grab_also_emits_no_command() -> None:
    """A motion grab (friction / magnetic pen holder) suppresses the
    gripper command on a rack too, not just on a dock."""
    steps = [HostSwapStep(kind="release"), HostSwapStep(kind="grab")]
    profile = _host_profile(steps)
    swap = profile.capabilities.tool_change.host_swap  # type: ignore[union-attr]
    swap.mechanism = "rack"
    swap.lock_mode = "motion"
    orch = ToolChangeOrchestrator(profile)
    plan = orch.plan(SwapContext(slot_index=1, from_slot_index=0))
    assert [c.send for c in plan.commands] == []


def test_swap_actions_carry_structured_label_color_reason() -> None:
    """P3 (v2): actions expose structured ``label`` / ``color`` /
    ``reason`` so the frontend can compose a localised prompt instead
    of parsing the English ``prompt`` text."""
    from pen_plotter.core.toolchange import _split_label_hex

    # Hex embedded in a display label splits into parts.
    assert _split_label_hex("Vert prairie #00ff00") == ("Vert prairie", "#00ff00")
    assert _split_label_hex("Red (#FF0000)") == ("Red", "#ff0000")
    assert _split_label_hex("#00ff00") == (None, "#00ff00")
    assert _split_label_hex(None) == (None, None)
    # A known colour wins over the embedded hex.
    assert _split_label_hex("Red #ff0000", "#aa0000") == ("Red", "#aa0000")

    profile = _host_profile()
    gcode = generate_gcode(TWO_LAYERS, profile, layers=_layers())
    actions = guided_swap_actions(gcode, profile)
    plans = list(actions.values())
    assert all(a.reason == "tool_change" for a in plans)
    assert all(a.slot is not None for a in plans)
    assert all(a.label for a in plans)


def test_load_boundary_reason_is_load() -> None:
    """A magazine-load boundary carries ``reason='load'`` plus the ink parts."""
    gcode = "; Load pen slot 2 (Rouge cerise #ff0011) into magazine\nM0\nG1 X1 Y1\n"
    profile = _host_profile()
    actions = guided_swap_actions(gcode, profile)
    assert len(actions) == 1
    action = next(iter(actions.values()))
    assert action.kind == "operator_confirm"
    assert action.reason == "load"
    assert action.slot == 2
    assert action.label == "Rouge cerise"
    assert action.color == "#ff0011"

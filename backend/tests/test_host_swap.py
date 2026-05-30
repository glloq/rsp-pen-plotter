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

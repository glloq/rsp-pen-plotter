"""Regression tests for the plotter-settings audit fixes.

Covers the three behaviours wired during the settings audit:

* carousel/rack tool changes route the head to the calibrated slot
  position (``PenSlot.position``) before triggering the swap;
* the time estimate honours ``acceleration_mm_s2`` via a trapezoidal
  velocity profile instead of assuming instant speed changes;
* the retired ``origin: "center"`` value still loads, coerced to
  ``"bottom_left"`` (its historical behaviour).
"""

from __future__ import annotations

from pen_plotter.core.gcode import LayerGeneration, generate_gcode
from pen_plotter.core.preflight import _move_seconds, preflight_report
from pen_plotter.models import (
    MachineProfile,
    PenSlot,
    Point,
    WorkspaceBounds,
)

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


def _carousel_profile(*, positions: bool) -> MachineProfile:
    pens = [
        PenSlot(
            index=0,
            name="Red",
            color="#ff0000",
            installed=True,
            position=Point(x=10.0, y=200.0) if positions else None,
        ),
        PenSlot(
            index=1,
            name="Blue",
            color="#0000ff",
            installed=True,
            position=Point(x=40.0, y=200.0) if positions else None,
        ),
    ]
    return MachineProfile(
        name="Carousel A3",
        units="mm",
        workspace=WorkspaceBounds(x_min=0.0, y_min=0.0, x_max=300.0, y_max=420.0),
        origin="bottom_left",
        gcode_dialect="grbl",
        pen_up_command="M280 P0 S40",
        pen_down_command="M280 P0 S90",
        tool_change_method="carousel",
        tool_change_command="T{slot}",
        drawing_speed_mm_s=60.0,
        travel_speed_mm_s=120.0,
        acceleration_mm_s2=1500.0,
        pen_slot_count=2,
        pens=pens,
    )


def _layers() -> list[LayerGeneration]:
    return [
        LayerGeneration(layer_id="red", target_pen_slot=0),
        LayerGeneration(layer_id="blue", target_pen_slot=1),
    ]


def test_carousel_routes_to_slot_position_before_change() -> None:
    profile = _carousel_profile(positions=True)
    gcode = generate_gcode(TWO_LAYERS, profile, layers=_layers())
    lines = gcode.splitlines()

    # The change to slot 1 (Blue) parks the head at its calibrated
    # position before the swap command, in machine coordinates.
    change_idx = next(i for i, ln in enumerate(lines) if ln.startswith("; Change to pen slot 1"))
    block = lines[change_idx : change_idx + 4]
    assert any(ln == "M280 P0 S40" for ln in block)  # pen up before travelling
    assert any(ln.startswith("G0 X40.000 Y200.000") for ln in block), block
    # The raw swap command follows the goto (``{slot}`` is substituted by
    # the streamer at run time, not during generation).
    assert any(ln == "T{slot}" for ln in block)


def test_no_position_routing_when_uncalibrated() -> None:
    profile = _carousel_profile(positions=False)
    gcode = generate_gcode(TWO_LAYERS, profile, layers=_layers())
    # Without a calibrated position no magazine goto is injected; the
    # swap command follows the comment directly.
    assert "Y200.000" not in gcode


def test_manual_pause_never_routes_to_position() -> None:
    """Only automated magazines (carousel/rack) chase the slot position."""
    profile = _carousel_profile(positions=True)
    manual = profile.model_copy(update={"tool_change_method": "manual_pause"})
    gcode = generate_gcode(TWO_LAYERS, manual, layers=_layers())
    assert "Y200.000" not in gcode


def test_move_seconds_trapezoid_vs_constant() -> None:
    # A long move that reaches cruise speed takes longer than the naive
    # constant-velocity estimate by exactly the ramp overhead.
    distance, speed, accel = 100.0, 50.0, 500.0
    constant = distance / speed
    trapez = _move_seconds(distance, speed, accel)
    assert trapez > constant
    # Ramp overhead = speed / accel (one full accel + one full decel
    # minus the distance saved). Closed-form: 2*(v/a) + (d - v^2/a)/v.
    expected = 2.0 * (speed / accel) + (distance - speed * speed / accel) / speed
    assert abs(trapez - expected) < 1e-9


def test_move_seconds_triangular_for_short_move() -> None:
    # Too short to reach cruise speed → triangular profile.
    distance, speed, accel = 1.0, 50.0, 500.0
    assert _move_seconds(distance, speed, accel) == 2.0 * (distance / accel) ** 0.5


def test_move_seconds_falls_back_without_accel() -> None:
    assert _move_seconds(100.0, 50.0, 0.0) == 100.0 / 50.0


def test_preflight_eta_grows_with_lower_acceleration() -> None:
    profile = _carousel_profile(positions=True)
    fast = preflight_report(TWO_LAYERS, profile, layers=_layers())
    slow_profile = profile.model_copy(update={"acceleration_mm_s2": 50.0})
    slow = preflight_report(TWO_LAYERS, slow_profile, layers=_layers())
    assert slow.estimated_seconds > fast.estimated_seconds


def test_origin_center_coerced_to_bottom_left() -> None:
    profile = MachineProfile.model_validate(
        {
            "name": "Legacy center",
            "units": "mm",
            "workspace": {"x_min": 0.0, "y_min": 0.0, "x_max": 300.0, "y_max": 420.0},
            "origin": "center",
            "gcode_dialect": "grbl",
            "pen_up_command": "M280 P0 S40",
            "pen_down_command": "M280 P0 S90",
            "tool_change_method": "manual_pause",
            "tool_change_command": "M0",
            "drawing_speed_mm_s": 60.0,
            "travel_speed_mm_s": 120.0,
            "acceleration_mm_s2": 1500.0,
            "pen_slot_count": 1,
        }
    )
    assert profile.origin == "bottom_left"

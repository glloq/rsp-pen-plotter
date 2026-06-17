"""Per-pen XY tip-offset compensation (opt-in).

Covers the ``apply_pen_offsets`` switch + ``PenSlot.xy_offset_mm``:
disabled by default (byte-identical G-code), applied to drawing strokes
only when enabled, per-pen, and reflected in the workspace bounds check.

See ``docs/camera_tip_offset.md`` / ADR 0005.
"""

from __future__ import annotations

import re

from pen_plotter.core.gcode import generate_gcode
from pen_plotter.core.preflight import preflight_report
from pen_plotter.domain.print_plan import LayerPlan
from pen_plotter.models import MachineProfile, PenSlot, Point, WorkspaceBounds

NS = (
    'xmlns="http://www.w3.org/2000/svg" '
    'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"'
)
ONE_LINE = (
    f'<svg {NS} viewBox="0 0 100 100">'
    '<g inkscape:label="black"><path d="M0 0 L100 0 L100 100 L0 100 Z"/></g>'
    "</svg>"
)
TWO_LAYERS = (
    f'<svg {NS} viewBox="0 0 100 100">'
    '<g inkscape:label="black"><path d="M10 10 L40 10"/></g>'
    '<g inkscape:label="red"><path d="M10 50 L40 50"/></g>'
    "</svg>"
)

_MOVE = re.compile(r"^G[01] X(-?\d+\.\d+) Y(-?\d+\.\d+)")


def _moves(gcode: str) -> list[tuple[float, float]]:
    """Every absolute G0/G1 coordinate in emission order."""
    out: list[tuple[float, float]] = []
    for line in gcode.splitlines():
        m = _MOVE.match(line)
        if m:
            out.append((float(m.group(1)), float(m.group(2))))
    return out


def _profile(*, apply_offsets: bool, slot0_offset: Point | None = None) -> MachineProfile:
    """A pinned GRBL profile; slot 0 optionally carries an XY offset."""
    return MachineProfile(
        name="Offset GRBL",
        units="mm",
        workspace=WorkspaceBounds(x_min=0.0, y_min=0.0, x_max=300.0, y_max=300.0),
        origin="top_left",
        gcode_dialect="grbl",
        pen_up_command="M280 P0 S40",
        pen_down_command="M280 P0 S90",
        tool_change_method="manual_pause",
        tool_change_command="M0",
        drawing_speed_mm_s=30.0,
        travel_speed_mm_s=120.0,
        acceleration_mm_s2=500.0,
        pen_slot_count=2,
        apply_pen_offsets=apply_offsets,
        pens=[
            PenSlot(
                index=0,
                name="Black",
                color="#000000",
                xy_offset_mm=slot0_offset or Point(x=0.0, y=0.0),
            ),
            PenSlot(index=1, name="Red", color="#ff0000", xy_offset_mm=Point(x=-2.0, y=1.5)),
        ],
    )


def test_offset_defaults_unset() -> None:
    pen = PenSlot(index=0)
    assert pen.xy_offset_mm == Point(x=0.0, y=0.0)
    assert pen.offset_source == "unset"


def test_disabled_is_byte_identical() -> None:
    """An offset set on a pen is ignored while the profile opts out."""
    layers = (LayerPlan(layer_id="black", target_pen_slot=0, source_color="#000000"),)
    baseline = generate_gcode(ONE_LINE, _profile(apply_offsets=False), layers=list(layers))
    with_offset = generate_gcode(
        ONE_LINE,
        _profile(apply_offsets=False, slot0_offset=Point(x=5.0, y=-3.0)),
        layers=list(layers),
    )
    assert baseline == with_offset


def test_enabled_shifts_drawing_strokes() -> None:
    """Enabling offsets translates the pen's strokes by exactly its offset."""
    layers = (LayerPlan(layer_id="black", target_pen_slot=0, source_color="#000000"),)
    base = generate_gcode(
        ONE_LINE, _profile(apply_offsets=True), layers=list(layers)
    )
    shifted = generate_gcode(
        ONE_LINE,
        _profile(apply_offsets=True, slot0_offset=Point(x=5.0, y=-3.0)),
        layers=list(layers),
    )
    base_moves = _moves(base)
    shifted_moves = _moves(shifted)
    assert len(base_moves) == len(shifted_moves)

    home = (0.0, 0.0)
    for (bx, by), (sx, sy) in zip(base_moves, shifted_moves, strict=True):
        if (bx, by) == home:
            # Header/footer home moves use workspace coords, never offset.
            assert (sx, sy) == home
        else:
            assert abs(sx - (bx + 5.0)) < 1e-6
            assert abs(sy - (by - 3.0)) < 1e-6


def test_offset_is_per_pen() -> None:
    """Each layer's strokes shift by its own pen's offset, independently."""
    layers = [
        LayerPlan(layer_id="black", target_pen_slot=0, source_color="#000000"),
        LayerPlan(layer_id="red", target_pen_slot=1, source_color="#ff0000"),
    ]
    base = _moves(generate_gcode(TWO_LAYERS, _profile(apply_offsets=False), layers=layers))
    shifted = _moves(
        generate_gcode(
            TWO_LAYERS,
            _profile(apply_offsets=True, slot0_offset=Point(x=10.0, y=0.0)),
            layers=layers,
        )
    )
    assert len(base) == len(shifted)
    # The black layer (slot 0) moves +10 in X; the red layer (slot 1) moves
    # -2 X / +1.5 Y. The two layers cannot share a single global shift, which
    # is what proves the offset is resolved per pen.
    deltas = {
        (round(sx - bx, 3), round(sy - by, 3))
        for (bx, by), (sx, sy) in zip(base, shifted, strict=True)
        if (bx, by) != (0.0, 0.0)
    }
    assert (10.0, 0.0) in deltas
    assert (-2.0, 1.5) in deltas


def test_offset_can_push_out_of_bounds() -> None:
    """A large offset that shifts strokes off the bed is flagged by preflight."""
    layers = [LayerPlan(layer_id="black", target_pen_slot=0, source_color="#000000")]
    # Drawing fits the 300×300 workspace with a 10 mm margin; the small
    # baseline offsets stay inside.
    in_bounds = preflight_report(
        ONE_LINE, _profile(apply_offsets=True), layers=layers, margin_mm=10.0
    )
    assert in_bounds.within_bounds

    # A +20 mm X offset on the drawing pen pushes the far edge past x_max.
    out = preflight_report(
        ONE_LINE,
        _profile(apply_offsets=True, slot0_offset=Point(x=20.0, y=0.0)),
        layers=layers,
        margin_mm=10.0,
    )
    assert not out.within_bounds
    assert any("exceeds the workspace" in w for w in out.warnings)


def test_offset_ignored_for_bounds_when_disabled() -> None:
    """A would-be out-of-bounds offset is inert while the profile opts out."""
    layers = [LayerPlan(layer_id="black", target_pen_slot=0, source_color="#000000")]
    report = preflight_report(
        ONE_LINE,
        _profile(apply_offsets=False, slot0_offset=Point(x=50.0, y=0.0)),
        layers=layers,
        margin_mm=0.0,
    )
    assert report.within_bounds

"""Byte-for-byte regression tests on the generated G-code.

Each scenario pairs a known SVG input with a frozen profile and the
exact expected G-code output. Any change to templates, slot-handling,
pause logic or feed-rate emission shows up here immediately.

To regenerate the references intentionally::

    uv run pytest tests/test_gcode_golden.py --update-goldens

The diff in ``tests/golden/expected/*.gcode`` then becomes part of the
commit and must be reviewed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from pen_plotter.core.gcode import generate_gcode
from pen_plotter.domain.print_plan import LayerPlan
from pen_plotter.models import (
    EbbConfig,
    MachineProfile,
    PenSlot,
    Placement,
    WorkspaceBounds,
)

INPUTS_DIR = Path(__file__).resolve().parent / "golden" / "inputs"
EXPECTED_DIR = Path(__file__).resolve().parent / "golden" / "expected"


def _frozen_grbl_profile() -> MachineProfile:
    """A fully-specified GRBL profile pinned for golden-file determinism.

    Built in code (not loaded from YAML) so the references stay stable
    regardless of any profile-format tweaks.
    """
    return MachineProfile(
        name="Golden GRBL A4",
        units="mm",
        workspace=WorkspaceBounds(x_min=0.0, y_min=0.0, x_max=297.0, y_max=210.0),
        origin="top_left",
        gcode_dialect="grbl",
        pen_up_command="M280 P0 S40",
        pen_down_command="M280 P0 S90",
        tool_change_method="manual_pause",
        tool_change_command="M0",
        drawing_speed_mm_s=30.0,
        travel_speed_mm_s=120.0,
        acceleration_mm_s2=500.0,
        pen_slot_count=4,
        supports_arcs=False,
        arc_tolerance_mm=0.1,
        ebb=None,
        pens=[
            PenSlot(index=0, name="Black 0.3", color="#000000", installed=True),
            PenSlot(index=1, name="Red 0.5", color="#ff0000", installed=True),
            PenSlot(index=2, name="Blue 0.5", color="#0000ff", installed=True),
            PenSlot(index=3, name="Spare", color="#00aa00", installed=False),
        ],
    )


def _frozen_ebb_profile() -> MachineProfile:
    """A frozen EBB profile (AxiDraw-like). Unused for now but pinned for future expansion."""
    return MachineProfile(
        name="Golden EBB A4",
        units="mm",
        workspace=WorkspaceBounds(x_min=0.0, y_min=0.0, x_max=297.0, y_max=210.0),
        origin="top_left",
        gcode_dialect="ebb",
        pen_up_command="SP,1",
        pen_down_command="SP,0",
        tool_change_method="manual_pause",
        tool_change_command="M0",
        drawing_speed_mm_s=30.0,
        travel_speed_mm_s=120.0,
        acceleration_mm_s2=500.0,
        pen_slot_count=1,
        supports_arcs=False,
        arc_tolerance_mm=0.1,
        ebb=EbbConfig(),
    )


@dataclass(frozen=True)
class GoldenCase:
    name: str
    svg_filename: str
    layers: tuple[LayerPlan, ...]
    scale_mode: str = "fit"
    margin_mm: float = 10.0
    placement: Placement | None = None


CASES: tuple[GoldenCase, ...] = (
    GoldenCase(
        name="simple_square",
        svg_filename="simple_square.svg",
        layers=(
            LayerPlan(layer_id="black", target_pen_slot=0, source_color="#000000"),
        ),
    ),
    GoldenCase(
        name="two_layers",
        svg_filename="two_layers.svg",
        layers=(
            LayerPlan(layer_id="red", target_pen_slot=1, source_color="#ff0000"),
            LayerPlan(layer_id="blue", target_pen_slot=2, source_color="#0000ff"),
        ),
    ),
    GoldenCase(
        name="triangle_actual_scale",
        svg_filename="triangle.svg",
        layers=(
            LayerPlan(
                layer_id="black",
                target_pen_slot=0,
                source_color="#000000",
                drawing_speed_mm_s=15.0,
            ),
        ),
        scale_mode="actual",
    ),
)


def _generate(case: GoldenCase) -> str:
    svg = (INPUTS_DIR / case.svg_filename).read_text(encoding="utf-8")
    return generate_gcode(
        svg,
        _frozen_grbl_profile(),
        layers=list(case.layers),
        scale_mode=case.scale_mode,  # type: ignore[arg-type]
        margin_mm=case.margin_mm,
        placement=case.placement,
    )


@pytest.mark.golden
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_gcode_matches_golden(case: GoldenCase, update_goldens: bool) -> None:
    """Generated G-code must match the committed reference byte-for-byte."""
    expected_path = EXPECTED_DIR / f"{case.name}.gcode"
    actual = _generate(case)

    if update_goldens or not expected_path.exists():
        EXPECTED_DIR.mkdir(parents=True, exist_ok=True)
        expected_path.write_text(actual, encoding="utf-8")
        if not update_goldens:
            pytest.fail(
                f"Golden file {expected_path} did not exist; created it. "
                "Review the diff and re-run."
            )
        return

    expected = expected_path.read_text(encoding="utf-8")
    assert actual == expected, (
        f"G-code drift for case {case.name!r}. "
        f"Re-run with --update-goldens to refresh after intentional changes.\n"
        f"--- expected ---\n{expected}\n--- actual ---\n{actual}"
    )

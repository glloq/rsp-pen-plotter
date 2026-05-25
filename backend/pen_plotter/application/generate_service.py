"""``run_generate``: the application use case behind ``POST /generate``.

The endpoint adapter only forwards the request and packs the response —
all decisions live here so a CLI or test runner can drive the exact
same pipeline without going through HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass

from pen_plotter.application.plan_resolver import resolve_plan
from pen_plotter.core.ebb import generate_ebb
from pen_plotter.core.gcode import generate_gcode
from pen_plotter.domain.print_plan import PrintPlan, ResolvedPlan
from pen_plotter.models import MachineProfile, Placement


@dataclass
class GenerateOutcome:
    """Bundle of everything ``run_generate`` produces.

    The endpoint serialises ``gcode`` + ``line_count`` to the wire and
    persists ``resolved`` to SQLite for traceability.
    """

    gcode: str
    line_count: int
    resolved: ResolvedPlan


def _placement_for_engine(resolved: ResolvedPlan) -> Placement | None:
    """Translate the domain ``PlacementPlan`` into the engine's model."""
    p = resolved.plan.placement
    if p is None:
        return None
    return Placement(
        sheet_width_mm=p.sheet_width_mm,
        sheet_height_mm=p.sheet_height_mm,
        offset_x_mm=p.offset_x_mm,
        offset_y_mm=p.offset_y_mm,
    )


def run_generate(plan: PrintPlan, profile: MachineProfile) -> GenerateOutcome:
    """Resolve and render a plan into engine-native output.

    Args:
        plan: The raw plan from the client.
        profile: The machine profile to render against.

    Returns:
        A :class:`GenerateOutcome` carrying the program and the
        resolved snapshot used to produce it.

    Raises:
        PlanResolutionError: If the plan fails business validation.
        ValueError: If the SVG is unparsable.
    """
    resolved = resolve_plan(plan, profile)
    generator = generate_ebb if profile.gcode_dialect == "ebb" else generate_gcode
    program = generator(
        resolved.plan.svg,
        profile,
        layers=resolved.plan.layers,
        scale_mode=resolved.plan.scale_mode,
        margin_mm=resolved.plan.margin_mm,
        placement=_placement_for_engine(resolved),
    )
    return GenerateOutcome(
        gcode=program,
        line_count=program.count("\n"),
        resolved=resolved,
    )

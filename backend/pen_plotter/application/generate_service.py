"""``run_generate``: the application use case behind ``POST /generate``.

The endpoint adapter only forwards the request and packs the response —
all decisions live here so a CLI or test runner can drive the exact
same pipeline without going through HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass

from pen_plotter.application.plan_resolver import resolve_plan
from pen_plotter.application.text_render import rerender_text_svg
from pen_plotter.core.ebb import generate_ebb
from pen_plotter.core.gcode import generate_gcode
from pen_plotter.domain.print_plan import PrintPlan, ResolvedPlan
from pen_plotter.models import MachineProfile, Placement


class MissingPenSlotsError(RuntimeError):
    """Raised when a plan targets pen slots that are not installed.

    Surfaced as ``409 Conflict`` by the endpoint adapter so the UI can
    prompt the operator to install the missing pens — or override with
    ``allow_missing_slots=True`` if they intend to swap pens manually
    when the firmware pauses on the M0 prompts.
    """

    def __init__(self, slots: list[int]) -> None:
        """Store the deduplicated, sorted list of unsatisfied slot indices."""
        self.slots = sorted(set(slots))
        super().__init__(
            f"Pen slots not installed: {', '.join(str(s) for s in self.slots)}"
        )


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


def run_generate(
    plan: PrintPlan,
    profile: MachineProfile,
    *,
    allow_missing_slots: bool = False,
) -> GenerateOutcome:
    """Resolve and render a plan into engine-native output.

    Args:
        plan: The raw plan from the client.
        profile: The machine profile to render against.
        allow_missing_slots: When ``False`` (the default), the call is
            refused with :class:`MissingPenSlotsError` if any layer
            targets a pen slot that is not installed in the magazine.
            Set to ``True`` to override — typically after the operator
            has been prompted and chosen to swap pens manually at the
            firmware M0 pause.

    Returns:
        A :class:`GenerateOutcome` carrying the program and the
        resolved snapshot used to produce it.

    Raises:
        PlanResolutionError: If the plan fails business validation.
        MissingPenSlotsError: If a layer targets a non-installed slot
            and the override is not set.
        ValueError: If the SVG is unparsable.
    """
    resolved = resolve_plan(plan, profile)

    if not allow_missing_slots:
        missing = [
            layer.target_pen_slot
            for layer in resolved.layers
            if layer.target_pen_slot is not None and not layer.pen_slot_installed
        ]
        if missing:
            raise MissingPenSlotsError(missing)

    # In-pipeline text rerender (post-L5): when the plan carries a
    # TypographyPlan + library_file_id + source_mime, re-render the
    # text source from the library bytes so the operator's font / page
    # / Hershey edits land without a re-upload. Falls back to the
    # plan's pre-rendered SVG when the rerender isn't applicable —
    # see ``application/text_render.py`` for the gating rules. The
    # rerender doesn't alter ``resolved`` (the plan_hash is computed
    # from typography fields, not from the SVG payload) so /preflight
    # + /generate keep agreeing on the same hash.
    svg = rerender_text_svg(resolved.plan) or resolved.plan.svg

    generator = generate_ebb if profile.gcode_dialect == "ebb" else generate_gcode
    program = generator(
        svg,
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

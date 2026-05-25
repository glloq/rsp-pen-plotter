"""``run_preflight``: the application use case behind ``POST /preflight``.

Shares ``resolve_plan`` with :mod:`generate_service` so any divergence
between the two endpoints is mechanically impossible — they consume the
exact same :class:`ResolvedPlan`.
"""

from __future__ import annotations

from dataclasses import dataclass

from pen_plotter.application.generate_service import _placement_for_engine
from pen_plotter.application.plan_resolver import resolve_plan
from pen_plotter.application.text_render import rerender_text_svg
from pen_plotter.core.preflight import preflight_report
from pen_plotter.domain.print_plan import PrintPlan, ResolvedPlan
from pen_plotter.models import MachineProfile, PreflightReport


@dataclass
class PreflightOutcome:
    """Bundle of everything ``run_preflight`` produces."""

    report: PreflightReport
    resolved: ResolvedPlan


def run_preflight(plan: PrintPlan, profile: MachineProfile) -> PreflightOutcome:
    """Resolve and analyse a plan without producing G-code.

    Args:
        plan: The raw plan from the client.
        profile: The machine profile to check against.

    Returns:
        A :class:`PreflightOutcome` carrying the report and the
        resolved snapshot (same hash as the one ``run_generate`` would
        produce for the same plan).

    Raises:
        PlanResolutionError: If the plan fails business validation.
        ValueError: If the SVG is unparsable.
    """
    resolved = resolve_plan(plan, profile)
    # Match generate_service: when the plan carries a TypographyPlan
    # + library_file_id + source_mime, re-render the text source so
    # the preflight metrics (path length, drawing time, bounds) reflect
    # the operator's latest typography edits — not the SVG that was
    # rendered at upload time. The rerender is opt-in + safe-fallback;
    # see ``application/text_render.py`` for the gating rules.
    svg = rerender_text_svg(resolved.plan) or resolved.plan.svg
    report = preflight_report(
        svg,
        profile,
        layers=resolved.plan.layers,
        scale_mode=resolved.plan.scale_mode,
        margin_mm=resolved.plan.margin_mm,
        placement=_placement_for_engine(resolved),
    )
    return PreflightOutcome(report=report, resolved=resolved)

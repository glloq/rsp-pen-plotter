"""Pre-run checks and time/length estimation for a placed drawing.

Reuses the same placement transform as G-code generation so the report
reflects exactly how the drawing will be plotted: workspace fit, pen-change
count, missing pens, and estimated drawing/travel time. Dialect-independent
(works for both G-code and EBB profiles).
"""

from __future__ import annotations

import math

from pen_plotter.core.gcode import (
    _bounds_of,
    _exceeds_workspace,
    _make_transform,
    _read_layers,
    sheet_exceeds_workspace,
)
from pen_plotter.domain.print_plan import LayerPlan, ScaleMode
from pen_plotter.models import MachineProfile, Placement, PreflightReport


def _polyline_length(points: list[tuple[float, float]]) -> float:
    """Total length of a polyline in its coordinate space."""
    return sum(
        math.dist(points[i], points[i + 1]) for i in range(len(points) - 1)
    )


def preflight_report(
    svg: str,
    profile: MachineProfile,
    *,
    layers: list[LayerPlan] | None = None,
    scale_mode: ScaleMode = "fit",
    margin_mm: float = 10.0,
    placement: Placement | None = None,
) -> PreflightReport:
    """Build a :class:`PreflightReport` for a pivot SVG and target profile.

    Args:
        svg: The normalized (typically optimized) SVG markup.
        profile: The target machine profile.
        layers: Per-layer pen-slot and speed settings.
        scale_mode: Placement mode, mirroring G-code generation.
        margin_mm: Margin used when ``scale_mode`` is ``"fit"``.

    Returns:
        A report with bounds, estimates, and any blocking warnings.
    """
    geometry = _read_layers(svg)
    overrides = {item.layer_id: item for item in (layers or [])}
    bounds = _bounds_of(geometry)
    transform = _make_transform(bounds, profile, scale_mode, margin_mm, placement)
    pens = {pen.index: pen for pen in profile.effective_pens()}

    warnings: list[str] = []
    within_bounds = bounds.empty or not _exceeds_workspace(bounds, transform, profile)
    if not within_bounds:
        warnings.append("The drawing exceeds the workspace; coordinates may be out of bounds.")
    if placement is not None and sheet_exceeds_workspace(profile, placement):
        warnings.append("Sheet exceeds the workspace; check sheet size and offset.")

    drawing_length = 0.0
    travel_length = 0.0
    drawing_time = 0.0
    travel_time = 0.0
    pen_changes = 0
    path_count = 0
    missing: list[int] = []
    previous_slot: int | None = None
    previous_color: str | None = None
    previous_end: tuple[float, float] | None = None
    travel_speed = max(profile.travel_speed_mm_s, 1e-9)
    mono_pen = profile.pen_slot_count <= 1

    for layer in geometry:
        setting = overrides.get(layer.label)
        slot = setting.target_pen_slot if setting else None
        source_color = setting.source_color if setting else None
        pause_before = setting.pause_before if setting else "auto"

        if slot is not None and slot not in missing:
            pen = pens.get(slot)
            if pen is None or not pen.installed:
                missing.append(slot)

        # Mirror the pause logic in ``generate_gcode`` so the count matches the
        # number of operator prompts the streamer will actually surface.
        slot_changed = slot is not None and slot != previous_slot
        color_changed = (
            mono_pen and source_color is not None and source_color != previous_color
        )
        first_pose = (
            mono_pen
            and previous_color is None
            and previous_slot is None
            and source_color is not None
        )
        will_pause = profile.tool_change_method != "none" and pause_before != "never" and (
            pause_before == "always" or slot_changed or color_changed or first_pose
        )
        if will_pause:
            pen_changes += 1
        if slot is not None:
            previous_slot = slot
        if source_color is not None:
            previous_color = source_color

        override_speed = setting.drawing_speed_mm_s if setting else None
        speed = max(override_speed or profile.drawing_speed_mm_s, 1e-9)

        for polyline in layer.polylines:
            machine_points = [transform(px, py) for px, py in polyline]
            path_count += 1
            if previous_end is not None:
                hop = math.dist(previous_end, machine_points[0])
                travel_length += hop
                travel_time += hop / travel_speed
            length = _polyline_length(machine_points)
            drawing_length += length
            drawing_time += length / speed
            previous_end = machine_points[-1]

    for slot in missing:
        warnings.append(f"Pen slot {slot} is assigned but not installed in the magazine.")

    if bounds.empty:
        width_mm = height_mm = scale = 0.0
    else:
        corners = [
            transform(bounds.x_min, bounds.y_min),
            transform(bounds.x_max, bounds.y_min),
            transform(bounds.x_min, bounds.y_max),
            transform(bounds.x_max, bounds.y_max),
        ]
        xs = [c[0] for c in corners]
        ys = [c[1] for c in corners]
        width_mm = max(xs) - min(xs)
        height_mm = max(ys) - min(ys)
        span = max(bounds.x_max - bounds.x_min, 1e-9)
        scale = width_mm / span

    return PreflightReport(
        ok=within_bounds and not missing,
        within_bounds=within_bounds,
        width_mm=width_mm,
        height_mm=height_mm,
        scale=scale,
        drawing_length_mm=drawing_length,
        travel_length_mm=travel_length,
        estimated_seconds=drawing_time + travel_time,
        pen_changes=pen_changes,
        layer_count=len(geometry),
        path_count=path_count,
        missing_pen_slots=missing,
        warnings=warnings,
    )

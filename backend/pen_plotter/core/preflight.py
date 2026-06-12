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
from pen_plotter.core.pause_logic import (
    effective_layer_pen,
    initial_slot_inks,
    installed_pen_hex_slots,
    should_pause,
)
from pen_plotter.domain.print_plan import LayerPlan, ScaleMode
from pen_plotter.models import MachineProfile, Placement, PreflightReport


def _polyline_length(points: list[tuple[float, float]]) -> float:
    """Total length of a polyline in its coordinate space."""
    return sum(math.dist(points[i], points[i + 1]) for i in range(len(points) - 1))


def _move_seconds(distance: float, speed: float, accel: float) -> float:
    """Time to cover ``distance`` under a trapezoidal velocity profile.

    The head accelerates from rest to ``speed`` at ``accel`` (mm/s²), cruises,
    then decelerates back to rest. Short moves never reach ``speed`` and follow
    a triangular profile instead. With ``accel <= 0`` the estimate falls back to
    the constant-velocity model so dialects without an acceleration limit (and
    misconfigured profiles) keep a sane number.
    """
    if distance <= 0.0:
        return 0.0
    if accel <= 0.0 or speed <= 0.0:
        return distance / max(speed, 1e-9)
    # Distance spent ramping up to (and back down from) the cruise speed.
    ramp_distance = speed * speed / accel
    if ramp_distance <= distance:
        cruise = distance - ramp_distance
        return 2.0 * (speed / accel) + cruise / speed
    # Triangular profile: peak speed is reached exactly at the midpoint.
    return 2.0 * math.sqrt(distance / accel)


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
        placement: Optional sheet rectangle inside the workspace.
            Mirrors the engine's behaviour so the report's bounds /
            warnings match what generation will actually do.

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
    pen_lift_time = 0.0
    pen_changes = 0
    path_count = 0
    pen_lift_seconds = max(profile.pen_lift_time_ms, 0.0) / 1000.0
    missing: list[int] = []
    previous_slot: int | None = None
    previous_color: str | None = None
    previous_end: tuple[float, float] | None = None
    travel_speed = max(profile.travel_speed_mm_s, 1e-9)
    accel = profile.acceleration_mm_s2
    mono_pen = profile.pen_slot_count <= 1
    pen_hex_to_slot = installed_pen_hex_slots(pens)
    # Per-slot ink tracking, mirrored from core.gcode: a layer that
    # reuses a slot with a different colour triggers a re-ink pause,
    # which must be counted here too.
    slot_inks = initial_slot_inks(pens)
    # Slots the plan actually draws from — feeds the rack-calibration
    # warning below (a host swap can only travel to calibrated slots).
    used_slots: set[int] = set()

    for layer in geometry:
        setting = overrides.get(layer.label)
        slot = setting.target_pen_slot if setting else None
        source_color = setting.source_color if setting else None
        pause_before = setting.pause_before if setting else "auto"
        assigned_hex = setting.assigned_color_hex if setting else None

        if slot is not None and slot not in missing:
            pen = pens.get(slot)
            if pen is None or not pen.installed:
                missing.append(slot)

        # Share the predicate AND the L7 assigned-colour promotion with
        # ``generate_gcode`` so the reported ``pen_changes`` count
        # exactly matches the M0 prompts the streamer will surface —
        # see core/pause_logic.
        effective_slot, effective_color = effective_layer_pen(
            slot=slot,
            source_color=source_color,
            assigned_color_hex=assigned_hex,
            pen_hex_to_slot=pen_hex_to_slot,
        )
        slot_reinked = (
            effective_slot is not None
            and effective_color is not None
            and slot_inks.get(effective_slot) is not None
            and slot_inks[effective_slot] != effective_color.lower()
        )
        if should_pause(
            slot=effective_slot,
            source_color=effective_color,
            pause_before=pause_before,
            previous_slot=previous_slot,
            previous_color=previous_color,
            mono_pen=mono_pen,
            tool_change_method=profile.tool_change_method,
            slot_reinked=slot_reinked,
        ).pause:
            pen_changes += 1
        if effective_slot is not None:
            previous_slot = effective_slot
            used_slots.add(effective_slot)
        if effective_color is not None:
            previous_color = effective_color
        if effective_slot is not None and effective_color is not None:
            slot_inks[effective_slot] = effective_color.lower()

        override_speed = setting.drawing_speed_mm_s if setting else None
        speed = max(override_speed or profile.drawing_speed_mm_s, 1e-9)

        for polyline in layer.polylines:
            machine_points = [transform(px, py) for px, py in polyline]
            path_count += 1
            if previous_end is not None:
                hop = math.dist(previous_end, machine_points[0])
                travel_length += hop
                travel_time += _move_seconds(hop, travel_speed, accel)
            # One pen-down before the stroke + one pen-up after it.
            # On drawings dominated by short paths the servo settling
            # time outweighs the motion time, so it has to be in the
            # estimate even though it's not a "move".
            pen_lift_time += 2.0 * pen_lift_seconds
            length = _polyline_length(machine_points)
            drawing_length += length
            drawing_time += _move_seconds(length, speed, accel)
            previous_end = machine_points[-1]

    for slot in missing:
        warnings.append(f"Pen slot {slot} is assigned but not installed in the magazine.")

    # Host (rack) swaps travel to each slot's CALIBRATED position; the
    # strategy silently skips move steps for uncalibrated slots, which
    # reads as "the head never goes to the rack". Surface it before the
    # run instead.
    if profile.tool_change_method == "rack":
        swap = profile.effective_capabilities().tool_change.host_swap
        needs_positions = bool(
            swap
            and any(s.kind in ("move_to_old_slot", "move_to_new_slot") for s in swap.steps)
        )
        if needs_positions:
            for slot in sorted(used_slots):
                pen = pens.get(slot)
                if pen is None or pen.position is None:
                    warnings.append(
                        f"Pen slot {slot} has no calibrated magazine position; "
                        "the host swap sequence will skip its move steps. "
                        "Calibrate it in the Colours tab."
                    )

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
        estimated_seconds=drawing_time + travel_time + pen_lift_time,
        pen_changes=pen_changes,
        layer_count=len(geometry),
        path_count=path_count,
        missing_pen_slots=missing,
        warnings=warnings,
    )

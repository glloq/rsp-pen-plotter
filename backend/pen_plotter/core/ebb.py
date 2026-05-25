"""EiBotBoard (EBB) program generation for AxiDraw-class plotters.

The EBB does not speak G-code: it takes relative stepper moves (``SM``) over a
duration, servo pen commands (``SP``), and motor enable/config (``EM``/``SC``).
The two motors form an H-bot, so a Cartesian move ``(dx, dy)`` maps to mixed
motor steps ``a = dx + dy`` and ``b = dx - dy`` (scaled by ``steps_per_mm``).

All parameters (steps/mm, servo positions, speeds, pen commands) come from the
machine profile, so supporting a new EBB machine needs only a new profile.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from pen_plotter.core.gcode import (
    _bounds_of,
    _make_transform,
    _read_layers,
)
from pen_plotter.domain.print_plan import LayerPlan, ScaleMode
from pen_plotter.models import EbbConfig, MachineProfile, Placement


def generate_ebb(
    svg: str,
    profile: MachineProfile,
    *,
    layers: list[LayerPlan] | None = None,
    scale_mode: ScaleMode = "fit",
    margin_mm: float = 10.0,
    placement: Placement | None = None,
) -> str:
    """Generate an EBB command program for a pivot SVG.

    Args:
        svg: The normalized (typically optimized) SVG markup.
        profile: The target machine profile (``gcode_dialect`` ``"ebb"``).
        layers: Per-layer speed settings; pen slots are ignored (EBB plotters
            have a single pen).
        scale_mode: ``"fit"`` scales the drawing into the workspace; ``"actual"``
            maps one user unit to one millimeter.
        margin_mm: Margin used when ``scale_mode`` is ``"fit"``.

    Returns:
        The EBB program as newline-separated commands.

    Raises:
        ValueError: If the SVG cannot be parsed.
    """
    cfg = profile.ebb or EbbConfig()
    spm = cfg.steps_per_mm
    try:
        layer_geometry = _read_layers(svg)
    except ET.ParseError as exc:
        raise ValueError(f"Could not parse SVG: {exc}") from exc

    overrides = {item.layer_id: item for item in (layers or [])}
    bounds = _bounds_of(layer_geometry)
    transform = _make_transform(bounds, profile, scale_mode, margin_mm, placement)

    out: list[str] = [
        f"; OmniPlot EBB program for {profile.name}",
        "EM,1,1",
        f"SC,4,{cfg.servo_down}",
        f"SC,5,{cfg.servo_up}",
        f"SC,11,{cfg.servo_rate}",
        profile.pen_up_command,
    ]

    # Track committed motor steps to avoid rounding drift across moves.
    pos_a = 0
    pos_b = 0
    cur_x = 0.0
    cur_y = 0.0

    def move(x_mm: float, y_mm: float, speed_mm_s: float) -> str | None:
        nonlocal pos_a, pos_b, cur_x, cur_y
        target_a = round((x_mm + y_mm) * spm)
        target_b = round((x_mm - y_mm) * spm)
        da = target_a - pos_a
        db = target_b - pos_b
        if da == 0 and db == 0:
            return None
        dist = ((x_mm - cur_x) ** 2 + (y_mm - cur_y) ** 2) ** 0.5
        duration_ms = max(1, round(dist / speed_mm_s * 1000.0)) if speed_mm_s > 0 else 1
        pos_a, pos_b = target_a, target_b
        cur_x, cur_y = x_mm, y_mm
        return f"SM,{duration_ms},{da},{db}"

    mono_pen = profile.pen_slot_count <= 1
    previous_color: str | None = None

    if not bounds.empty:
        for layer in layer_geometry:
            setting = overrides.get(layer.label)
            draw_speed = (
                setting.drawing_speed_mm_s if setting else None
            ) or profile.drawing_speed_mm_s

            # Mono-pen colour-change prompt: emit the same comment + pause
            # command used by the G-code path so the streamer can intercept
            # it via ``guided_pause_points``. The pause command never reaches
            # the EBB board (the streamer skips it).
            source_color = setting.source_color if setting else None
            color_label = setting.color_label if setting else None
            pause_before = setting.pause_before if setting else "auto"
            color_changed = (
                mono_pen and source_color is not None and source_color != previous_color
            )
            first_pose = (
                mono_pen and previous_color is None and source_color is not None
            )
            should_pause = (
                profile.tool_change_method == "manual_pause"
                and profile.tool_change_command.strip()
                and pause_before != "never"
                and (pause_before == "always" or color_changed or first_pose)
            )
            if should_pause:
                label = color_label or source_color or "#000000"
                color = source_color or "#000000"
                out.append(f"; Change pen: {label} ({color})")
                out.append(profile.tool_change_command)
            if source_color is not None:
                previous_color = source_color

            for polyline in layer.polylines:
                sx, sy = transform(*polyline[0])
                travel = move(sx, sy, profile.travel_speed_mm_s)
                if travel:
                    out.append(travel)
                out.append(profile.pen_down_command)
                for point in polyline[1:]:
                    mx, my = transform(*point)
                    line = move(mx, my, draw_speed)
                    if line:
                        out.append(line)
                out.append(profile.pen_up_command)

    out.append(profile.pen_up_command)
    out.append("EM,0,0")
    return "\n".join(out) + "\n"

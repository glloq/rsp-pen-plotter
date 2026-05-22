"""G-code generation from the pivot SVG.

Reads layer geometry (in SVG user units), places and scales it within the
target machine's workspace, and renders G-code via per-command Jinja2
templates. Pen up/down, tool changes, and feed rates are driven entirely by the
machine profile, so no plotter-specific logic lives here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from pen_plotter.core.arcs import ArcTo, fit_arcs
from pen_plotter.core.layers import labeled_group_fragments
from pen_plotter.core.toolpath import _doc_from_svg
from pen_plotter.models import MachineProfile

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_env = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    undefined=StrictUndefined,
    keep_trailing_newline=False,
    trim_blocks=True,
    lstrip_blocks=True,
)

ScaleMode = Literal["fit", "actual"]


@dataclass
class LayerGeneration:
    """Per-layer generation settings."""

    layer_id: str
    target_pen_slot: int | None = None
    drawing_speed_mm_s: float | None = None


@dataclass
class _Bounds:
    """Mutable accumulator for an axis-aligned bounding box."""

    x_min: float = float("inf")
    y_min: float = float("inf")
    x_max: float = float("-inf")
    y_max: float = float("-inf")

    def update(self, x: float, y: float) -> None:
        """Expand the bounds to include a point."""
        self.x_min, self.y_min = min(self.x_min, x), min(self.y_min, y)
        self.x_max, self.y_max = max(self.x_max, x), max(self.y_max, y)

    @property
    def empty(self) -> bool:
        """Whether no points have been added."""
        return self.x_min == float("inf")


@dataclass
class _Layer:
    """A layer's label and its polylines in user units."""

    label: str
    polylines: list[list[tuple[float, float]]] = field(default_factory=list)


def _read_layers(svg: str) -> list[_Layer]:
    """Read per-layer polyline geometry from the pivot SVG, in user units."""
    layers: list[_Layer] = []
    for label, fragment in labeled_group_fragments(svg):
        doc = _doc_from_svg(fragment)
        layer = _Layer(label=label)
        for collection in doc.layers.values():
            for line in collection:
                if len(line) >= 2:
                    layer.polylines.append([(p.real, p.imag) for p in line])
        layers.append(layer)
    return layers


def _bounds_of(layers: list[_Layer]) -> _Bounds:
    """Compute the combined bounding box of all geometry."""
    bounds = _Bounds()
    for layer in layers:
        for polyline in layer.polylines:
            for x, y in polyline:
                bounds.update(x, y)
    return bounds


def _make_transform(
    bounds: _Bounds, profile: MachineProfile, scale_mode: ScaleMode, margin_mm: float
) -> Callable[[float, float], tuple[float, float]]:
    """Build a function mapping user-unit points to workspace millimeters."""
    ws = profile.workspace
    ws_w, ws_h = ws.x_max - ws.x_min, ws.y_max - ws.y_min
    bbox_w = max(bounds.x_max - bounds.x_min, 1e-9)
    bbox_h = max(bounds.y_max - bounds.y_min, 1e-9)

    if scale_mode == "actual":
        scale = 1.0
    else:
        usable_w = max(ws_w - 2 * margin_mm, 1e-9)
        usable_h = max(ws_h - 2 * margin_mm, 1e-9)
        scale = min(usable_w / bbox_w, usable_h / bbox_h)

    bbox_cx = (bounds.x_min + bounds.x_max) / 2
    bbox_cy = (bounds.y_min + bounds.y_max) / 2
    ws_cx, ws_cy = (ws.x_min + ws.x_max) / 2, (ws.y_min + ws.y_max) / 2
    y_up = profile.origin in ("bottom_left", "center")

    def transform(x: float, y: float) -> tuple[float, float]:
        mx = ws_cx + (x - bbox_cx) * scale
        my = ws_cy + (y - bbox_cy) * scale * (-1 if y_up else 1)
        return mx, my

    return transform


def _exceeds_workspace(
    bounds: _Bounds,
    transform: Callable[[float, float], tuple[float, float]],
    profile: MachineProfile,
) -> bool:
    """Whether the transformed drawing falls outside the workspace bounds."""
    ws = profile.workspace
    tol = 0.01
    corners = [
        transform(bounds.x_min, bounds.y_min),
        transform(bounds.x_min, bounds.y_max),
        transform(bounds.x_max, bounds.y_min),
        transform(bounds.x_max, bounds.y_max),
    ]
    return any(
        x < ws.x_min - tol or x > ws.x_max + tol or y < ws.y_min - tol or y > ws.y_max + tol
        for x, y in corners
    )


def generate_gcode(
    svg: str,
    profile: MachineProfile,
    *,
    layers: list[LayerGeneration] | None = None,
    scale_mode: ScaleMode = "fit",
    margin_mm: float = 10.0,
) -> str:
    """Generate G-code for a pivot SVG targeting a machine profile.

    Args:
        svg: The normalized (typically optimized) SVG markup.
        profile: The target machine profile.
        layers: Per-layer pen-slot and speed settings, keyed by layer id.
        scale_mode: ``"fit"`` scales the drawing to the workspace (centered with
            a margin); ``"actual"`` maps one user unit to one millimeter.
        margin_mm: Margin used when ``scale_mode`` is ``"fit"``.

    Returns:
        The generated G-code as a single string.

    Raises:
        ValueError: If the SVG cannot be parsed.
    """
    layer_geometry = _read_layers(svg)

    overrides = {item.layer_id: item for item in (layers or [])}
    bounds = _bounds_of(layer_geometry)
    transform = _make_transform(bounds, profile, scale_mode, margin_mm)

    header_t = _env.get_template("header.j2")
    footer_t = _env.get_template("footer.j2")
    pen_up_t = _env.get_template("pen_up.j2")
    pen_down_t = _env.get_template("pen_down.j2")
    line_t = _env.get_template("line.j2")
    travel_t = _env.get_template("travel.j2")
    arc_t = _env.get_template("arc.j2")
    tool_change_t = _env.get_template("tool_change.j2")

    pens = {pen.index: pen for pen in profile.effective_pens()}

    out: list[str] = [header_t.render(profile=profile)]
    if not bounds.empty and _exceeds_workspace(bounds, transform, profile):
        out.append("; WARNING: drawing exceeds the workspace; coordinates may be out of bounds")
    previous_slot: int | None = None

    if not bounds.empty:
        for layer in layer_geometry:
            setting = overrides.get(layer.label)
            slot = setting.target_pen_slot if setting else None
            if profile.tool_change_method != "none" and slot is not None and slot != previous_slot:
                pen = pens.get(slot)
                if pen is None or not pen.installed:
                    out.append(f"; WARNING: pen slot {slot} is not installed in the magazine")
                pen_name = pen.name if pen and pen.name else f"Pen {slot}"
                out.append(tool_change_t.render(profile=profile, slot=slot, pen_name=pen_name))
                previous_slot = slot

            speed = (setting.drawing_speed_mm_s if setting else None) or profile.drawing_speed_mm_s
            feed = speed * 60.0

            # Per-slot calibration overrides the profile pen commands when set.
            pen = pens.get(slot) if slot is not None else None
            pen_up_line = (pen and pen.pen_up_command) or pen_up_t.render(profile=profile)
            pen_down_line = (pen and pen.pen_down_command) or pen_down_t.render(profile=profile)

            for polyline in layer.polylines:
                machine_points = [transform(px, py) for px, py in polyline]
                start = machine_points[0]
                out.append(pen_up_line)
                out.append(travel_t.render(x=start[0], y=start[1]))
                out.append(pen_down_line)
                if profile.supports_arcs:
                    prev = start
                    for seg in fit_arcs(machine_points, profile.arc_tolerance_mm):
                        if isinstance(seg, ArcTo):
                            out.append(
                                arc_t.render(
                                    x=seg.x,
                                    y=seg.y,
                                    i=seg.cx - prev[0],
                                    j=seg.cy - prev[1],
                                    clockwise=seg.clockwise,
                                    feed=feed,
                                )
                            )
                        else:
                            out.append(line_t.render(x=seg.x, y=seg.y, feed=feed))
                        prev = (seg.x, seg.y)
                else:
                    for mx, my in machine_points[1:]:
                        out.append(line_t.render(x=mx, y=my, feed=feed))

    out.append(
        footer_t.render(
            profile=profile, home_x=profile.workspace.x_min, home_y=profile.workspace.y_min
        )
    )
    return "\n".join(out) + "\n"

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
from xml.etree import ElementTree as ET

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from pen_plotter.core.layers import _INKSCAPE_LABEL, _group_to_svg, _local
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
    root = ET.fromstring(svg)
    viewbox = root.get("viewBox")
    groups = [
        child
        for child in root
        if _local(child.tag) == "g" and child.get(_INKSCAPE_LABEL) is not None
    ]
    fragments: list[tuple[str, str]]
    if groups:
        fragments = [
            (group.get(_INKSCAPE_LABEL) or f"layer-{i + 1}", _group_to_svg(viewbox, group))
            for i, group in enumerate(groups)
        ]
    else:
        fragments = [("layer-1", svg)]

    layers: list[_Layer] = []
    for label, fragment in fragments:
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
    try:
        layer_geometry = _read_layers(svg)
    except ET.ParseError as exc:
        raise ValueError(f"Could not parse SVG: {exc}") from exc

    overrides = {item.layer_id: item for item in (layers or [])}
    bounds = _bounds_of(layer_geometry)
    transform = _make_transform(bounds, profile, scale_mode, margin_mm)

    header_t = _env.get_template("header.j2")
    footer_t = _env.get_template("footer.j2")
    pen_up_t = _env.get_template("pen_up.j2")
    pen_down_t = _env.get_template("pen_down.j2")
    line_t = _env.get_template("line.j2")
    travel_t = _env.get_template("travel.j2")
    tool_change_t = _env.get_template("tool_change.j2")

    out: list[str] = [header_t.render(profile=profile)]
    previous_slot: int | None = None

    if not bounds.empty:
        for layer in layer_geometry:
            setting = overrides.get(layer.label)
            slot = setting.target_pen_slot if setting else None
            if profile.tool_change_method != "none" and slot is not None and slot != previous_slot:
                out.append(tool_change_t.render(profile=profile, slot=slot))
                previous_slot = slot

            speed = (setting.drawing_speed_mm_s if setting else None) or profile.drawing_speed_mm_s
            feed = speed * 60.0

            for polyline in layer.polylines:
                start = transform(*polyline[0])
                out.append(pen_up_t.render(profile=profile))
                out.append(travel_t.render(x=start[0], y=start[1]))
                out.append(pen_down_t.render(profile=profile))
                for point in polyline[1:]:
                    mx, my = transform(*point)
                    out.append(line_t.render(x=mx, y=my, feed=feed))

    out.append(
        footer_t.render(
            profile=profile, home_x=profile.workspace.x_min, home_y=profile.workspace.y_min
        )
    )
    return "\n".join(out) + "\n"

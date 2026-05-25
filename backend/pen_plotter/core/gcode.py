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

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from pen_plotter.core.arcs import ArcTo, fit_arcs
from pen_plotter.core.layers import labeled_group_fragments
from pen_plotter.core.toolpath import _doc_from_svg
from pen_plotter.domain.print_plan import LayerPlan, ScaleMode
from pen_plotter.models import MachineProfile, Placement

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_env = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    undefined=StrictUndefined,
    keep_trailing_newline=False,
    trim_blocks=True,
    lstrip_blocks=True,
)

# Legacy alias kept so older test modules (and any external callers)
# importing ``LayerGeneration`` from ``core.gcode`` keep working after
# the dataclass was promoted to a Pydantic model in ``domain.print_plan``.
LayerGeneration = LayerPlan


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


def _drawable_region(
    profile: MachineProfile, placement: Placement | None
) -> tuple[float, float, float, float]:
    """Return ``(x_min, y_min, width, height)`` of the area to fit the drawing in.

    Without ``placement`` we draw across the whole workspace (backwards compat).
    With ``placement`` we restrict to the sheet rectangle, positioned at the
    supplied offset inside the workspace.
    """
    ws = profile.workspace
    if placement is None:
        return ws.x_min, ws.y_min, ws.x_max - ws.x_min, ws.y_max - ws.y_min
    return (
        ws.x_min + placement.offset_x_mm,
        ws.y_min + placement.offset_y_mm,
        placement.sheet_width_mm,
        placement.sheet_height_mm,
    )


def _make_transform(
    bounds: _Bounds,
    profile: MachineProfile,
    scale_mode: ScaleMode,
    margin_mm: float,
    placement: Placement | None = None,
) -> Callable[[float, float], tuple[float, float]]:
    """Build a function mapping user-unit points to workspace millimeters.

    The drawing is centred in the *drawable region* — either the workspace
    (default) or the sheet rectangle when ``placement`` is supplied.
    """
    region_x, region_y, region_w, region_h = _drawable_region(profile, placement)
    bbox_w = max(bounds.x_max - bounds.x_min, 1e-9)
    bbox_h = max(bounds.y_max - bounds.y_min, 1e-9)

    if scale_mode == "actual":
        scale = 1.0
    else:
        usable_w = max(region_w - 2 * margin_mm, 1e-9)
        usable_h = max(region_h - 2 * margin_mm, 1e-9)
        scale = min(usable_w / bbox_w, usable_h / bbox_h)

    bbox_cx = (bounds.x_min + bounds.x_max) / 2
    bbox_cy = (bounds.y_min + bounds.y_max) / 2
    region_cx = region_x + region_w / 2
    region_cy = region_y + region_h / 2
    y_up = profile.origin in ("bottom_left", "center")
    # For Y-up profiles, the operator's mental model is "top of the work plan
    # = top of the paper". The composite SVG carries geometry with Y growing
    # downward, so we mirror around the workspace centre after positioning.
    # Doing the flip at the bbox/region centre instead would mirror the
    # content *inside* its own footprint — the on-screen sheet preview and
    # the gcode simulator would no longer agree on where the drawing sits.
    ws = profile.workspace
    y_mirror = ws.y_min + ws.y_max

    def transform(x: float, y: float) -> tuple[float, float]:
        mx = region_cx + (x - bbox_cx) * scale
        my = region_cy + (y - bbox_cy) * scale
        if y_up:
            my = y_mirror - my
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


def sheet_exceeds_workspace(profile: MachineProfile, placement: Placement) -> bool:
    """Whether the sheet rectangle falls outside the workspace bounds."""
    ws = profile.workspace
    tol = 0.01
    return (
        placement.offset_x_mm < -tol
        or placement.offset_y_mm < -tol
        or placement.offset_x_mm + placement.sheet_width_mm > (ws.x_max - ws.x_min) + tol
        or placement.offset_y_mm + placement.sheet_height_mm > (ws.y_max - ws.y_min) + tol
    )


def generate_gcode(
    svg: str,
    profile: MachineProfile,
    *,
    layers: list[LayerPlan] | None = None,
    scale_mode: ScaleMode = "fit",
    margin_mm: float = 10.0,
    placement: Placement | None = None,
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
    transform = _make_transform(bounds, profile, scale_mode, margin_mm, placement)

    header_t = _env.get_template("header.j2")
    footer_t = _env.get_template("footer.j2")
    pen_up_t = _env.get_template("pen_up.j2")
    pen_down_t = _env.get_template("pen_down.j2")
    line_t = _env.get_template("line.j2")
    travel_t = _env.get_template("travel.j2")
    arc_t = _env.get_template("arc.j2")
    tool_change_t = _env.get_template("tool_change.j2")
    pen_color_change_t = _env.get_template("pen_color_change.j2")

    pens = {pen.index: pen for pen in profile.effective_pens()}
    mono_pen = profile.pen_slot_count <= 1

    out: list[str] = [header_t.render(profile=profile)]
    if placement is not None and sheet_exceeds_workspace(profile, placement):
        out.append("; WARNING: sheet exceeds the workspace; check sheet size and offset")
    if not bounds.empty and _exceeds_workspace(bounds, transform, profile):
        out.append("; WARNING: drawing exceeds the workspace; coordinates may be out of bounds")
    previous_slot: int | None = None
    previous_color: str | None = None

    if not bounds.empty:
        for layer in layer_geometry:
            setting = overrides.get(layer.label)
            slot = setting.target_pen_slot if setting else None
            source_color = setting.source_color if setting else None
            color_label = setting.color_label if setting else None
            pause_before = setting.pause_before if setting else "auto"

            slot_changed = slot is not None and slot != previous_slot
            color_changed = (
                mono_pen
                and source_color is not None
                and source_color != previous_color
            )
            # First pose on a mono-pen machine: ask the operator to install the
            # initial pen before drawing anything. Multi-pen profiles still
            # rely on the slot-change check above (covered by ``slot_changed``).
            first_pose = (
                mono_pen
                and previous_color is None
                and previous_slot is None
                and source_color is not None
            )

            should_pause = profile.tool_change_method != "none" and pause_before != "never" and (
                pause_before == "always" or slot_changed or color_changed or first_pose
            )
            if should_pause:
                if slot_changed:
                    pen = pens.get(slot)  # type: ignore[arg-type]
                    if pen is None or not pen.installed:
                        out.append(f"; WARNING: pen slot {slot} is not installed in the magazine")
                    pen_name = pen.name if pen and pen.name else f"Pen {slot}"
                    out.append(
                        tool_change_t.render(profile=profile, slot=slot, pen_name=pen_name)
                    )
                else:
                    # Mono-pen path (or "always"/initial pause without slot): emit
                    # a colour-themed prompt so the streamer can guide the swap.
                    color = source_color or "#000000"
                    label = color_label or color
                    out.append(
                        pen_color_change_t.render(profile=profile, color=color, label=label)
                    )

            if slot is not None:
                previous_slot = slot
            if source_color is not None:
                previous_color = source_color

            # Always emit a layer-info marker so downstream consumers (the
            # simulator UI in particular) can attribute every G-code line
            # to a layer / colour / pen slot, even when no pause was
            # triggered. The comment is purely informational — firmwares
            # ignore it — and machine-readable: a fixed-shape key/value
            # block so the frontend parser can split on whitespace.
            layer_color = source_color or ""
            layer_label = (color_label or layer.label or "").replace('"', "'")
            layer_slot = "" if slot is None else str(slot)
            out.append(
                f'; LAYER label="{layer_label}" color={layer_color} slot={layer_slot}'
            )

            speed = (setting.drawing_speed_mm_s if setting else None) or profile.drawing_speed_mm_s
            feed = speed * 60.0

            # Per-slot calibration overrides the profile pen commands when set.
            pen = pens.get(slot) if slot is not None else None
            pen_up_line = (pen and pen.pen_up_command) or pen_up_t.render(profile=profile)
            pen_down_line = (pen and pen.pen_down_command) or pen_down_t.render(profile=profile)

            travel_feed = profile.travel_speed_mm_s * 60.0

            for polyline in layer.polylines:
                machine_points = [transform(px, py) for px, py in polyline]
                start = machine_points[0]
                out.append(pen_up_line)
                out.append(travel_t.render(x=start[0], y=start[1], feed=travel_feed))
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
            profile=profile,
            home_x=profile.workspace.x_min,
            home_y=profile.workspace.y_min,
            travel_feed=profile.travel_speed_mm_s * 60.0,
        )
    )
    return "\n".join(out) + "\n"

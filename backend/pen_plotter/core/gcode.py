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

from jinja2 import Environment, FileSystemLoader, StrictUndefined, meta

from pen_plotter.core.arcs import ArcTo, fit_arcs
from pen_plotter.core.layers import labeled_group_fragments
from pen_plotter.core.pause_logic import should_pause
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

# Variables each template is expected to receive from ``generate_gcode``.
# Verified at import time against the template AST: if a template grows
# a new ``{{ ... }}`` reference and gcode.py isn't updated to pass it,
# the backend refuses to boot with a precise error pointing at the
# deployment desync instead of failing at the next /generate with a
# generic ``'X' is undefined`` 422. Add to this map whenever a new
# template variable is introduced; the verifier will tell you what's
# missing.
_TEMPLATE_EXPECTED_VARS: dict[str, frozenset[str]] = {
    "header.j2": frozenset({"profile"}),
    "footer.j2": frozenset({"profile", "home_x", "home_y", "travel_feed"}),
    "pen_up.j2": frozenset({"profile"}),
    "pen_down.j2": frozenset({"profile"}),
    "tool_change.j2": frozenset({"profile", "slot", "pen_name"}),
    "pen_color_change.j2": frozenset({"profile", "color", "label"}),
    "line.j2": frozenset({"x", "y", "feed"}),
    "travel.j2": frozenset({"x", "y", "feed"}),
    "arc.j2": frozenset({"x", "y", "i", "j", "clockwise", "feed"}),
}


# Pre-resolved at import — Jinja caches templates internally, but the
# first /generate call still pays the lookup + compile cost. Hoisting
# saves ~100 ms cold-cache on the gcode phase (see docs/perf-report.md).
_HEADER_T = _env.get_template("header.j2")
_FOOTER_T = _env.get_template("footer.j2")
_PEN_UP_T = _env.get_template("pen_up.j2")
_PEN_DOWN_T = _env.get_template("pen_down.j2")
_LINE_T = _env.get_template("line.j2")
_TRAVEL_T = _env.get_template("travel.j2")
_ARC_T = _env.get_template("arc.j2")
_TOOL_CHANGE_T = _env.get_template("tool_change.j2")
_PEN_COLOR_CHANGE_T = _env.get_template("pen_color_change.j2")


def _verify_template_contract() -> None:
    """Boot-time guard: refuse to start if templates use undeclared variables.

    The class of bug this catches is a deployment desync — usually a
    stale ``__pycache__`` next to freshly-pulled templates, or a partial
    rebuild that updated one half of the (template, gcode.py) pair but
    not the other. Without this check the first /generate call surfaces
    as ``Generation failed: '<var>' is undefined`` (a 422 from a generic
    Exception catch), which is opaque to the operator and untraceable
    in logs. With this check, the same desync raises a precise
    ``RuntimeError`` at module import with the offending variable name +
    a fix-it hint, so it ends up in the uvicorn startup log instead of
    blocking the operator's first print.
    """
    for name, expected in _TEMPLATE_EXPECTED_VARS.items():
        source, _, _ = _env.loader.get_source(_env, name)  # type: ignore[union-attr]
        ast = _env.parse(source)
        used = meta.find_undeclared_variables(ast)
        unexpected = used - expected
        if unexpected:
            raise RuntimeError(
                f"G-code template {name!r} uses variable(s) "
                f"{sorted(unexpected)} that ``generate_gcode`` does not pass. "
                "This is a deployment desync — the templates on disk are "
                "newer than the compiled Python in ``__pycache__`` (or vice "
                "versa). Purge __pycache__ + restart, or update "
                "``_TEMPLATE_EXPECTED_VARS`` in core/gcode.py if you added "
                "a new variable to this template intentionally."
            )


_verify_template_contract()

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


def generate_gcode_from_geometry(
    geometry: object,
    profile: MachineProfile,
    *,
    layers: list[LayerPlan] | None = None,
    scale_mode: ScaleMode = "fit",
    margin_mm: float = 10.0,
    placement: Placement | None = None,
) -> str:
    """Generate G-code from a :class:`GeometryIR` artifact.

    Counterpart of :func:`pen_plotter.core.toolpath.optimize_geometry_ir`:
    closes the IR loop on the G-code side so a consumer running with
    ``OMNIPLOT_IR_ENABLED=1`` can route both phases through typed IR
    artifacts. Today the IR is rebuilt into the labelled SVG pivot
    via :func:`pen_plotter.core.toolpath._geometry_ir_to_svg` and the
    SVG path takes over; future iterations can emit G-code directly
    from the polyline lists.

    Surface is stable so downstream code can opt into the IR
    pipeline without waiting for the inner SVG round-trip to be
    removed.
    """
    from pen_plotter.core.toolpath import _geometry_ir_to_svg

    svg = _geometry_ir_to_svg(geometry)
    return generate_gcode(
        svg,
        profile,
        layers=layers,
        scale_mode=scale_mode,
        margin_mm=margin_mm,
        placement=placement,
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
        placement: Optional sheet rectangle inside the workspace. When
            supplied, ``scale_mode`` operates against this sub-region
            instead of the full workspace, and the homing G0 lands at
            the rectangle's offset rather than the workspace origin.

    Returns:
        The generated G-code as a single string.

    Raises:
        ValueError: If the SVG cannot be parsed.
    """
    from pen_plotter.observability import traced_span

    with traced_span(
        "pipeline.generate_gcode",
        svg_bytes=len(svg),
        profile_name=profile.name,
        scale_mode=scale_mode,
    ):
        return _generate_gcode_impl(
            svg, profile, layers=layers, scale_mode=scale_mode,
            margin_mm=margin_mm, placement=placement,
        )


def _generate_gcode_impl(
    svg: str,
    profile: MachineProfile,
    *,
    layers: list[LayerPlan] | None,
    scale_mode: ScaleMode,
    margin_mm: float,
    placement: Placement | None,
) -> str:
    layer_geometry = _read_layers(svg)

    overrides = {item.layer_id: item for item in (layers or [])}
    bounds = _bounds_of(layer_geometry)
    transform = _make_transform(bounds, profile, scale_mode, margin_mm, placement)

    header_t = _HEADER_T
    footer_t = _FOOTER_T
    pen_up_t = _PEN_UP_T
    pen_down_t = _PEN_DOWN_T
    line_t = _LINE_T
    travel_t = _TRAVEL_T
    arc_t = _ARC_T
    tool_change_t = _TOOL_CHANGE_T
    pen_color_change_t = _PEN_COLOR_CHANGE_T

    pens = {pen.index: pen for pen in profile.effective_pens()}
    mono_pen = profile.pen_slot_count <= 1

    out: list[str] = [header_t.render(profile=profile)]
    if placement is not None and sheet_exceeds_workspace(profile, placement):
        out.append("; WARNING: sheet exceeds the workspace; check sheet size and offset")
    if not bounds.empty and _exceeds_workspace(bounds, transform, profile):
        out.append("; WARNING: drawing exceeds the workspace; coordinates may be out of bounds")
    previous_slot: int | None = None
    previous_color: str | None = None

    # Pre-compute hex → installed-pen-slot index so the assignment can
    # promote a mono-pen swap into a tool-change when the operator's
    # picked hex matches a mounted slot. Lower-cased lookup so case
    # differences across the inventory ↔ profile YAML don't miss matches.
    pen_hex_to_slot: dict[str, int] = {}
    for pen_index, slot_pen in pens.items():
        if slot_pen.installed and slot_pen.color:
            pen_hex_to_slot.setdefault(slot_pen.color.lower(), pen_index)

    if not bounds.empty:
        for layer in layer_geometry:
            setting = overrides.get(layer.label)
            slot = setting.target_pen_slot if setting else None
            source_color = setting.source_color if setting else None
            color_label = setting.color_label if setting else None
            pause_before = setting.pause_before if setting else "auto"
            assigned_hex = setting.assigned_color_hex if setting else None

            # L7: when the operator picked an assigned colour AND it
            # matches an installed pen by hex, promote the prompt to a
            # proper tool-change with the magazine slot. Without a
            # matching pen we still surface the assigned hex in the
            # mono-pen swap prompt so the operator knows which Sharpie
            # to grab — the assignment was made against the active
            # pool (pens / available / union) at /upload time.
            promoted_slot: int | None = None
            if assigned_hex and slot is None:
                promoted_slot = pen_hex_to_slot.get(assigned_hex.lower())
            effective_slot = slot if slot is not None else promoted_slot
            effective_color = assigned_hex or source_color

            decision = should_pause(
                slot=effective_slot,
                source_color=effective_color,
                pause_before=pause_before,
                previous_slot=previous_slot,
                previous_color=previous_color,
                mono_pen=mono_pen,
                tool_change_method=profile.tool_change_method,
            )
            if decision.pause:
                if decision.slot_changed:
                    prompt_pen = (
                        pens.get(effective_slot) if effective_slot is not None else None
                    )
                    if prompt_pen is None or not prompt_pen.installed:
                        out.append(
                            f"; WARNING: pen slot {effective_slot} is not installed in the magazine"
                        )
                    pen_name = (
                        prompt_pen.name
                        if prompt_pen and prompt_pen.name
                        else f"Pen {effective_slot}"
                    )
                    out.append(
                        tool_change_t.render(
                            profile=profile, slot=effective_slot, pen_name=pen_name
                        )
                    )
                else:
                    # Mono-pen path (or "always"/initial pause without slot): emit
                    # a colour-themed prompt so the streamer can guide the swap.
                    color = effective_color or "#000000"
                    label = color_label or color
                    out.append(
                        pen_color_change_t.render(profile=profile, color=color, label=label)
                    )

            if effective_slot is not None:
                previous_slot = effective_slot
            if effective_color is not None:
                previous_color = effective_color

            # Always emit a layer-info marker so downstream consumers (the
            # simulator UI in particular) can attribute every G-code line
            # to a layer / colour / pen slot, even when no pause was
            # triggered. The comment is purely informational — firmwares
            # ignore it — and machine-readable: a fixed-shape key/value
            # block so the frontend parser can split on whitespace.
            # ``layer_color`` reflects the *assigned* hex when set so the
            # simulator highlights the chosen ink rather than the raw
            # centroid the operator overrode.
            layer_color = effective_color or ""
            layer_label = (color_label or layer.label or "").replace('"', "'")
            layer_slot = "" if effective_slot is None else str(effective_slot)
            out.append(
                f'; LAYER label="{layer_label}" color={layer_color} slot={layer_slot}'
            )
            slot = effective_slot

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

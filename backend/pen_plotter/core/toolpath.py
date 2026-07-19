"""Toolpath optimization via vpype.

Runs vpype's ``linemerge -> linesimplify -> linesort`` pipeline on each layer
to reduce pen-up travel, preserving layer labels and colors, then refines the
resulting order with :mod:`pen_plotter.core.pathsort` (closed-loop seam
rotation + time-budgeted 2-opt — see
``docs/audit_optimisation_trace_2026-07-19.md`` §F2 for the measured gains).
Optimization operates per labeled group so that the layer identity
established during extraction is retained. Geometry is processed in the
SVG's user-unit coordinate system (its ``viewBox``), so tolerances are
passed as bare numbers.
"""

from __future__ import annotations

import io
import re
from typing import Any
from xml.etree import ElementTree as ET
from xml.sax.saxutils import quoteattr

import numpy as np
import vpype as vp
import vpype_cli
from pydantic import BaseModel

from pen_plotter.core.layers import (
    _INKSCAPE_LABEL,
    _group_color,
    _group_to_svg,
    _local,
    strip_root_size,
)
from pen_plotter.core.pathsort import improve_order
from pen_plotter.core.svg_ns import INKSCAPE_NS as _INKSCAPE_NS
from pen_plotter.core.svg_ns import SVG_NS as _SVG_NS
from pen_plotter.observability import traced_span

_QUANTIZATION = 0.5

# Time budget for the 2-opt refinement pass, per layer. Chosen to match
# ``core.tsp.two_opt_improve``'s default: enough for the measured −6…−13 %
# pen-up gain on thousand-path layers, bounded so a Pi-class device never
# stalls the /optimize call.
_TWO_OPT_BUDGET_S = 1.5


class LayerOptimization(BaseModel):
    """Per-layer optimization settings supplied by the client."""

    layer_id: str
    optimize: bool = True
    simplify_tolerance_mm: float = 0.05
    # Allow closed loops to start anywhere along their perimeter so the
    # sorter can enter them at the nearest vertex. Moves the visible seam
    # of each loop to wherever the travel path lands — opt out for plots
    # where the original seam placement matters aesthetically.
    seam_rotation: bool = True


class ToolpathMetrics(BaseModel):
    """Pen-up travel before and after optimization, in SVG user units."""

    pen_up_before_mm: float
    pen_up_after_mm: float
    reduction_pct: float


class ToolpathResult(BaseModel):
    """Optimized SVG plus travel metrics."""

    svg: str
    metrics: ToolpathMetrics


def _doc_from_svg(group_svg: str) -> vp.Document:
    """Read a self-contained SVG into a vpype document in user units."""
    stripped = strip_root_size(group_svg)
    return vp.read_multilayer_svg(io.StringIO(stripped), quantization=_QUANTIZATION)


def _doc_to_path_d(doc: vp.Document) -> str:
    """Serialize every line in a document as a single SVG path ``d`` string."""
    subpaths: list[str] = []
    for layer in doc.layers.values():
        for line in layer:
            if len(line) < 2:
                continue
            points = " L".join(f"{p.real:.3f} {p.imag:.3f}" for p in line)
            subpaths.append(f"M{points}")
    return " ".join(subpaths)


def _optimized_group(label: str, color: str, doc: vp.Document) -> str:
    """Build a labeled, colored SVG group from optimized geometry."""
    path_d = _doc_to_path_d(doc)
    body = f'<path d="{path_d}"/>' if path_d else ""
    return f'<g inkscape:label={quoteattr(label)} fill="none" stroke={quoteattr(color)}>{body}</g>'


def _pipeline(simplify_tolerance_mm: float, merge_tolerance_mm: float) -> str:
    """Build the vpype optimization pipeline string (tolerances in user units)."""
    return (
        f"linemerge --tolerance {merge_tolerance_mm} "
        f"linesimplify --tolerance {simplify_tolerance_mm} "
        "linesort"
    )


def _detect_units_per_mm(root: ET.Element) -> float | None:
    """Auto-detect units_per_mm from SVG root element width and viewBox.

    Parses ``width`` attribute with physical units (mm/cm/in) and divides
    by ``viewBox`` width to get the conversion factor. Returns None if
    width has no unit (px) or is absent, value is non-positive, or viewBox
    is missing.
    """
    width_str = root.get("width")
    if not width_str:
        return None

    # Parse width with regex: "^([0-9.]+)\s*(mm|cm|in)$"
    match = re.match(r"^([0-9.]+)\s*(mm|cm|in)$", width_str.strip())
    if not match:
        return None

    width_value = float(match.group(1))
    unit = match.group(2)

    # Convert to mm
    unit_factors = {"mm": 1.0, "cm": 10.0, "in": 25.4}
    width_mm = width_value * unit_factors[unit]

    if width_mm <= 0:
        return None

    # Get viewBox width
    viewbox_str = root.get("viewBox")
    if not viewbox_str:
        return None

    try:
        parts = viewbox_str.split()
        if len(parts) < 4:
            return None
        vb_width = float(parts[2])
    except (ValueError, IndexError):
        return None

    if vb_width <= 0:
        return None

    return vb_width / width_mm


def _refine_doc_order(doc: vp.Document, *, seam_rotation: bool, closed_tolerance: float) -> None:
    """Refine each layer's path order in place after the vpype pipeline.

    Applies :func:`pen_plotter.core.pathsort.improve_order` (closed-loop
    seam rotation + time-budgeted 2-opt) on top of ``linesort``'s greedy
    result. ``improve_order`` never returns a worse order than its input,
    so the reported ``pen_up_after_mm`` can only shrink.
    """
    for layer_id, layer in doc.layers.items():
        # No length filter: every line must survive the round-trip, even a
        # degenerate single-point one, or geometry would silently vanish.
        lines = [np.asarray(line) for line in layer]
        if len(lines) < 3:
            continue
        improved = improve_order(
            lines,
            seam_rotation=seam_rotation,
            closed_tolerance=max(closed_tolerance, 1e-6),
            two_opt_budget_s=_TWO_OPT_BUDGET_S,
        )
        doc.replace(improved, layer_id)


def optimize_svg(
    svg: str,
    *,
    layers: list[LayerOptimization] | None = None,
    merge_tolerance_mm: float = 0.1,
    units_per_mm: float | None = None,
) -> ToolpathResult:
    """Optimize toolpaths in a pivot SVG, reducing pen-up travel.

    Args:
        svg: The normalized SVG markup.
        layers: Per-layer settings; layers absent from the list are optimized
            with default settings. Layers with ``optimize=False`` are passed
            through unchanged.
        merge_tolerance_mm: Endpoint join tolerance for ``linemerge``.
        units_per_mm: Optional scale factor (user units per millimeter). When
            provided or auto-detected, tolerances are scaled accordingly.
            Falls back to 1.0 (no scaling).

    Returns:
        A :class:`ToolpathResult` with the optimized SVG and travel metrics.

    Raises:
        ValueError: If the SVG cannot be parsed.
    """
    with traced_span(
        "pipeline.optimize_svg",
        svg_bytes=len(svg),
        layer_count=len(layers or []),
    ):
        return _optimize_svg(
            svg, layers=layers, merge_tolerance_mm=merge_tolerance_mm, units_per_mm=units_per_mm
        )


def _doc_from_ir_layer(layer: Any) -> vp.Document:
    """Build a single-layer vpype document straight from IR polylines.

    Direct counterpart of :func:`_doc_from_svg` for the typed pipeline —
    no SVG serialisation, no XML parse. Closed polylines are explicitly
    closed (first point re-appended) to match what the SVG round-trip
    produced via ``<polygon>`` elements.
    """
    collection = vp.LineCollection()
    for poly in getattr(layer, "polylines", []) or []:
        pts = getattr(poly, "points", []) or []
        if len(pts) < 2:
            continue
        line = np.array([complex(float(x), float(y)) for x, y in pts])
        if getattr(poly, "closed", False) and line[0] != line[-1]:
            line = np.append(line, line[0])
        collection.append(line)
    doc = vp.Document()
    doc.add(collection, layer_id=1)
    return doc


def optimize_geometry_ir(
    geometry: Any,
    *,
    layers: list[LayerOptimization] | None = None,
    merge_tolerance_mm: float = 0.1,
    units_per_mm: float | None = None,
) -> ToolpathResult:
    """Optimize toolpaths starting from a :class:`GeometryIR` artifact.

    Direct vpype consumer (v2 roadmap 2.1a): each IR layer's polylines
    feed a :class:`vpype.Document` straight from the typed lists — no
    SVG serialisation, no XML parse, no ``read_multilayer_svg``. The
    optimized result is still serialised to the labelled SVG pivot so
    downstream consumers (preview, G-code generation on the SVG path)
    are unaffected. IR points are millimetres by contract, so the
    default tolerance scale is 1.0 unless ``units_per_mm`` overrides it.
    """
    with traced_span(
        "pipeline.optimize_geometry_ir",
        layer_count=len(getattr(geometry, "layers", []) or []),
    ):
        ir_layers = list(getattr(geometry, "layers", []) or [])
        settings = {item.layer_id: item for item in (layers or [])}
        scale = units_per_mm or 1.0

        # Same single-path early-exit as the SVG route: one layer with at
        # most one polyline is already monotonic, skip the vpype pipeline.
        if len(ir_layers) == 1 and len(getattr(ir_layers[0], "polylines", []) or []) <= 1:
            return ToolpathResult(
                svg=_geometry_ir_to_svg(geometry),
                metrics=ToolpathMetrics(
                    pen_up_before_mm=0.0, pen_up_after_mm=0.0, reduction_pct=0.0
                ),
            )

        before_total = 0.0
        after_total = 0.0
        out_groups: list[str] = []
        for layer in ir_layers:
            label = getattr(layer, "label", "") or getattr(layer, "layer_id", "")
            color = getattr(layer, "color", "#000000") or "#000000"
            setting = settings.get(label)
            optimize = setting.optimize if setting else True
            simplify = setting.simplify_tolerance_mm if setting else 0.05
            seam_rotation = setting.seam_rotation if setting else True

            doc = _doc_from_ir_layer(layer)
            before_total += doc.pen_up_length()
            if optimize:
                pipeline_str = _pipeline(simplify * scale, merge_tolerance_mm * scale)
                doc = vpype_cli.execute(pipeline_str, document=doc)
                _refine_doc_order(
                    doc,
                    seam_rotation=seam_rotation,
                    closed_tolerance=merge_tolerance_mm * scale,
                )
            after_total += doc.pen_up_length()
            out_groups.append(_optimized_group(label, color, doc))

        reduction = (
            (before_total - after_total) / before_total * 100.0 if before_total > 0 else 0.0
        )
        viewbox = getattr(geometry, "viewbox", None)
        size = vb = ""
        if viewbox is not None:
            x, y, w, h = viewbox
            size = f' width="{w}" height="{h}"'
            vb = f' viewBox="{x} {y} {w} {h}"'
        out_svg = (
            f'<svg xmlns="{_SVG_NS}" xmlns:inkscape="{_INKSCAPE_NS}"{size}{vb}>'
            + "".join(out_groups)
            + "</svg>"
        )
        return ToolpathResult(
            svg=out_svg,
            metrics=ToolpathMetrics(
                pen_up_before_mm=before_total,
                pen_up_after_mm=after_total,
                reduction_pct=reduction,
            ),
        )


def _geometry_ir_to_svg(geometry: Any) -> str:
    """Render a :class:`GeometryIR` back to a labelled SVG pivot.

    Inverse of :func:`pen_plotter.domain.ir.adapter.geometry_ir_from_svg`
    — produces the same shape the SVG path of :func:`_optimize_svg`
    consumes (one ``<g inkscape:label>`` per layer, polylines as
    ``<polyline points="...">`` children).
    """
    viewbox = getattr(geometry, "viewbox", None)
    vb_attr = ""
    size = ""
    if viewbox is not None:
        x, y, w, h = viewbox
        vb_attr = f' viewBox="{x} {y} {w} {h}"'
        size = f' width="{w}" height="{h}"'
    parts = [f'<svg xmlns="{_SVG_NS}" xmlns:inkscape="{_INKSCAPE_NS}"{size}{vb_attr}>']
    for layer in getattr(geometry, "layers", []) or []:
        label = getattr(layer, "label", "") or getattr(layer, "layer_id", "")
        color = getattr(layer, "color", "#000000") or "#000000"
        parts.append(f'<g inkscape:label="{label}" stroke="{color}" fill="none">')
        for poly in getattr(layer, "polylines", []) or []:
            pts = getattr(poly, "points", []) or []
            if len(pts) < 2:
                continue
            points = " ".join(f"{px:.6f},{py:.6f}" for px, py in pts)
            tag = "polygon" if getattr(poly, "closed", False) else "polyline"
            parts.append(f'<{tag} points="{points}"/>')
        parts.append("</g>")
    parts.append("</svg>")
    return "".join(parts)


def _path_count(svg: str) -> int:
    """Count drawable primitives in ``svg``.

    Every shape svgelements turns into plottable geometry must be listed
    here: the count gates the single-path early-exit in
    :func:`_optimize_svg`, and a missing tag silently skips optimization.
    Regression cover: ``circle`` was absent, so a mono-layer stippling /
    halftone / circle_pack job (dots are ``<circle>`` elements) shipped
    in raw generation order — the exact pen-up regression the optimizer
    exists to prevent (audit_optimisation_trace_2026-07-19, découverte
    pendant F2).
    """
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return 0
    count = 0
    for elem in root.iter():
        tag = _local(elem.tag)
        if tag in {"path", "polyline", "polygon", "line", "circle", "ellipse", "rect"}:
            count += 1
    return count


def _optimize_svg(
    svg: str,
    *,
    layers: list[LayerOptimization] | None,
    merge_tolerance_mm: float,
    units_per_mm: float | None = None,
) -> ToolpathResult:
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as exc:
        raise ValueError(f"Could not parse SVG: {exc}") from exc

    # Determine the scale factor: explicit param > auto-detect > 1.0
    scale = units_per_mm or _detect_units_per_mm(root) or 1.0

    settings = {item.layer_id: item for item in (layers or [])}
    viewbox = root.get("viewBox")
    groups = [
        child
        for child in root
        if _local(child.tag) == "g" and child.get(_INKSCAPE_LABEL) is not None
    ]

    targets: list[tuple[str, str, str]]
    if groups:
        targets = [
            (
                group.get(_INKSCAPE_LABEL) or f"layer-{i + 1}",
                _group_color(group),
                _group_to_svg(viewbox, group),
            )
            for i, group in enumerate(groups)
        ]
    else:
        targets = [("layer-1", _group_color(root), svg)]

    # Quick win F.3 (docs/perf-report.md §B2): a single-layer SVG with
    # at most one path is already monotonic — vpype's
    # linemerge/linesimplify/linesort can't reduce pen-up travel. Skip
    # the ~100 ms vpype pipeline entirely and return the input
    # unchanged. The "one path" cap keeps the early-exit safe: any
    # second polyline introduces a potential pen-up that the optimizer
    # might still want to reorder.
    if len(targets) == 1 and _path_count(targets[0][2]) <= 1:
        return ToolpathResult(
            svg=svg,
            metrics=ToolpathMetrics(
                pen_up_before_mm=0.0,
                pen_up_after_mm=0.0,
                reduction_pct=0.0,
            ),
        )

    before_total = 0.0
    after_total = 0.0
    out_groups: list[str] = []

    for label, color, group_svg in targets:
        setting = settings.get(label)
        optimize = setting.optimize if setting else True
        simplify = setting.simplify_tolerance_mm if setting else 0.05
        seam_rotation = setting.seam_rotation if setting else True

        doc = _doc_from_svg(group_svg)
        before_total += doc.pen_up_length()
        if optimize:
            # Scale tolerances by the units_per_mm factor
            scaled_merge_tolerance = merge_tolerance_mm * scale
            scaled_simplify = simplify * scale
            pipeline_str = _pipeline(scaled_simplify, scaled_merge_tolerance)
            doc = vpype_cli.execute(pipeline_str, document=doc)
            _refine_doc_order(
                doc, seam_rotation=seam_rotation, closed_tolerance=scaled_merge_tolerance
            )
        after_total += doc.pen_up_length()
        out_groups.append(_optimized_group(label, color, doc))

    reduction = (before_total - after_total) / before_total * 100.0 if before_total > 0 else 0.0
    width = root.get("width")
    height = root.get("height")
    size = f' width="{width}" height="{height}"' if width and height else ""
    vb = f' viewBox="{viewbox}"' if viewbox else ""
    out_svg = (
        f'<svg xmlns="{_SVG_NS}" xmlns:inkscape="{_INKSCAPE_NS}"{size}{vb}>'
        + "".join(out_groups)
        + "</svg>"
    )
    return ToolpathResult(
        svg=out_svg,
        metrics=ToolpathMetrics(
            pen_up_before_mm=before_total,
            pen_up_after_mm=after_total,
            reduction_pct=reduction,
        ),
    )

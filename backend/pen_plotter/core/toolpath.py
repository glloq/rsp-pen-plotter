"""Toolpath optimization via vpype.

Runs vpype's ``linemerge -> linesimplify -> linesort`` pipeline on each layer
to reduce pen-up travel, preserving layer labels and colors. Optimization
operates per labeled group so that the layer identity established during
extraction is retained. Geometry is processed in the SVG's user-unit
coordinate system (its ``viewBox``), so tolerances are passed as bare numbers.
"""

from __future__ import annotations

import io
from typing import Any
from xml.etree import ElementTree as ET
from xml.sax.saxutils import quoteattr

import vpype as vp
import vpype_cli
from pydantic import BaseModel

from pen_plotter.core.layers import (
    _INKSCAPE_LABEL,
    _INKSCAPE_NS,
    _SVG_NS,
    _group_color,
    _group_to_svg,
    _local,
    strip_root_size,
)

_QUANTIZATION = 0.5


class LayerOptimization(BaseModel):
    """Per-layer optimization settings supplied by the client."""

    layer_id: str
    optimize: bool = True
    simplify_tolerance_mm: float = 0.05


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


def optimize_svg(
    svg: str,
    *,
    layers: list[LayerOptimization] | None = None,
    merge_tolerance_mm: float = 0.1,
) -> ToolpathResult:
    """Optimize toolpaths in a pivot SVG, reducing pen-up travel.

    Args:
        svg: The normalized SVG markup.
        layers: Per-layer settings; layers absent from the list are optimized
            with default settings. Layers with ``optimize=False`` are passed
            through unchanged.
        merge_tolerance_mm: Endpoint join tolerance for ``linemerge``.

    Returns:
        A :class:`ToolpathResult` with the optimized SVG and travel metrics.

    Raises:
        ValueError: If the SVG cannot be parsed.
    """
    from pen_plotter.observability import traced_span

    with traced_span(
        "pipeline.optimize_svg",
        svg_bytes=len(svg),
        layer_count=len(layers or []),
    ):
        return _optimize_svg(svg, layers=layers, merge_tolerance_mm=merge_tolerance_mm)


def optimize_geometry_ir(
    geometry: Any,
    *,
    layers: list[LayerOptimization] | None = None,
    merge_tolerance_mm: float = 0.1,
) -> ToolpathResult:
    """Optimize toolpaths starting from a :class:`GeometryIR` artifact.

    First v0.2 consumer of the typed IR. The current implementation
    rebuilds an SVG pivot from the IR and delegates to
    :func:`optimize_svg`; future iterations can feed vpype's
    ``Document`` directly from the polylines and skip the SVG
    round-trip entirely (the SIMD geometry work tracked under
    audit #1 §7).

    Surface is stable today: callers can opt into the IR pipeline
    by passing the cached ``GeometryIR`` instead of an SVG string,
    even though the inner loop hasn't been rewritten yet.
    """
    from pen_plotter.observability import traced_span

    with traced_span(
        "pipeline.optimize_geometry_ir",
        layer_count=len(getattr(geometry, "layers", []) or []),
    ):
        svg = _geometry_ir_to_svg(geometry)
        return _optimize_svg(svg, layers=layers, merge_tolerance_mm=merge_tolerance_mm)


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
    """Count drawable primitives (path/polyline/polygon/line) in ``svg``."""
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return 0
    count = 0
    for elem in root.iter():
        tag = _local(elem.tag)
        if tag in {"path", "polyline", "polygon", "line"}:
            count += 1
    return count


def _optimize_svg(
    svg: str,
    *,
    layers: list[LayerOptimization] | None,
    merge_tolerance_mm: float,
) -> ToolpathResult:
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as exc:
        raise ValueError(f"Could not parse SVG: {exc}") from exc

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

        doc = _doc_from_svg(group_svg)
        before_total += doc.pen_up_length()
        if optimize:
            doc = vpype_cli.execute(_pipeline(simplify, merge_tolerance_mm), document=doc)
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

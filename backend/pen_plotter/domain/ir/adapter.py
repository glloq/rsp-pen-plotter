"""Bridges between the v0.1 SVG-string pipeline and the v0.2 IR types.

These adapters let callers consume the typed IR (:mod:`pen_plotter.domain.ir`)
without rewriting the existing converters. They are imported on demand
and gated by ``OMNIPLOT_IR_ENABLED=1`` so the default v0.1 code path
stays unchanged.

Today the adapter flattens an SVG pivot into :class:`GeometryIR` by
walking the same layer groups :func:`pen_plotter.core.layers.extract_layers`
already understands. Bezier / arc primitives are sampled to polylines
using a coarse default tolerance — sufficient for hashing and for the
optimizer benchmarks; finer control will come with a dedicated
flattening pass in phase B.
"""

from __future__ import annotations

import hashlib
import os
import re
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import Element

from pen_plotter.domain.ir.geometry import GeometryIR, LayerGeometry, Polyline

_INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"
_SVG_NS = "http://www.w3.org/2000/svg"
_INKSCAPE_LABEL = f"{{{_INKSCAPE_NS}}}label"

# SVG number grammar: optional sign, then EITHER ``digits[.digits]`` OR
# ``.digits`` — tools like PyMuPDF emit coordinates with no leading zero
# (e.g. ``.61035158``), so a regex that requires a digit before the
# decimal point would silently misparse them. Mirrors the pattern used
# in :mod:`pen_plotter.core.pdf_postprocess`.
_NUMBER_PATTERN = r"-?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?"
_NUMBER_RE = re.compile(_NUMBER_PATTERN)


def is_ir_enabled() -> bool:
    """Return ``True`` when ``OMNIPLOT_IR_ENABLED`` is set to a truthy value."""
    raw = os.environ.get("OMNIPLOT_IR_ENABLED", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def content_sha256(data: bytes) -> str:
    """Return the SHA-256 of ``data`` as a hex string."""
    return hashlib.sha256(data).hexdigest()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_viewbox(value: str | None) -> tuple[float, float, float, float] | None:
    if not value:
        return None
    parts = _NUMBER_RE.findall(value)
    if len(parts) != 4:
        return None
    x, y, w, h = (float(p) for p in parts)
    return (x, y, w, h)


def _color_of(element: Element) -> str:
    stroke = element.get("stroke")
    if stroke and stroke != "none":
        return stroke
    fill = element.get("fill")
    if fill and fill != "none":
        return fill
    return "#000000"


def _polylines_from_path(d: str) -> list[Polyline]:
    """Coarse path-``d`` flattener.

    Handles ``M``/``L``/``Z`` and uses straight-line approximations for
    Bezier control points (good enough for hashing and travel metrics;
    a proper flattener lands with phase B).
    """
    tokens = re.findall(rf"[MmLlHhVvCcSsQqTtAaZz]|{_NUMBER_PATTERN}", d)
    polylines: list[Polyline] = []
    points: list[tuple[float, float]] = []
    x = y = 0.0
    start_x = start_y = 0.0
    cmd: str | None = None
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.isalpha():
            cmd = tok
            i += 1
            if cmd in {"Z", "z"}:
                if points:
                    points.append((start_x, start_y))
                    if len(points) >= 2:
                        polylines.append(Polyline(points=points, closed=True))
                    points = []
                # Per the SVG spec the current point returns to the
                # subpath's initial point after a closepath — relative
                # commands following a ``z`` are offset from there.
                x, y = start_x, start_y
            continue
        if cmd is None:
            i += 1
            continue
        absolute = cmd.isupper()
        op = cmd.upper()
        try:
            if op != "M" and not points:
                # Drawing command with no open subpath (e.g. an ``L``
                # straight after a ``Z``): the new subpath starts at the
                # current point, so seed it as the first vertex.
                points.append((x, y))
            if op in {"M", "L"}:
                nx, ny = float(tokens[i]), float(tokens[i + 1])
                i += 2
                x, y = (nx, ny) if absolute else (x + nx, y + ny)
                if op == "M":
                    if points and len(points) >= 2:
                        polylines.append(Polyline(points=points))
                    points = [(x, y)]
                    start_x, start_y = x, y
                    cmd = "L" if absolute else "l"
                else:
                    points.append((x, y))
            elif op == "H":
                nx = float(tokens[i])
                i += 1
                x = nx if absolute else x + nx
                points.append((x, y))
            elif op == "V":
                ny = float(tokens[i])
                i += 1
                y = ny if absolute else y + ny
                points.append((x, y))
            elif op == "C":
                x1, y1, x2, y2, nx, ny = (float(tokens[i + k]) for k in range(6))
                i += 6
                if not absolute:
                    nx, ny = x + nx, y + ny
                x, y = nx, ny
                points.append((x, y))
            elif op == "Q":
                x1, y1, nx, ny = (float(tokens[i + k]) for k in range(4))
                i += 4
                if not absolute:
                    nx, ny = x + nx, y + ny
                x, y = nx, ny
                points.append((x, y))
            else:
                # Unknown / unsupported operator — bail this contour.
                i += 1
        except (IndexError, ValueError):
            break

    if points and len(points) >= 2:
        polylines.append(Polyline(points=points))
    return polylines


def _layer_polylines(group: Element) -> list[Polyline]:
    out: list[Polyline] = []
    for elem in group.iter():
        tag = _local(elem.tag)
        if tag == "path":
            d = elem.get("d")
            if d:
                out.extend(_polylines_from_path(d))
        elif tag == "polyline" or tag == "polygon":
            raw = elem.get("points") or ""
            nums = [float(n) for n in _NUMBER_RE.findall(raw)]
            pts = list(zip(nums[0::2], nums[1::2], strict=False))
            if len(pts) >= 2:
                out.append(Polyline(points=pts, closed=(tag == "polygon")))
        elif tag == "line":
            try:
                x1 = float(elem.get("x1", "0"))
                y1 = float(elem.get("y1", "0"))
                x2 = float(elem.get("x2", "0"))
                y2 = float(elem.get("y2", "0"))
                out.append(Polyline(points=[(x1, y1), (x2, y2)]))
            except ValueError:
                continue
    return out


def geometry_ir_from_svg(svg: str, *, source_hash: str) -> GeometryIR:
    """Build a :class:`GeometryIR` from a pivot SVG.

    ``source_hash`` should be the :func:`content_sha256` of the
    originating bytes (image / SVG / PDF page) so the IR remains
    content-addressed.
    """
    root = ET.fromstring(svg)
    viewbox = _parse_viewbox(root.get("viewBox"))

    layers: list[LayerGeometry] = []
    groups = [
        child
        for child in root
        if _local(child.tag) == "g" and child.get(_INKSCAPE_LABEL) is not None
    ]
    if not groups:
        polys = _layer_polylines(root)
        layers.append(
            LayerGeometry(
                layer_id="layer-1",
                color=_color_of(root),
                label="layer-1",
                polylines=polys,
            )
        )
    else:
        for order, group in enumerate(groups):
            label = group.get(_INKSCAPE_LABEL) or f"layer-{order + 1}"
            layers.append(
                LayerGeometry(
                    layer_id=f"layer-{order + 1}",
                    color=_color_of(group),
                    label=label,
                    polylines=_layer_polylines(group),
                )
            )

    return GeometryIR(source_hash=source_hash, viewbox=viewbox, layers=layers)

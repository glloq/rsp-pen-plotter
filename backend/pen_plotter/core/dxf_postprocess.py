"""Post-processing for ezdxf-emitted SVG.

The ezdxf SVG backend renders the model space onto a canvas with:
- a background ``<rect>`` filled with the editor background colour (which
  would otherwise plot as a giant frame, since vpype renders it via its
  filled outline);
- all drawables loose at the SVG root, so :func:`extract_layers` treats the
  whole document as a single anonymous ``layer-1`` instead of separating
  entities by colour/layer.

This module strips the background rectangle and wraps the remaining vector
content into a labeled group named for its DXF colour class (``color-…``)
so the user can assign each colour to a different pen, mirroring the
per-colour layering the bitmap converter produces.
"""

from __future__ import annotations

import re
from xml.etree import ElementTree as ET

from pen_plotter.core.svg_ns import INKSCAPE_NS as _INKSCAPE_NS
from pen_plotter.core.svg_ns import SVG_NS as _SVG_NS
from pen_plotter.core.svg_ns import svg_tostring

_INKSCAPE_LABEL = f"{{{_INKSCAPE_NS}}}label"


def _local(tag: str) -> str:
    """Return an element's local name without its namespace."""
    return tag.rsplit("}", 1)[-1]


def _class_colors(style_text: str) -> dict[str, str]:
    """Build a ``class → stroke colour`` map from ezdxf's inline stylesheet.

    ezdxf emits styles like ``.C1 {stroke: #ff0000; …}``. When a class is
    redefined later (e.g. ``.C2 {stroke: none; fill: #ffffff;}``), the
    redefinition wins for CSS but for our purposes we want the stroke
    colour because that's what is plotted; if it is ``none`` we fall back
    to the fill colour.
    """
    strokes: dict[str, str] = {}
    fills: dict[str, str] = {}
    for cls, body in re.findall(r"\.([A-Za-z0-9_-]+)\s*\{([^}]*)\}", style_text):
        stroke_match = re.search(r"stroke:\s*([^;]+);", body)
        if stroke_match:
            value = stroke_match.group(1).strip()
            if value != "none":
                strokes[cls] = value
        fill_match = re.search(r"fill:\s*([^;]+);", body)
        if fill_match:
            value = fill_match.group(1).strip()
            if value != "none":
                fills[cls] = value
    out: dict[str, str] = {}
    for cls in set(strokes) | set(fills):
        out[cls] = strokes.get(cls) or fills.get(cls, "#000000")
    return out


def _is_background_rect(rect: ET.Element) -> bool:
    """Detect the editor-background rectangle emitted by ezdxf.

    It is filled with no stroke and covers the whole viewBox. We're
    intentionally narrow here so a user's own filled ``<rect>`` is not
    misclassified.
    """
    if rect.get("stroke") and rect.get("stroke") != "none":
        return False
    fill = rect.get("fill")
    if not fill or fill == "none":
        return False
    try:
        x = float(rect.get("x", "0"))
        y = float(rect.get("y", "0"))
        _ = float(rect.get("width", "0"))
        _ = float(rect.get("height", "0"))
    except ValueError:
        return False
    # ezdxf places the background at the origin of the viewBox.
    return x == 0.0 and y == 0.0


_MM_RE = re.compile(r"^([0-9.+\-eE]+)\s*mm$")


def _mm_value(raw: str | None) -> float | None:
    """Parse an SVG length attribute that ends in ``mm``."""
    if not raw:
        return None
    match = _MM_RE.match(raw.strip())
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _mm_scale(root: ET.Element) -> tuple[float, float] | None:
    """Compute the ``(sx, sy)`` to rebase the SVG into mm user units.

    ezdxf renders into an internal ~1 000 000-unit canvas regardless of the
    drawing's physical size. The placement step in :mod:`gcode` scales the
    final output back to the workspace, so the produced G-code is
    geometrically correct, *but* vpype's ``linesimplify --tolerance 0.05``
    (which we treat as 0.05 mm) is interpreted in those user units —
    becoming 0.05 / 20 000 mm of tolerance on a 50 mm drawing, i.e. no
    simplification at all. The result is an exploded polyline with
    thousands of nearly-collinear points and a G-code file 1000× larger
    than necessary.

    Returns ``(scale_x, scale_y)`` to apply to children so that 1 user
    unit equals 1 mm, or ``None`` if the SVG already uses mm-aligned
    units (no rebasing needed).
    """
    width_mm = _mm_value(root.get("width"))
    height_mm = _mm_value(root.get("height"))
    viewbox = (root.get("viewBox") or "").split()
    if width_mm is None or height_mm is None or len(viewbox) != 4:
        return None
    try:
        _vx, _vy, vw, vh = (float(v) for v in viewbox)
    except ValueError:
        return None
    if vw <= 0 or vh <= 0:
        return None
    scale_x = width_mm / vw
    scale_y = height_mm / vh
    if abs(scale_x - 1.0) < 1e-6 and abs(scale_y - 1.0) < 1e-6:
        return None
    return scale_x, scale_y


def postprocess_dxf_svg(svg: str) -> str:
    """Strip the ezdxf background and group drawables into labeled layers.

    Args:
        svg: Raw ezdxf SVGBackend output.

    Returns:
        Normalized pivot SVG: no background rect, vector content grouped
        by colour class into ``<g inkscape:label="color-…">`` direct
        children of ``<svg>``.
    """
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return svg

    # If ezdxf used a million-unit canvas for what's really a small drawing,
    # capture the mm-per-unit scale before we re-bucket so we can preserve
    # geometry while moving the document into mm coordinates.
    mm_scale = _mm_scale(root)

    style_text = ""
    for elem in root.iter():
        if _local(elem.tag) == "style" and elem.text:
            style_text += elem.text
    class_map = _class_colors(style_text)

    # Drop the background rect.
    for child in list(root):
        if _local(child.tag) == "rect" and _is_background_rect(child):
            root.remove(child)

    # Gather every drawable element (and its parent group) under a single
    # outer <g> that ezdxf already emits, then re-bucket by class.
    drawables: list[ET.Element] = []
    for elem in list(root):
        local = _local(elem.tag)
        if local == "g":
            # Flatten one level: move children of the wrapping group up so
            # we can re-group by class.
            drawable_tags = {"path", "polyline", "polygon", "line", "circle", "rect", "ellipse"}
            for child in list(elem):
                if _local(child.tag) in drawable_tags:
                    drawables.append(child)
            root.remove(elem)
        elif local in {"path", "polyline", "polygon", "line", "circle", "rect", "ellipse"}:
            drawables.append(elem)
            root.remove(elem)

    if not drawables:
        return svg_tostring(root)

    # Bucket by `class` attribute (ezdxf assigns one CSS class per colour);
    # entries with no class fall into a default bucket.
    buckets: dict[str, list[ET.Element]] = {}
    for drawable in drawables:
        cls = (drawable.get("class") or "").strip()
        buckets.setdefault(cls, []).append(drawable)

    # Sort buckets for deterministic output: classes alphabetical, no-class last.
    keys = sorted(buckets.keys(), key=lambda k: (k == "", k))
    transform = None
    if mm_scale is not None:
        sx, sy = mm_scale
        transform = (
            f"scale({sx})" if abs(sx - sy) < 1e-9 else f"scale({sx} {sy})"
        )
    for cls in keys:
        color = class_map.get(cls, "#000000") if cls else "#000000"
        label = (
            f"color-{color.lstrip('#')}"
            if color.startswith("#")
            else f"class-{cls or 'default'}"
        )
        group = ET.Element(f"{{{_SVG_NS}}}g")
        group.set(_INKSCAPE_LABEL, label)
        group.set("stroke", color)
        group.set("fill", "none")
        if transform:
            group.set("transform", transform)
        for drawable in buckets[cls]:
            group.append(drawable)
        root.append(group)

    if mm_scale is not None:
        # Rebase the viewBox so subsequent stages (placement, vpype) see
        # the drawing in millimetres rather than in ezdxf's internal
        # million-unit canvas.
        width_mm = _mm_value(root.get("width"))
        height_mm = _mm_value(root.get("height"))
        if width_mm is not None and height_mm is not None:
            root.set("viewBox", f"0 0 {width_mm} {height_mm}")

    return svg_tostring(root)

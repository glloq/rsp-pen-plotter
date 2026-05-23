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

_SVG_NS = "http://www.w3.org/2000/svg"
_INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"
_INKSCAPE_LABEL = f"{{{_INKSCAPE_NS}}}label"

ET.register_namespace("", _SVG_NS)
ET.register_namespace("inkscape", _INKSCAPE_NS)


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
            for child in list(elem):
                if _local(child.tag) in {"path", "polyline", "polygon", "line", "circle", "rect", "ellipse"}:
                    drawables.append(child)
            root.remove(elem)
        elif local in {"path", "polyline", "polygon", "line", "circle", "rect", "ellipse"}:
            drawables.append(elem)
            root.remove(elem)

    if not drawables:
        return ET.tostring(root, encoding="unicode")

    # Bucket by `class` attribute (ezdxf assigns one CSS class per colour);
    # entries with no class fall into a default bucket.
    buckets: dict[str, list[ET.Element]] = {}
    for drawable in drawables:
        cls = (drawable.get("class") or "").strip()
        buckets.setdefault(cls, []).append(drawable)

    # Sort buckets for deterministic output: classes alphabetical, no-class last.
    keys = sorted(buckets.keys(), key=lambda k: (k == "", k))
    for cls in keys:
        color = class_map.get(cls, "#000000") if cls else "#000000"
        label = f"color-{color.lstrip('#')}" if color.startswith("#") else f"class-{cls or 'default'}"
        group = ET.Element(f"{{{_SVG_NS}}}g")
        group.set(_INKSCAPE_LABEL, label)
        group.set("stroke", color)
        group.set("fill", "none")
        for drawable in buckets[cls]:
            group.append(drawable)
        root.append(group)

    return ET.tostring(root, encoding="unicode")

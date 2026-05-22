"""Layer extraction from the pivot SVG.

Inspects the normalized SVG and produces one :class:`LayerInfo` per top-level
group. Groups carrying an ``inkscape:label`` (as emitted by the converters)
become individual layers; otherwise the whole document is treated as a single
layer.

Path length and bounding box are measured in the SVG's user-unit coordinate
system (its ``viewBox``). For text/Markdown that system is millimeters by
construction; for other inputs it is provisional until physical placement is
decided in a later phase.
"""

from __future__ import annotations

import io
from functools import lru_cache
from xml.etree import ElementTree as ET

from svgelements import SVG, Shape

from pen_plotter.models import BoundingBox, LayerInfo

_SVG_NS = "http://www.w3.org/2000/svg"
_INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"
_INKSCAPE_LABEL = f"{{{_INKSCAPE_NS}}}label"
_DRAWABLE = {"path", "polyline", "polygon", "line", "circle", "rect", "ellipse"}

ET.register_namespace("", _SVG_NS)
ET.register_namespace("inkscape", _INKSCAPE_NS)


def _local(tag: str) -> str:
    """Return an element's local name without its namespace."""
    return tag.rsplit("}", 1)[-1]


def strip_root_size(svg: str) -> str:
    """Remove ``width``/``height`` from the root ``<svg>`` element.

    This forces measurement and geometry libraries to work in the document's
    ``viewBox`` user units instead of scaling to physical pixels. Unlike a
    regex, it only ever touches the root element's attributes.

    Args:
        svg: The SVG markup.

    Returns:
        The SVG with root size attributes removed, or the input unchanged if it
        cannot be parsed.
    """
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return svg
    root.attrib.pop("width", None)
    root.attrib.pop("height", None)
    return ET.tostring(root, encoding="unicode")


def _count_drawables(element: ET.Element) -> int:
    """Count drawable descendants (and the element itself) of an element."""
    count = 1 if _local(element.tag) in _DRAWABLE else 0
    for child in element:
        count += _count_drawables(child)
    return count


def _group_color(group: ET.Element) -> str:
    """Resolve a representative color for a group from its fill or stroke."""
    for attr in ("fill", "stroke"):
        value = group.get(attr)
        if value and value != "none":
            return value
    for child in group.iter():
        for attr in ("fill", "stroke"):
            value = child.get(attr)
            if value and value != "none":
                return value
    return "#000000"


@lru_cache(maxsize=256)
def _measure(svg_markup: str) -> tuple[float, BoundingBox]:
    """Measure total path length and bounding box in user units.

    Physical ``width``/``height`` are stripped so svgelements reports lengths in
    the document's ``viewBox`` coordinate system rather than scaling to pixels.
    Results are memoized since the same fragment may be measured repeatedly.

    Args:
        svg_markup: A self-contained SVG document.

    Returns:
        A ``(length, bbox)`` pair; zeros if the SVG has no measurable geometry.
    """
    stripped = strip_root_size(svg_markup)
    total = 0.0
    x_min = y_min = float("inf")
    x_max = y_max = float("-inf")
    try:
        parsed = SVG.parse(io.StringIO(stripped))
    except Exception:
        return 0.0, BoundingBox(x_min=0.0, y_min=0.0, x_max=0.0, y_max=0.0)

    for element in parsed.elements():
        if not isinstance(element, Shape):
            continue
        try:
            total += float(element.length())
            box = element.bbox()
        except Exception:
            continue
        if box is None:
            continue
        x_min, y_min = min(x_min, box[0]), min(y_min, box[1])
        x_max, y_max = max(x_max, box[2]), max(y_max, box[3])

    if x_min == float("inf"):
        return total, BoundingBox(x_min=0.0, y_min=0.0, x_max=0.0, y_max=0.0)
    return total, BoundingBox(x_min=x_min, y_min=y_min, x_max=x_max, y_max=y_max)


def _group_to_svg(viewbox: str | None, group: ET.Element) -> str:
    """Wrap a single group as a standalone SVG for measurement."""
    inner = ET.tostring(group, encoding="unicode")
    attrs = f'xmlns="{_SVG_NS}" xmlns:inkscape="{_INKSCAPE_NS}"'
    vb = f' viewBox="{viewbox}"' if viewbox else ""
    return f"<svg {attrs}{vb}>{inner}</svg>"


def extract_layers(svg: str) -> list[LayerInfo]:
    """Extract layer descriptors from a pivot SVG document.

    Args:
        svg: The normalized SVG markup.

    Returns:
        One :class:`LayerInfo` per detected layer, ordered by document order.

    Raises:
        ValueError: If the SVG cannot be parsed.
    """
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as exc:
        raise ValueError(f"Could not parse SVG: {exc}") from exc

    viewbox = root.get("viewBox")
    groups = [
        child
        for child in root
        if _local(child.tag) == "g" and child.get(_INKSCAPE_LABEL) is not None
    ]

    if not groups:
        length, bbox = _measure(svg)
        return [
            LayerInfo(
                layer_id="layer-1",
                source_color=_group_color(root),
                target_pen_slot=None,
                draw_order=0,
                total_length_mm=length,
                path_count=_count_drawables(root),
                bbox=bbox,
            )
        ]

    layers: list[LayerInfo] = []
    for order, group in enumerate(groups):
        label = group.get(_INKSCAPE_LABEL) or f"layer-{order + 1}"
        length, bbox = _measure(_group_to_svg(viewbox, group))
        layers.append(
            LayerInfo(
                layer_id=label,
                source_color=_group_color(group),
                target_pen_slot=None,
                draw_order=order,
                total_length_mm=length,
                path_count=_count_drawables(group),
                bbox=bbox,
            )
        )
    return layers

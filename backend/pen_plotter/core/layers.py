"""Layer extraction from the pivot SVG.

Inspects the normalized SVG and produces one :class:`LayerInfo` per top-level
group. Groups carrying an ``inkscape:label`` (as emitted by the converters)
become individual layers; otherwise the whole document is treated as a single
layer. Geometric statistics (length, bounding box) are filled in by later
pipeline phases and default to zero here.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from pen_plotter.models import BoundingBox, LayerInfo

_SVG_NS = "http://www.w3.org/2000/svg"
_INKSCAPE_LABEL = "{http://www.inkscape.org/namespaces/inkscape}label"
_DRAWABLE = {"path", "polyline", "polygon", "line", "circle", "rect", "ellipse"}


def _local(tag: str) -> str:
    """Return an element's local name without its namespace."""
    return tag.rsplit("}", 1)[-1]


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


def _empty_bbox() -> BoundingBox:
    """Return a placeholder bounding box filled in by later phases."""
    return BoundingBox(x_min=0.0, y_min=0.0, x_max=0.0, y_max=0.0)


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

    groups = [
        child
        for child in root
        if _local(child.tag) == "g" and child.get(_INKSCAPE_LABEL) is not None
    ]

    if not groups:
        return [
            LayerInfo(
                layer_id="layer-1",
                source_color=_group_color(root),
                target_pen_slot=None,
                draw_order=0,
                total_length_mm=0.0,
                path_count=_count_drawables(root),
                bbox=_empty_bbox(),
            )
        ]

    layers: list[LayerInfo] = []
    for order, group in enumerate(groups):
        label = group.get(_INKSCAPE_LABEL) or f"layer-{order + 1}"
        layers.append(
            LayerInfo(
                layer_id=label,
                source_color=_group_color(group),
                target_pen_slot=None,
                draw_order=order,
                total_length_mm=0.0,
                path_count=_count_drawables(group),
                bbox=_empty_bbox(),
            )
        )
    return layers

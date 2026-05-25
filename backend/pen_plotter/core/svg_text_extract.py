"""Extract ``<text>``/``<tspan>`` content from an SVG for Hershey re-render.

SVG `<text>` elements are not plottable as-is — they rely on the renderer
to outline the glyph from a TrueType face. The pen-plotter pipeline
instead wants single-stroke Hershey polylines at the same baseline
positions, mirroring what the PDF re-render path does for PyMuPDF text.

This module pulls every visible text run out of an SVG tree, yields
:class:`~pen_plotter.typography.PlacedSpan` instances in document order,
and (separately) strips the consumed ``<text>`` nodes so the caller can
splice the Hershey replacement group back in without double-tracing.
"""

from __future__ import annotations

import re
from xml.etree import ElementTree as ET

from pen_plotter.typography import PlacedSpan

_SVG_NS = "http://www.w3.org/2000/svg"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_length(value: str | None, default: float = 0.0) -> float:
    """Parse an SVG length attribute, dropping the unit suffix if present."""
    if not value:
        return default
    match = re.match(r"^\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", value)
    if not match:
        return default
    return float(match.group(1))


def _style_prop(style: str | None, prop: str) -> str | None:
    """Read one ``key: value`` pair from a CSS-style ``style="..."`` string."""
    if not style:
        return None
    match = re.search(rf"(?:^|;)\s*{re.escape(prop)}\s*:\s*([^;]+)", style)
    return match.group(1).strip() if match else None


def _resolve_font_size(elem: ET.Element, inherited: float) -> float:
    """Pull font-size from attribute or inline style, falling back to inherited."""
    direct = elem.get("font-size")
    if direct:
        return _parse_length(direct, inherited)
    styled = _style_prop(elem.get("style"), "font-size")
    if styled:
        return _parse_length(styled, inherited)
    return inherited


def _resolve_bold(elem: ET.Element, inherited: bool) -> bool:
    """Resolve font-weight to a bold flag (heavy / >=600 counts as bold)."""
    raw = elem.get("font-weight") or _style_prop(elem.get("style"), "font-weight")
    if raw is None:
        return inherited
    raw = raw.strip().lower()
    if raw in {"bold", "bolder", "heavy", "black"}:
        return True
    if raw in {"normal", "lighter", "light"}:
        return False
    try:
        return int(raw) >= 600
    except ValueError:
        return inherited


def _resolve_italic(elem: ET.Element, inherited: bool) -> bool:
    """Resolve font-style to an italic flag."""
    raw = elem.get("font-style") or _style_prop(elem.get("style"), "font-style")
    if raw is None:
        return inherited
    raw = raw.strip().lower()
    return raw in {"italic", "oblique"}


def _text_content(elem: ET.Element) -> str:
    """Concatenate this element's text and its descendants' text in document order.

    ``<tspan>`` children with their own coordinates are handled by the
    walker (each becomes its own :class:`PlacedSpan`). This helper is for
    the leaf case where a ``<text>`` has only flat text (no nested tspans
    with positioning of their own).
    """
    parts: list[str] = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        if _local(child.tag) == "tspan":
            parts.append(_text_content(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def _walk_text(
    elem: ET.Element,
    *,
    cursor_x: float,
    cursor_y: float,
    inherited_size: float,
    inherited_bold: bool,
    inherited_italic: bool,
    spans: list[PlacedSpan],
) -> tuple[float, float]:
    """Recursively walk a `<text>` element, emitting one span per positioned run.

    Returns the updated cursor (so a following sibling tspan that omits
    its own x/y picks up where the previous one ended — approximated by
    the original anchor since we don't measure Hershey advance here).
    """
    x = _parse_length(elem.get("x"), cursor_x)
    y = _parse_length(elem.get("y"), cursor_y)
    size = _resolve_font_size(elem, inherited_size)
    bold = _resolve_bold(elem, inherited_bold)
    italic = _resolve_italic(elem, inherited_italic)

    if elem.text and elem.text.strip():
        spans.append(
            PlacedSpan(
                text=elem.text,
                x=x,
                baseline_y=y,
                size=size,
                bold=bold,
                italic=italic,
            )
        )

    for child in elem:
        if _local(child.tag) == "tspan":
            x, y = _walk_text(
                child,
                cursor_x=x,
                cursor_y=y,
                inherited_size=size,
                inherited_bold=bold,
                inherited_italic=italic,
                spans=spans,
            )
        if child.tail and child.tail.strip():
            spans.append(
                PlacedSpan(
                    text=child.tail,
                    x=x,
                    baseline_y=y,
                    size=size,
                    bold=bold,
                    italic=italic,
                )
            )

    return x, y


def extract_svg_text_spans(root: ET.Element) -> list[PlacedSpan]:
    """Return every visible text run in ``root`` as a positioned span.

    Nested ``<tspan>`` elements inherit the parent's font-size, weight,
    and style unless they override them. ``<textPath>`` is not supported
    (it would require evaluating the referenced path's parametric
    position) — text along a path is left in place and surfaces in the
    caller's warning list.
    """
    spans: list[PlacedSpan] = []
    for elem in root.iter():
        if _local(elem.tag) != "text":
            continue
        _walk_text(
            elem,
            cursor_x=0.0,
            cursor_y=0.0,
            inherited_size=16.0,
            inherited_bold=False,
            inherited_italic=False,
            spans=spans,
        )
    return spans


def strip_text_elements(root: ET.Element) -> int:
    """Remove every ``<text>`` element from the tree. Returns the count removed."""
    removed = 0
    parent_map = {child: parent for parent in root.iter() for child in parent}
    for elem in list(root.iter()):
        if _local(elem.tag) != "text":
            continue
        parent = parent_map.get(elem)
        if parent is not None:
            parent.remove(elem)
            removed += 1
    return removed


__all__ = ["extract_svg_text_spans", "strip_text_elements"]

"""SVG sanitization.

Removes active content (scripts, event handlers, foreign HTML, javascript URLs)
from SVG before it is returned to the browser, since some converters (notably
the SVG passthrough) emit user-supplied markup verbatim.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

_DANGEROUS_TAGS = {"script", "foreignobject", "iframe", "object", "embed", "use", "animate", "set"}
_URL_ATTRS = {"href", "{http://www.w3.org/1999/xlink}href", "xlink:href"}

ET.register_namespace("", "http://www.w3.org/2000/svg")
ET.register_namespace("inkscape", "http://www.inkscape.org/namespaces/inkscape")


def _local(tag: str) -> str:
    """Return an element's lowercased local name without its namespace."""
    return tag.rsplit("}", 1)[-1].lower()


def _clean(element: ET.Element) -> None:
    """Recursively strip dangerous children and attributes from an element."""
    for attr in list(element.attrib):
        value = element.attrib[attr]
        local = attr.rsplit("}", 1)[-1].lower()
        if local.startswith("on"):
            del element.attrib[attr]
        elif attr in _URL_ATTRS and value.strip().lower().startswith(("javascript:", "data:text")):
            del element.attrib[attr]

    for child in list(element):
        if _local(child.tag) in _DANGEROUS_TAGS:
            element.remove(child)
        else:
            _clean(child)


def sanitize_svg(svg: str) -> str:
    """Return a copy of the SVG with active/script content removed.

    Args:
        svg: The SVG markup to sanitize.

    Returns:
        Sanitized SVG markup. If the input cannot be parsed it is returned
        unchanged (callers parse it elsewhere and will surface the error).
    """
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return svg
    if _local(root.tag) in _DANGEROUS_TAGS:
        return '<svg xmlns="http://www.w3.org/2000/svg"></svg>'
    _clean(root)
    return ET.tostring(root, encoding="unicode")

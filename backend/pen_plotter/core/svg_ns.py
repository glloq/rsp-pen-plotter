"""SVG namespace helpers.

``xml.etree.ElementTree`` uses a process-global ``_namespace_map`` to decide
prefixes when serializing. Third-party libraries (weasyprint pulls in
xml.sax / lxml shims that touch the same map) can reset our registration of
the SVG namespace as the default, so ``tostring`` then falls back to an
auto-prefix like ``ns0:`` — producing markup the browser will parse but
DOMPurify rejects, leaving the SVG preview tab blank.

This module centralises a re-registration step that runs immediately before
each ``tostring`` call, so the output is always ``<svg xmlns="...">`` —
regardless of what else happened to the global map first.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"
INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"
XLINK_NS = "http://www.w3.org/1999/xlink"


def _ensure_namespaces() -> None:
    """(Re)register the default prefixes our SVG output depends on."""
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("inkscape", INKSCAPE_NS)
    ET.register_namespace("xlink", XLINK_NS)


def svg_tostring(element: ET.Element) -> str:
    """Serialize an SVG element tree with the default namespaces restored."""
    _ensure_namespaces()
    return ET.tostring(element, encoding="unicode")

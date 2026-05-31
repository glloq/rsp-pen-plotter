"""Plain text converter.

Renders UTF-8 text as single-stroke Hershey paths.
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from pen_plotter.converters.base import ConversionResult, Converter
from pen_plotter.typography import HersheyRenderer, TypographyOptions

# Match the four numeric components of an SVG viewBox attribute so we can
# read back the page dimensions the renderer actually produced (the
# laid-out height may exceed ``page_height_mm`` when text overflows).
_VIEWBOX_RE = re.compile(
    r'viewBox\s*=\s*"\s*([\d.eE+-]+)\s+([\d.eE+-]+)\s+([\d.eE+-]+)\s+([\d.eE+-]+)\s*"'
)


class TextConverter(Converter):
    """Renders plain text to a single-stroke SVG document."""

    supported_mimes: ClassVar[frozenset[str]] = frozenset({"text/plain"})

    def convert(self, data: bytes, *, options: dict[str, Any] | None = None) -> ConversionResult:
        """Render text bytes to SVG.

        Args:
            data: Raw UTF-8 text bytes.
            options: Optional parameters validated against
                :class:`~pen_plotter.typography.TypographyOptions`.

        Returns:
            A :class:`ConversionResult` containing the rendered SVG. The
            metadata reports the rendered page dimensions so the frontend
            sizes the on-sheet placement to the full page (matching the
            SVG's viewBox) instead of the content bounding box — otherwise
            the content's margin offset within the viewBox shows up as an
            off-centre placement with text clipped on the right / bottom.

        Raises:
            ValueError: If typography options are invalid.
        """
        text = data.decode("utf-8", errors="replace")
        renderer = HersheyRenderer(TypographyOptions.model_validate(options or {}))
        svg = renderer.render_text(text)
        metadata: dict[str, Any] = {}
        match = _VIEWBOX_RE.search(svg)
        if match:
            metadata["page_width_mm"] = float(match.group(3))
            metadata["page_height_mm"] = float(match.group(4))
        return ConversionResult(svg=svg, source_mime="image/svg+xml", metadata=metadata)

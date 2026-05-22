"""Plain text converter.

Renders UTF-8 text as single-stroke Hershey paths.
"""

from __future__ import annotations

from typing import Any, ClassVar

from pen_plotter.converters.base import ConversionResult, Converter
from pen_plotter.typography import HersheyRenderer, TypographyOptions


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
            A :class:`ConversionResult` containing the rendered SVG.

        Raises:
            ValueError: If typography options are invalid.
        """
        text = data.decode("utf-8", errors="replace")
        renderer = HersheyRenderer(TypographyOptions.model_validate(options or {}))
        return ConversionResult(svg=renderer.render_text(text), source_mime="image/svg+xml")

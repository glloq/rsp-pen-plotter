"""SVG passthrough converter.

SVG is already the pivot format, so this converter decodes the input and
returns it unchanged. It is the only converter implemented in Phase 1.
"""

from __future__ import annotations

from typing import Any, ClassVar

from pen_plotter.converters.base import ConversionResult, Converter


class SvgConverter(Converter):
    """Passes SVG input through to the pivot format unchanged."""

    supported_mimes: ClassVar[frozenset[str]] = frozenset({"image/svg+xml"})

    def convert(self, data: bytes, *, options: dict[str, Any] | None = None) -> ConversionResult:
        """Decode SVG bytes as UTF-8 and return them as the pivot result.

        Args:
            data: The raw SVG file bytes.
            options: Unused; accepted for interface compatibility.

        Returns:
            A :class:`ConversionResult` containing the decoded SVG markup.
        """
        svg = data.decode("utf-8")
        return ConversionResult(svg=svg, source_mime="image/svg+xml")

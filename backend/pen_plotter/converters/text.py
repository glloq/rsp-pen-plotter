"""Plain text converter.

Renders text as single-stroke Hershey paths. Accepts UTF-8 (with or without
BOM), UTF-16, or Windows-1252 / Latin-1 byte streams — the latter is the
common case for ``.txt`` files saved by Notepad on French Windows systems,
where naive UTF-8 decoding would otherwise turn every accented character
into a replacement glyph.
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


def _decode_text(data: bytes) -> str:
    """Best-effort decode of an uploaded plain-text file.

    Tries UTF-8 (and UTF-16 when a BOM is present) strictly first; falls
    back to Windows-1252, which is a superset of Latin-1 and decodes any
    byte sequence without raising. This avoids the U+FFFD replacement
    glyphs that ``utf-8 / errors='replace'`` produces for non-UTF-8 input
    — those glyphs surface downstream as ``?`` in the rendered SVG.
    """
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            pass
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


class TextConverter(Converter):
    """Renders plain text to a single-stroke SVG document."""

    supported_mimes: ClassVar[frozenset[str]] = frozenset({"text/plain"})

    def convert(self, data: bytes, *, options: dict[str, Any] | None = None) -> ConversionResult:
        """Render text bytes to SVG.

        Args:
            data: Raw text bytes. UTF-8 is preferred; UTF-16 (with BOM)
                and Windows-1252 / Latin-1 are accepted as fallbacks.
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
        text = _decode_text(data)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        renderer = HersheyRenderer(TypographyOptions.model_validate(options or {}))
        svg = renderer.render_text(text)
        metadata: dict[str, Any] = {}
        match = _VIEWBOX_RE.search(svg)
        if match:
            metadata["page_width_mm"] = float(match.group(3))
            metadata["page_height_mm"] = float(match.group(4))
        return ConversionResult(svg=svg, source_mime="image/svg+xml", metadata=metadata)

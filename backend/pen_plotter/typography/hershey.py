"""Hershey single-stroke text layout to SVG.

Renders text as open polylines (no fills), laying out paragraphs with word
wrap, alignment, and configurable page geometry. Output coordinates are in
millimeters so they map directly onto a machine's workspace.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal
from xml.sax.saxutils import quoteattr

from HersheyFonts import HersheyFonts
from pydantic import BaseModel, Field

Alignment = Literal["left", "center", "right"]


@lru_cache(maxsize=1)
def available_fonts() -> tuple[str, ...]:
    """Return the names of the bundled Hershey fonts.

    Returns:
        A sorted tuple of font names usable as ``TypographyOptions.font``.
    """
    return tuple(sorted(HersheyFonts().default_font_names))


class TypographyOptions(BaseModel):
    """Layout parameters for rendering text with a Hershey font."""

    font: str = "futural"
    font_size_mm: float = Field(default=4.0, gt=0.0, le=200.0)
    page_width_mm: float = Field(default=210.0, gt=0.0)
    page_height_mm: float = Field(default=297.0, gt=0.0)
    margin_mm: float = Field(default=15.0, ge=0.0)
    line_spacing: float = Field(default=1.5, gt=0.0)
    alignment: Alignment = "left"
    stroke_width_mm: float = Field(default=0.3, gt=0.0)


@dataclass
class Block:
    """A run of text rendered at a single size (e.g. a heading or paragraph)."""

    text: str
    size_mm: float


class HersheyRenderer:
    """Lays out text blocks into a single-stroke SVG document."""

    def __init__(self, options: TypographyOptions) -> None:
        """Create a renderer.

        Args:
            options: Layout parameters.

        Raises:
            ValueError: If the requested font is not available.
        """
        if options.font not in available_fonts():
            raise ValueError(f"Unknown Hershey font: {options.font!r}")
        self.opts = options
        self._font = HersheyFonts()
        self._font.load_default_font(options.font)
        self._current_size = 0.0

    def render_text(self, text: str) -> str:
        """Render plain text (paragraphs separated by newlines) to SVG.

        Args:
            text: The text to render.

        Returns:
            A complete SVG document string.
        """
        return self.render_blocks([Block(text, self.opts.font_size_mm)])

    def render_blocks(self, blocks: list[Block]) -> str:
        """Render a sequence of sized text blocks to SVG.

        Args:
            blocks: Ordered blocks to lay out top to bottom.

        Returns:
            A complete SVG document string.
        """
        usable_w = self.opts.page_width_mm - 2 * self.opts.margin_mm
        cursor_y = self.opts.margin_mm
        paths: list[str] = []

        for block in blocks:
            self._set_size(block.size_mm)
            line_height = block.size_mm * self.opts.line_spacing
            for paragraph in block.text.split("\n"):
                for line in self._wrap(paragraph, usable_w):
                    paths.append(self._render_line(line, block.size_mm, cursor_y, usable_w))
                    cursor_y += line_height

        return self._wrap_svg([p for p in paths if p])

    def _set_size(self, size_mm: float) -> None:
        """Configure the font's rendering scale if it changed."""
        if size_mm != self._current_size:
            self._font.normalize_rendering(size_mm)
            self._current_size = size_mm

    def _measure(self, line: str) -> float:
        """Return the rendered width of a line in millimeters."""
        max_x = 0.0
        for (x0, _), (x1, _) in self._font.lines_for_text(line):
            max_x = max(max_x, x0, x1)
        return max_x

    def _wrap(self, paragraph: str, usable_w: float) -> list[str]:
        """Greedily word-wrap a paragraph to the usable width."""
        words = paragraph.split()
        if not words:
            return [""]
        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if self._measure(candidate) <= usable_w:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def _render_line(self, line: str, size_mm: float, top_y: float, usable_w: float) -> str:
        """Render one already-wrapped line as an SVG path string."""
        if not line.strip():
            return ""
        baseline_y = top_y + size_mm
        x_offset = self.opts.margin_mm + self._align_shift(self._measure(line), usable_w)
        segments: list[str] = []
        for (x0, y0), (x1, y1) in self._font.lines_for_text(line):
            segments.append(
                f"M{x_offset + x0:.2f} {baseline_y - y0:.2f} "
                f"L{x_offset + x1:.2f} {baseline_y - y1:.2f}"
            )
        if not segments:
            return ""
        return f'<path d="{" ".join(segments)}"/>'

    def _align_shift(self, line_width: float, usable_w: float) -> float:
        """Return the horizontal offset for the configured alignment."""
        slack = max(0.0, usable_w - line_width)
        if self.opts.alignment == "center":
            return slack / 2.0
        if self.opts.alignment == "right":
            return slack
        return 0.0

    def _wrap_svg(self, paths: list[str]) -> str:
        """Assemble path strings into a complete SVG document."""
        w, h = self.opts.page_width_mm, self.opts.page_height_mm
        header = (
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
            f'width="{w}mm" height="{h}mm" viewBox="0 0 {w} {h}">'
        )
        group = (
            f'<g fill="none" stroke="black" stroke-width="{self.opts.stroke_width_mm}" '
            f"inkscape:label={quoteattr('text')}>" + "".join(paths) + "</g>"
        )
        return header + group + "</svg>"

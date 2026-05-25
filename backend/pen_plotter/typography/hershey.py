"""Hershey single-stroke text layout to SVG.

Renders text as open polylines (no fills), laying out paragraphs with word
wrap, alignment, and configurable page geometry. Output coordinates are in
millimeters so they map directly onto a machine's workspace.

Each character stroke is emitted as one continuous SVG sub-path so the
downstream toolpath optimizer and G-code generator can draw it in a single
pen-down pass instead of lifting the pen between every line segment.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal
from xml.sax.saxutils import quoteattr

from HersheyFonts import HersheyFonts
from pydantic import BaseModel, Field

Alignment = Literal["left", "center", "right"]

# Synthetic-italic slant (degrees) applied when ``TypographyOptions.italic``
# is set on a font that has no native italic variant. Matches the typical
# slant of TrueType italic faces (~12°) — steep enough to read as italic
# without distorting the glyph beyond recognition.
_ITALIC_SLANT_DEG = 12.0

# Synthetic-bold pass offset, expressed as a fraction of the cap height.
# We emit the strokes twice with a small offset so the pen physically
# paints a thicker line — the SVG ``stroke-width`` attribute is cosmetic
# on a pen plotter and does not actually broaden the drawn strokes.
_BOLD_OFFSET_RATIO = 0.06


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
    # Default is the size of typical readable body text on a pen plotter.
    # 4 mm — what the prototype shipped with — looks fine in the SVG
    # preview but is roughly 3 px tall in the simulator's default
    # workspace-fit view, well below the resolving power of a Hershey
    # glyph. 10 mm is the smallest size that stays comfortably readable
    # both on paper and in the simulator without forcing the operator
    # to zoom in.
    font_size_mm: float = Field(default=10.0, gt=0.0, le=200.0)
    page_width_mm: float = Field(default=210.0, gt=0.0)
    page_height_mm: float = Field(default=297.0, gt=0.0)
    margin_mm: float = Field(default=15.0, ge=0.0)
    line_spacing: float = Field(default=1.5, gt=0.0)
    alignment: Alignment = "left"
    stroke_width_mm: float = Field(default=0.3, gt=0.0)
    # Synthetic style toggles. Hershey fonts are single-stroke so there is
    # no real "bold" or "italic" face; these flags emulate them at render
    # time. ``bold`` draws each stroke twice with a small offset to widen
    # the visible line; ``italic`` shears every point along x by an angle
    # proportional to its height above the baseline.
    bold: bool = False
    italic: bool = False
    # Extra horizontal space inserted between characters, in millimeters.
    # Negative values tighten the spacing (use with care — letters may
    # collide). Applied uniformly to every character on every line.
    letter_spacing_mm: float = Field(default=0.0, ge=-10.0, le=50.0)


@dataclass
class Block:
    """A run of text rendered at a single size (e.g. a heading or paragraph)."""

    text: str
    size_mm: float


@dataclass
class PlacedSpan:
    """A text run rendered at a fixed page position.

    Used by the PDF / DOCX / HTML re-render pipeline, where the
    surrounding document already places each text span at an absolute
    location with its own font size. Coordinates are in the surrounding
    SVG's user units — typically points for PyMuPDF output, millimeters
    for our own typography flow — and ``baseline_y`` follows SVG
    convention (y grows down). ``size`` is the font em-height in the
    same units; the renderer normalizes Hershey output so a capital
    letter is ~70 % of that height, matching the cap-height convention
    of TrueType faces.
    """

    text: str
    x: float
    baseline_y: float
    size: float
    bold: bool = False
    italic: bool = False


def render_placed_spans(
    spans: list[PlacedSpan],
    *,
    font: str = "futural",
    stroke_width: float = 0.3,
    label: str = "text",
) -> str:
    """Render placed text spans as a labeled single-stroke SVG group.

    Each span is drawn at its own ``(x, baseline_y)`` using its own
    ``size`` (and optional bold / italic). Returns one
    ``<g inkscape:label="…">`` holding one ``<path>`` per span, ready to
    be appended to a host SVG document. Returns an empty string when
    every span is blank.

    Args:
        spans: Ordered text spans to render.
        font: Bundled Hershey font name. Falls back to ``futural`` if
            the request names an unknown face.
        stroke_width: SVG ``stroke-width`` attribute (cosmetic; the pen
            plotter ignores it but downstream consumers may render it).
        label: ``inkscape:label`` for the group — drives the layer name
            that ``extract_layers`` produces.
    """
    if not spans:
        return ""
    if font not in available_fonts():
        font = "futural"
    hf = HersheyFonts()
    hf.load_default_font(font)

    current_size = 0.0
    paths: list[str] = []
    for span in spans:
        if span.size <= 0 or not span.text.strip():
            continue
        if span.size != current_size:
            hf.normalize_rendering(span.size)
            current_size = span.size
        path_d = _placed_span_path(hf, span)
        if path_d:
            paths.append(f'<path d="{path_d}"/>')

    if not paths:
        return ""
    # ``xmlns:inkscape`` is declared inline so the fragment parses
    # standalone — callers that splice it into a host SVG via
    # ``xml.etree`` would otherwise hit an "unbound prefix" error
    # because the host's namespace declarations aren't visible to
    # ``ET.fromstring``.
    return (
        '<g xmlns="http://www.w3.org/2000/svg" '
        'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        f'fill="none" stroke="black" stroke-width="{stroke_width}" '
        f"inkscape:label={quoteattr(label)}>" + "".join(paths) + "</g>"
    )


def _placed_span_path(hf: HersheyFonts, span: PlacedSpan) -> str:
    """Serialize one placed span's strokes to an SVG path ``d`` value.

    Handles the same synthetic style transforms as :class:`HersheyRenderer`
    (bold = double-pass with a small x offset; italic = ~12° x-shear)
    so the placed flow and the laid-out flow paint identical glyphs.
    """
    italic_shear = math.tan(math.radians(_ITALIC_SLANT_DEG)) if span.italic else 0.0
    bold_offset = span.size * _BOLD_OFFSET_RATIO if span.bold else 0.0
    passes = (0.0, bold_offset) if span.bold else (0.0,)

    subpaths: list[str] = []
    for offset_x in passes:
        for stroke in hf.strokes_for_text(span.text):
            pts = list(stroke)
            if len(pts) < 2:
                continue
            placed = [
                (
                    span.x + offset_x + x + y * italic_shear,
                    span.baseline_y - y,
                )
                for x, y in pts
            ]
            head = f"M{placed[0][0]:.2f} {placed[0][1]:.2f}"
            tail = " ".join(f"L{px:.2f} {py:.2f}" for px, py in placed[1:])
            subpaths.append(f"{head} {tail}")
    return " ".join(subpaths)


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
            A complete SVG document string. The returned SVG's viewBox
            covers ``page_height_mm`` exactly; if the laid-out content
            extends past the bottom margin the SVG is grown vertically
            so every glyph is reachable inside the plotter's workspace
            and the operator sees the overflow instead of having text
            silently clipped at the page boundary.
        """
        usable_w = self.opts.page_width_mm - 2 * self.opts.margin_mm
        usable_bottom = self.opts.page_height_mm - self.opts.margin_mm
        cursor_y = self.opts.margin_mm
        paths: list[str] = []
        max_baseline = cursor_y

        for block in blocks:
            self._set_size(block.size_mm)
            line_height = block.size_mm * self.opts.line_spacing
            for paragraph in block.text.split("\n"):
                for line in self._wrap(paragraph, usable_w):
                    paths.append(self._render_line(line, block.size_mm, cursor_y, usable_w))
                    cursor_y += line_height
                    max_baseline = max(max_baseline, cursor_y)

        # Grow the page when content overflowed so nothing is clipped.
        # The margin is preserved at the new bottom edge.
        effective_height = self.opts.page_height_mm
        if max_baseline > usable_bottom:
            effective_height = max_baseline + self.opts.margin_mm
        return self._wrap_svg([p for p in paths if p], height_mm=effective_height)

    def _set_size(self, size_mm: float) -> None:
        """Configure the font's rendering scale if it changed."""
        if size_mm != self._current_size:
            self._font.normalize_rendering(size_mm)
            self._current_size = size_mm

    def _strokes(self, text: str) -> list[list[tuple[float, float]]]:
        """Return continuous stroke polylines for ``text`` with kerning applied.

        ``strokes_for_text`` already returns one polyline per pen-down so
        each glyph stays connected. We extend it with optional uniform
        ``letter_spacing_mm`` by re-laying out one character at a time
        when the operator asked for non-zero spacing — the underlying
        library has no kerning knob.
        """
        if self.opts.letter_spacing_mm == 0.0:
            return [list(stroke) for stroke in self._font.strokes_for_text(text)]

        strokes: list[list[tuple[float, float]]] = []
        cursor_x = 0.0
        spacing = self.opts.letter_spacing_mm
        for ch in text:
            if ch == " ":
                # Use the font's own space advance and add the spacing tweak.
                space_w = self._char_advance(" ")
                cursor_x += space_w + spacing
                continue
            char_strokes = [list(s) for s in self._font.strokes_for_text(ch)]
            advance = self._char_advance(ch)
            for stroke in char_strokes:
                strokes.append([(cursor_x + x, y) for x, y in stroke])
            cursor_x += advance + spacing
        return strokes

    def _char_advance(self, ch: str) -> float:
        """Approximate the advance width of ``ch`` in current font units."""
        max_x = 0.0
        for stroke in self._font.strokes_for_text(ch):
            for x, _ in stroke:
                if x > max_x:
                    max_x = x
        # Spaces have no strokes; fall back to half the cap height so we
        # still advance the cursor on whitespace.
        if max_x == 0.0:
            return self._current_size * 0.4
        return max_x

    def _measure(self, line: str) -> float:
        """Return the rendered width of a line in millimeters."""
        x_min = math.inf
        x_max = -math.inf
        for stroke in self._strokes(line):
            for x, _ in stroke:
                if x < x_min:
                    x_min = x
                if x > x_max:
                    x_max = x
        if x_max == -math.inf:
            return 0.0
        return x_max - min(x_min, 0.0)

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

    def _transform(
        self, x: float, y: float, x_offset: float, baseline_y: float
    ) -> tuple[float, float]:
        """Convert a font-space point to page-space, applying italic shear.

        Font coordinates are y-up with the baseline at ``y=0``. We flip y
        against ``baseline_y`` to map into the SVG y-down system and then
        apply the italic shear in page space so the slant follows the
        upright character height.
        """
        if self.opts.italic:
            shear = math.tan(math.radians(_ITALIC_SLANT_DEG))
            x = x + y * shear
        return x_offset + x, baseline_y - y

    def _stroke_to_path(
        self,
        stroke: list[tuple[float, float]],
        x_offset: float,
        baseline_y: float,
    ) -> str:
        """Serialize one polyline as a single ``M ... L ...`` sub-path."""
        if len(stroke) < 2:
            return ""
        points = [self._transform(x, y, x_offset, baseline_y) for x, y in stroke]
        head = f"M{points[0][0]:.2f} {points[0][1]:.2f}"
        tail = " ".join(f"L{px:.2f} {py:.2f}" for px, py in points[1:])
        return f"{head} {tail}"

    def _render_line(self, line: str, size_mm: float, top_y: float, usable_w: float) -> str:
        """Render one already-wrapped line as an SVG path string."""
        if not line.strip():
            return ""
        baseline_y = top_y + size_mm
        x_offset = self.opts.margin_mm + self._align_shift(self._measure(line), usable_w)

        strokes = self._strokes(line)
        subpaths: list[str] = []
        for stroke in strokes:
            sub = self._stroke_to_path(stroke, x_offset, baseline_y)
            if sub:
                subpaths.append(sub)

        if self.opts.bold:
            # Second pass slightly offset so the pen physically paints a
            # wider line. Scale by the font size so the effect tracks the
            # cap height instead of being invisible at large sizes.
            offset = size_mm * _BOLD_OFFSET_RATIO
            for stroke in strokes:
                shifted = [(x + offset, y) for x, y in stroke]
                sub = self._stroke_to_path(shifted, x_offset, baseline_y)
                if sub:
                    subpaths.append(sub)

        if not subpaths:
            return ""
        return f'<path d="{" ".join(subpaths)}"/>'

    def _align_shift(self, line_width: float, usable_w: float) -> float:
        """Return the horizontal offset for the configured alignment."""
        slack = max(0.0, usable_w - line_width)
        if self.opts.alignment == "center":
            return slack / 2.0
        if self.opts.alignment == "right":
            return slack
        return 0.0

    def _wrap_svg(self, paths: list[str], *, height_mm: float | None = None) -> str:
        """Assemble path strings into a complete SVG document.

        ``height_mm`` overrides ``opts.page_height_mm`` so the laid-out
        content can grow the viewBox vertically when text overflows the
        configured page (see :meth:`render_blocks`). Width is fixed by
        the operator-configured ``page_width_mm`` — word wrap already
        keeps every line within it.
        """
        w = self.opts.page_width_mm
        h = height_mm if height_mm is not None else self.opts.page_height_mm
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

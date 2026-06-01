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
import unicodedata
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

# Minimum horizontal scale before the renderer falls back to breaking a
# token at character boundaries. When a line is wider than the page's
# usable width we squeeze it horizontally — the inter-letter and
# inter-word spacing tightens proportionally — so the whole word stays
# intact instead of being cut in the middle. Below ~60 % scale the
# single-stroke glyphs start to overlap each other and the line stops
# being readable, so any token still too wide at that point is split.
_MIN_LINE_SCALE = 0.6

# Minimum horizontal scale for the placed-span path (PDF / DOCX / SVG
# re-render). Placed spans must fit their source layout — there is no
# word-wrap fallback like the plain-text flow has — so we accept any
# compression that mathematically brings the Hershey extent back to
# the source bbox width. The operator's document layout wins over
# readability: rendering at, say, 30 % horizontal scale produces
# cramped but recognizable strokes, whereas leaving the line wider
# than the source pushes the right end past the page edge — the
# defect the operator originally reported.
_MIN_PLACED_SPAN_SCALE = 0.0

# Pre-substitution table for code points that have no Hershey glyph but
# read identically (or close enough) as one or more printable ASCII
# characters. The upstream ``HersheyFonts`` library silently drops any
# character that is not in its glyph dict — and the bundled fonts only
# carry printable ASCII (codes 32–127). Without this table, ``café``
# ends up plotted as ``caf``, smart-quoted text loses its quotes, and
# every em dash vanishes; worse, the dropped characters contribute zero
# advance, so the surrounding word collapses into a tighter run that the
# operator reads as a typo. The mapping is intentionally conservative —
# only characters whose ASCII rendering would not surprise a francophone
# / anglophone reader. Anything else falls through to NFKD decomposition
# (which strips combining accents from Latin code points) and finally to
# :data:`_FALLBACK_CHAR` so the missing glyph is visible rather than
# silently dropped.
_TYPOGRAPHIC_REPLACEMENTS = {
    # Whitespace variants — collapse to ordinary space so word wrap works.
    " ": " ",  # NBSP
    " ": " ",  # ogham space mark
    " ": " ",  # en space
    " ": " ",  # em space
    " ": " ",  # three-per-em space
    " ": " ",  # four-per-em space
    " ": " ",  # six-per-em space
    " ": " ",  # figure space
    " ": " ",  # punctuation space
    " ": " ",  # thin space
    " ": " ",  # hair space
    " ": " ",  # narrow no-break space
    " ": " ",  # medium mathematical space
    "　": " ",  # ideographic space
    # Zero-width chars — drop entirely so they don't ghost as fallback "?".
    "​": "",   # zero-width space
    "‌": "",   # zero-width non-joiner
    "‍": "",   # zero-width joiner
    "⁠": "",   # word joiner
    "﻿": "",   # BOM / zero-width no-break space
    # Smart quotes and guillemets.
    "‘": "'",
    "’": "'",
    "‚": ",",
    "‛": "'",
    "“": '"',
    "”": '"',
    "„": '"',
    "‟": '"',
    "«": '"',  # «
    "»": '"',  # »
    "‹": "<",  # ‹
    "›": ">",  # ›
    # Dashes — all collapse to hyphen-minus.
    "‐": "-",
    "‑": "-",
    "‒": "-",
    "–": "-",
    "—": "-",
    "―": "-",
    "−": "-",
    # Ellipsis and other punctuation.
    "…": "...",
    "·": ".",   # middle dot
    "•": "*",   # bullet
    "‣": "*",
    "◦": "o",
    # Math operators that have an obvious ASCII fallback.
    "×": "x",   # ×
    "÷": "/",   # ÷
    "≠": "!=",
    "≤": "<=",
    "≥": ">=",
    "±": "+/-",
    # Ligatures.
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "œ": "oe",  # œ
    "Œ": "OE",  # Œ
    "æ": "ae",  # æ
    "Æ": "AE",  # Æ
    "ß": "ss",  # ß
    # Currency symbols — keep short so they don't stretch the line.
    "€": "EUR",
    "£": "GBP",
    "¥": "YEN",
    "¢": "c",   # cent
    # Common typographic marks that have no ASCII equivalent — keep the
    # fallback explicit so changes to ``_FALLBACK_CHAR`` propagate.
    "°": "deg",  # degree sign
    "©": "(c)",
    "®": "(R)",
    "™": "(TM)",
    "§": "S",   # section sign
    "¶": "P",   # pilcrow
}

# Visible placeholder for code points that survive substitution + NFKD
# decomposition but still aren't in the font. A printed "?" beats a
# silently shortened word — the operator immediately sees that an input
# character could not be drawn.
_FALLBACK_CHAR = "?"


def _sanitize_for_font(text: str, supported: frozenset[str]) -> str:
    r"""Map ``text`` to characters the loaded Hershey font can render.

    Pipeline, applied per code point:

    1. Pass through anything already in ``supported`` (plus ``\\n`` and
       ``\\t`` — the layout splits paragraphs on newlines and the input
       may contain tabs).
    2. Look up :data:`_TYPOGRAPHIC_REPLACEMENTS` for known typographic
       variants (smart quotes, dashes, NBSP, ligatures, …) and emit the
       ASCII replacement (zero, one, or several characters).
    3. NFKD-decompose the code point and keep the base characters that
       are supported, dropping Unicode combining marks. This turns
       Latin diacritics — ``é``, ``ñ``, ``ç`` — into plain Romanizations
       since the bundled Hershey fonts carry no accented forms.
    4. Replace anything still unmapped with :data:`_FALLBACK_CHAR` so
       missing glyphs are visible rather than silently dropped.

    Args:
        text: Source text from the operator's file (any Unicode).
        supported: Glyph keys of the currently loaded Hershey font.

    Returns:
        A string in which every character (other than ``\\n`` / ``\\t``)
        is either in ``supported`` or equal to :data:`_FALLBACK_CHAR`.
    """
    if not text:
        return text
    out: list[str] = []
    for ch in text:
        if ch in supported or ch == "\n" or ch == "\t":
            out.append(ch)
            continue
        replacement = _TYPOGRAPHIC_REPLACEMENTS.get(ch)
        if replacement is not None:
            for r in replacement:
                out.append(r if r in supported else _FALLBACK_CHAR)
            continue
        kept: list[str] = []
        for c in unicodedata.normalize("NFKD", ch):
            if unicodedata.combining(c):
                continue
            if c in supported:
                kept.append(c)
        if kept:
            out.extend(kept)
        else:
            out.append(_FALLBACK_CHAR)
    return "".join(out)


@lru_cache(maxsize=8)
def _supported_chars(font_name: str) -> frozenset[str]:
    """Return the glyph keys for a bundled Hershey font.

    Cached because :class:`HersheyFonts` re-decodes the bundled font
    table from a base64 blob on every ``load_default_font`` call —
    fine when rendering, wasteful when we only need to know which
    characters the font carries.
    """
    hf = HersheyFonts()
    hf.load_default_font(font_name)
    return frozenset(hf.all_glyphs.keys())


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

    ``source_width`` is the source document's intended visual width of
    this span (typically the PyMuPDF ``bbox`` width). When set and the
    Hershey rendering is wider — which is common because single-stroke
    Hershey glyphs are typically broader than the source TrueType face
    at the same point size — the renderer compresses the span's x
    coordinates so its inter-letter and inter-word spacing tightens to
    fit the source extent, instead of overflowing past the right edge
    of the line in the source document's layout.
    """

    text: str
    x: float
    baseline_y: float
    size: float
    bold: bool = False
    italic: bool = False
    source_width: float | None = None


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
    supported = _supported_chars(font)

    current_size = 0.0
    paths: list[str] = []
    for span in spans:
        if span.size <= 0 or not span.text.strip():
            continue
        # Substitute Unicode characters the font cannot render BEFORE
        # measuring or drawing. Without this, accented Latin letters and
        # smart-quote punctuation extracted from a PDF/DXF are dropped
        # by ``strokes_for_text`` and the placed glyphs lose their
        # surrounding context.
        sanitized = _sanitize_for_font(span.text, supported)
        if not sanitized.strip():
            continue
        if span.size != current_size:
            hf.normalize_rendering(span.size)
            current_size = span.size
        path_d = _placed_span_path(hf, span, sanitized)
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


def _placed_span_path(hf: HersheyFonts, span: PlacedSpan, text: str) -> str:
    """Serialize one placed span's strokes to an SVG path ``d`` value.

    Handles the same synthetic style transforms as :class:`HersheyRenderer`
    (bold = double-pass with a small x offset; italic = ~12° x-shear)
    so the placed flow and the laid-out flow paint identical glyphs.
    ``text`` is the font-sanitized string to draw; ``span.text`` is the
    caller's original (pre-sanitization) source, kept so any future
    diagnostics can show the raw input.

    When ``span.source_width`` is set and the natural Hershey extent of
    ``text`` is wider, the glyphs are compressed horizontally (down to
    ``_MIN_LINE_SCALE``) so the span fits the source document's
    intended layout — otherwise PDF / DOCX text drifts rightward and
    overflows the line because Hershey glyphs are wider than the
    document's original TrueType face at the same point size.
    """
    italic_shear = math.tan(math.radians(_ITALIC_SLANT_DEG)) if span.italic else 0.0
    bold_offset = span.size * _BOLD_OFFSET_RATIO if span.bold else 0.0
    passes = (0.0, bold_offset) if span.bold else (0.0,)

    # Snapshot strokes once: ``strokes_for_text`` advances internal
    # state and we re-walk the polylines for both the measurement and
    # the (possibly doubled) draw passes.
    strokes = [list(stroke) for stroke in hf.strokes_for_text(text)]

    x_scale = 1.0
    if span.source_width is not None and span.source_width > 0:
        x_max = -math.inf
        for stroke in strokes:
            for x, _ in stroke:
                if x > x_max:
                    x_max = x
        # Account for the bold pass's right-side offset so a bold span
        # is squeezed enough to fit including its widening pass.
        natural_w = (x_max if x_max != -math.inf else 0.0) + bold_offset
        if natural_w > span.source_width:
            x_scale = max(_MIN_PLACED_SPAN_SCALE, span.source_width / natural_w)

    subpaths: list[str] = []
    for offset_x in passes:
        for stroke in strokes:
            if len(stroke) < 2:
                continue
            placed = [
                (
                    span.x + (offset_x + x) * x_scale + y * italic_shear,
                    span.baseline_y - y,
                )
                for x, y in stroke
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
        # Snapshot of the glyph keys the font carries. Used by
        # :func:`_sanitize_for_font` to map operator-supplied Unicode to
        # characters the font can actually draw — without this the
        # upstream library silently drops anything outside printable
        # ASCII (accents, smart quotes, em dashes, NBSP, …), which the
        # operator perceives as "letters going missing".
        self._supported = frozenset(self._font.all_glyphs.keys())

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
            # Sanitize the block's text ONCE at the entry boundary so
            # every downstream measurement, word-wrap split, and stroke
            # lookup operates on the same string. Doing it later — e.g.
            # inside ``_strokes`` only — would desync ``_measure`` (which
            # would still see the un-sanitized text) and the wrap would
            # break in the middle of a multi-character replacement like
            # ``…`` → ``...``.
            sanitized = _sanitize_for_font(block.text, self._supported)
            for paragraph in sanitized.split("\n"):
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
        """Return the typographic advance of ``ch`` in millimeters.

        Uses the glyph's ``char_width`` (right_side − left_side in raw
        font units) scaled by the active render scale, which matches
        what :func:`HersheyFonts.strokes_for_text` itself uses to space
        characters. The earlier implementation read the stroke
        bounding-box max-x — which omits the right side-bearing and so
        consistently underestimated the advance, packing letters too
        tightly in the ``letter_spacing != 0`` path. It also returned a
        constant fudge for whitespace (spaces have no strokes), giving
        spaces a different visible width depending on whether
        ``letter_spacing`` was set.
        """
        glyph = self._font.all_glyphs.get(ch)
        if glyph is None:
            return 0.0
        scalex = self._font.render_options["scalex"]
        # ``scalex`` is positive after ``normalize_rendering``; guard for
        # the (unused) case where the operator has flipped the axis.
        return float(glyph.char_width * abs(scalex))

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
        """Greedily word-wrap a paragraph to the maximum compressible width.

        Wrapping is performed at ``max_natural_w = usable_w / _MIN_LINE_SCALE``
        rather than at ``usable_w``: any line whose natural width fits
        within that bound can be squeezed back to ``usable_w`` by
        :meth:`_render_line`. Aiming for the compressible bound means a
        paragraph that overflows the usable area by a moderate amount
        stays on a single output line (slightly compressed) instead of
        being re-flowed into two natural-width lines — preserving the
        source document's line layout and avoiding the vertical
        overflow that an aggressive re-wrap would cause.

        Tokens still too wide at maximum compression are hard-broken at
        character boundaries: below ``_MIN_LINE_SCALE`` single-stroke
        glyphs collide and the line stops being legible.
        """
        words = paragraph.split()
        if not words:
            return [""]
        max_natural_w = usable_w / _MIN_LINE_SCALE
        pieces: list[str] = []
        for word in words:
            if self._measure(word) > max_natural_w:
                pieces.extend(self._break_long_word(word, max_natural_w))
            else:
                pieces.append(word)
        lines: list[str] = []
        current = pieces[0]
        for piece in pieces[1:]:
            candidate = f"{current} {piece}"
            if self._measure(candidate) <= max_natural_w:
                current = candidate
            else:
                lines.append(current)
                current = piece
        lines.append(current)
        return lines

    def _break_long_word(self, word: str, usable_w: float) -> list[str]:
        """Split ``word`` into chunks each fitting inside ``usable_w``.

        Last-resort hyphenation for tokens so wide that even maximum
        horizontal compression couldn't squeeze them onto a single line
        — long URLs, chemical names, or huge font sizes. The split is
        purely greedy at character boundaries; a chunk reduced to a
        single character is kept as-is even if that character alone
        overflows, since we cannot split further.
        """
        pieces: list[str] = []
        current = ""
        for ch in word:
            candidate = current + ch
            if current and self._measure(candidate) > usable_w:
                pieces.append(current)
                current = ch
            else:
                current = candidate
        if current:
            pieces.append(current)
        return pieces or [word]

    def _transform(
        self,
        x: float,
        y: float,
        x_offset: float,
        baseline_y: float,
        x_scale: float = 1.0,
    ) -> tuple[float, float]:
        """Convert a font-space point to page-space, applying italic shear.

        Font coordinates are y-up with the baseline at ``y=0``. We flip y
        against ``baseline_y`` to map into the SVG y-down system. The
        per-line ``x_scale`` is applied in font space (before the italic
        shear) so a compressed line keeps the italic angle of an upright
        line — only the horizontal extent of the glyphs and the gaps
        between them tighten.
        """
        if x_scale != 1.0:
            x = x * x_scale
        if self.opts.italic:
            shear = math.tan(math.radians(_ITALIC_SLANT_DEG))
            x = x + y * shear
        return x_offset + x, baseline_y - y

    def _stroke_to_path(
        self,
        stroke: list[tuple[float, float]],
        x_offset: float,
        baseline_y: float,
        x_scale: float = 1.0,
    ) -> str:
        """Serialize one polyline as a single ``M ... L ...`` sub-path."""
        if len(stroke) < 2:
            return ""
        points = [self._transform(x, y, x_offset, baseline_y, x_scale) for x, y in stroke]
        head = f"M{points[0][0]:.2f} {points[0][1]:.2f}"
        tail = " ".join(f"L{px:.2f} {py:.2f}" for px, py in points[1:])
        return f"{head} {tail}"

    def _render_line(self, line: str, size_mm: float, top_y: float, usable_w: float) -> str:
        """Render one already-wrapped line as an SVG path string."""
        if not line.strip():
            return ""
        baseline_y = top_y + size_mm
        natural_w = self._measure(line)
        # Squeeze lines that overflow horizontally so the word stays
        # intact instead of being cut on the right. ``_wrap`` already
        # guarantees the natural width never exceeds the corresponding
        # bound (``usable_w / _MIN_LINE_SCALE``), so the resulting scale
        # is always ``>= _MIN_LINE_SCALE`` and the glyphs remain legible.
        x_scale = 1.0
        if natural_w > usable_w and natural_w > 0:
            x_scale = usable_w / natural_w
        line_width = natural_w * x_scale
        x_offset = self.opts.margin_mm + self._align_shift(line_width, usable_w)

        strokes = self._strokes(line)
        subpaths: list[str] = []
        for stroke in strokes:
            sub = self._stroke_to_path(stroke, x_offset, baseline_y, x_scale)
            if sub:
                subpaths.append(sub)

        if self.opts.bold:
            # Second pass slightly offset so the pen physically paints a
            # wider line. Scale by the font size so the effect tracks the
            # cap height instead of being invisible at large sizes.
            offset = size_mm * _BOLD_OFFSET_RATIO
            for stroke in strokes:
                shifted = [(x + offset, y) for x, y in stroke]
                sub = self._stroke_to_path(shifted, x_offset, baseline_y, x_scale)
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

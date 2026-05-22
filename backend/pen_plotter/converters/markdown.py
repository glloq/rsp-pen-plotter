"""Markdown converter.

Parses Markdown into sized text blocks (headings larger than body text, list
items bulleted) and renders them with single-stroke Hershey fonts.
"""

from __future__ import annotations

from typing import Any, ClassVar

from markdown_it import MarkdownIt
from markdown_it.token import Token

from pen_plotter.converters.base import ConversionResult, Converter
from pen_plotter.typography import Block, HersheyRenderer, TypographyOptions

_HEADING_SCALE = {"h1": 2.0, "h2": 1.6, "h3": 1.3, "h4": 1.15, "h5": 1.0, "h6": 1.0}


def _blocks_from_markdown(text: str, base_size: float) -> list[Block]:
    """Convert Markdown source into sized text blocks.

    Args:
        text: Markdown source.
        base_size: Body font size in millimeters.

    Returns:
        Ordered blocks ready for the Hershey renderer.
    """
    tokens = MarkdownIt().parse(text)
    blocks: list[Block] = []
    in_list = False

    for i, token in enumerate(tokens):
        if token.type == "heading_open":
            scale = _HEADING_SCALE.get(token.tag, 1.0)
            content = _inline_text(tokens[i + 1]) if i + 1 < len(tokens) else ""
            blocks.append(Block(content, base_size * scale))
        elif token.type in ("bullet_list_open", "ordered_list_open"):
            in_list = True
        elif token.type in ("bullet_list_close", "ordered_list_close"):
            in_list = False
        elif token.type == "inline" and token.content:
            parent = tokens[i - 1].type if i > 0 else ""
            if parent == "heading_open":
                continue
            prefix = "- " if in_list else ""
            blocks.append(Block(prefix + token.content, base_size))

    return blocks


def _inline_text(token: Token) -> str:
    """Return the plain text content of an inline token."""
    return token.content if token.type == "inline" else ""


class MarkdownConverter(Converter):
    """Renders Markdown to a single-stroke SVG document."""

    supported_mimes: ClassVar[frozenset[str]] = frozenset({"text/markdown"})

    def convert(self, data: bytes, *, options: dict[str, Any] | None = None) -> ConversionResult:
        """Render Markdown bytes to SVG.

        Args:
            data: Raw UTF-8 Markdown bytes.
            options: Optional parameters validated against
                :class:`~pen_plotter.typography.TypographyOptions`.

        Returns:
            A :class:`ConversionResult` containing the rendered SVG.

        Raises:
            ValueError: If typography options are invalid.
        """
        text = data.decode("utf-8", errors="replace")
        opts = TypographyOptions.model_validate(options or {})
        renderer = HersheyRenderer(opts)
        blocks = _blocks_from_markdown(text, opts.font_size_mm)
        return ConversionResult(svg=renderer.render_blocks(blocks), source_mime="image/svg+xml")

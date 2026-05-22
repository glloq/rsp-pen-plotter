"""Default converter registration.

Centralizes which converters are available so the app and tests share one
source of truth.
"""

from __future__ import annotations

from pen_plotter.converters.bitmap import BitmapConverter
from pen_plotter.converters.document import DocumentConverter
from pen_plotter.converters.dxf import DxfConverter
from pen_plotter.converters.eps import EpsConverter
from pen_plotter.converters.html import HtmlConverter
from pen_plotter.converters.markdown import MarkdownConverter
from pen_plotter.converters.pdf import PdfConverter
from pen_plotter.converters.registry import ConverterRegistry
from pen_plotter.converters.svg import SvgConverter
from pen_plotter.converters.text import TextConverter


def register_default_converters(target: ConverterRegistry) -> None:
    """Register every built-in converter on the given registry.

    Args:
        target: The registry to populate.
    """
    target.register(SvgConverter())
    target.register(BitmapConverter())
    target.register(PdfConverter())
    target.register(DxfConverter())
    target.register(EpsConverter())
    target.register(TextConverter())
    target.register(MarkdownConverter())
    target.register(HtmlConverter())
    target.register(DocumentConverter())

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

    Idempotent: converters whose MIME types are already registered are skipped,
    so this is safe to call from both application startup and test setup.

    Args:
        target: The registry to populate.
    """
    existing = target.supported_mimes()
    converters = [
        SvgConverter(),
        BitmapConverter(),
        PdfConverter(),
        DxfConverter(),
        EpsConverter(),
        TextConverter(),
        MarkdownConverter(),
        HtmlConverter(),
        DocumentConverter(),
    ]
    for converter in converters:
        if converter.supported_mimes & existing:
            continue
        target.register(converter)

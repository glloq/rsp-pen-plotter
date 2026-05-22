"""Converter plugin layer.

Each converter normalizes one or more input MIME types to the SVG pivot
format. The standard pipeline runs identically downstream regardless of input.
"""

from pen_plotter.converters.base import ConversionResult, Converter, UnsupportedFormatError
from pen_plotter.converters.registry import ConverterRegistry, registry
from pen_plotter.converters.svg import SvgConverter

__all__ = [
    "ConversionResult",
    "Converter",
    "ConverterRegistry",
    "SvgConverter",
    "UnsupportedFormatError",
    "registry",
]

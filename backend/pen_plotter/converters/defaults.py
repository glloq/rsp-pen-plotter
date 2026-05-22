"""Default converter registration.

Centralizes which converters are available so the app and tests share one
source of truth.
"""

from __future__ import annotations

from pen_plotter.converters.bitmap import BitmapConverter
from pen_plotter.converters.registry import ConverterRegistry
from pen_plotter.converters.svg import SvgConverter


def register_default_converters(target: ConverterRegistry) -> None:
    """Register every built-in converter on the given registry.

    Args:
        target: The registry to populate.
    """
    target.register(SvgConverter())
    target.register(BitmapConverter())

"""DXF converter.

Renders DXF modelspace entities to SVG using the ezdxf drawing add-on with
its native SVG backend.
"""

from __future__ import annotations

import io
from typing import Any, ClassVar

import ezdxf
from ezdxf.addons.drawing import Frontend, RenderContext
from ezdxf.addons.drawing.layout import Page
from ezdxf.addons.drawing.svg import SVGBackend

from pen_plotter.converters.base import ConversionResult, Converter


class DxfConverter(Converter):
    """Converts a DXF drawing's modelspace to the SVG pivot format."""

    supported_mimes: ClassVar[frozenset[str]] = frozenset(
        {"image/vnd.dxf", "application/dxf", "image/x-dxf"}
    )

    def convert(self, data: bytes, *, options: dict[str, Any] | None = None) -> ConversionResult:
        """Convert DXF bytes to SVG.

        Args:
            data: Raw DXF file bytes (UTF-8 or latin-1 text).
            options: Unused; accepted for interface compatibility.

        Returns:
            A :class:`ConversionResult` containing the rendered SVG.

        Raises:
            ValueError: If the bytes are not a parseable DXF document.
        """
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1")
        try:
            doc = ezdxf.read(io.StringIO(text))
        except ezdxf.DXFError as exc:
            raise ValueError(f"Invalid DXF document: {exc}") from exc

        msp = doc.modelspace()
        backend = SVGBackend()
        Frontend(RenderContext(doc), backend).draw_layout(msp)
        svg = backend.get_string(Page(0, 0))
        return ConversionResult(svg=svg, source_mime="image/svg+xml")

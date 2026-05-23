"""DXF converter.

Renders DXF modelspace entities to SVG using the ezdxf drawing add-on with
its native SVG backend, then runs :func:`postprocess_dxf_svg` to strip the
editor-background ``<rect>`` (which would otherwise plot as a giant frame)
and re-bucket drawables by colour class into ``<g inkscape:label="color-…">``
groups so multi-colour DXF drawings keep their per-colour separation as
distinct plotter layers.
"""

from __future__ import annotations

import io
from typing import Any, ClassVar

import ezdxf
from ezdxf.addons.drawing import Frontend, RenderContext
from ezdxf.addons.drawing.layout import Page
from ezdxf.addons.drawing.svg import SVGBackend

from pen_plotter.converters.base import ConversionResult, Converter
from pen_plotter.core.dxf_postprocess import postprocess_dxf_svg


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
            A :class:`ConversionResult` containing the post-processed SVG —
            background rect removed, drawables grouped per colour class.

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
        raw_svg = backend.get_string(Page(0, 0))
        svg = postprocess_dxf_svg(raw_svg)
        return ConversionResult(svg=svg, source_mime="image/svg+xml")

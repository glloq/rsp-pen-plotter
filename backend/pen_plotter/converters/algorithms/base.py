"""Abstract raster algorithm interface.

A raster algorithm turns a single binary color region (a mask over the source
image) into plotter-friendly SVG geometry for one layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from numpy.typing import NDArray


class RasterAlgorithm(ABC):
    """Renders one binary color region into an SVG layer group."""

    name: ClassVar[str]
    description: ClassVar[str]

    @abstractmethod
    def render_layer(
        self,
        mask: NDArray[Any],
        color_hex: str,
        label: str,
        *,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Render a color region as an SVG ``<g>`` group.

        Args:
            mask: Boolean array (height, width); ``True`` marks region pixels.
            color_hex: Hex color for the layer, e.g. ``"#1a2b3c"``.
            label: Human-readable layer label.
            options: Optional algorithm-specific parameters.

        Returns:
            A single SVG ``<g>...</g>`` group as a string. Coordinates are in
            pixel space matching the source image (origin top-left).
        """
        raise NotImplementedError

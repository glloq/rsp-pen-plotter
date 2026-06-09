"""Direct vectorization via the potrace binary.

Traces the outline of a binary color region into filled SVG paths. Requires
the ``potrace`` command-line tool to be installed on the host.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from pen_plotter.converters.algorithms.base import OptionSpec, RasterAlgorithm

_GROUP_RE = re.compile(r"<g\b.*?</g>", re.DOTALL)


class DirectVectorizationAlgorithm(RasterAlgorithm):
    """Traces region outlines into filled paths using potrace."""

    name: ClassVar[str] = "direct"
    description: ClassVar[str] = "Trace region outlines into filled vector paths (potrace)."

    # ``direct`` is parameterless — potrace is invoked with fixed defaults.
    options_schema: ClassVar[list[OptionSpec]] = []

    def render_layer(
        self,
        mask: NDArray[Any],
        color_hex: str,
        label: str,
        *,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Trace the mask outline and return a recolored, labeled SVG group.

        Args:
            mask: Boolean array (height, width); ``True`` marks region pixels.
            color_hex: Hex color applied as the path fill.
            label: Layer label written to ``inkscape:label``.
            options: Unused; accepted for interface compatibility.

        Returns:
            A single SVG ``<g>...</g>`` group, or an empty group if the region
            yields no traceable geometry.

        Raises:
            RuntimeError: If the ``potrace`` binary is not available.
        """
        if shutil.which("potrace") is None:
            raise RuntimeError(
                "The 'potrace' binary is required for direct vectorization but was not found."
            )
        empty = f"<g inkscape:label={quoteattr(label)} fill={quoteattr(color_hex)}></g>"
        if not mask.any():
            return empty

        pixels = np.where(mask, np.uint8(0), np.uint8(255))
        with tempfile.TemporaryDirectory() as tmp:
            bmp_path = Path(tmp) / "mask.bmp"
            svg_path = Path(tmp) / "mask.svg"
            Image.fromarray(pixels).convert("1").save(bmp_path)
            subprocess.run(
                ["potrace", "-b", "svg", "-o", str(svg_path), str(bmp_path)],
                check=True,
                capture_output=True,
                timeout=120,
            )
            traced = svg_path.read_text()

        match = _GROUP_RE.search(traced)
        if match is None:
            return empty
        group = match.group(0)
        group = group.replace('fill="#000000"', f"fill={quoteattr(color_hex)}", 1)
        return group.replace("<g ", f"<g inkscape:label={quoteattr(label)} ", 1)

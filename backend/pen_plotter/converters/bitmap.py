"""Bitmap converter.

Loads raster images (PNG/JPG/TIFF/WebP, plus HEIC/HEIF), separates them into a
small set of colors via k-means, and renders each color region to an SVG layer
using a selectable raster algorithm.
"""

from __future__ import annotations

import io
from typing import Any, ClassVar

import numpy as np
import pillow_heif
from numpy.typing import NDArray
from PIL import Image
from pydantic import BaseModel, Field
from sklearn.cluster import KMeans

from pen_plotter.converters.algorithms import get_algorithm
from pen_plotter.converters.base import ConversionResult, Converter

pillow_heif.register_heif_opener()

_REC709 = np.array([0.2126, 0.7152, 0.0722])


class BitmapOptions(BaseModel):
    """Validated options accepted by :class:`BitmapConverter`."""

    algorithm: str = "direct"
    num_colors: int = Field(default=4, ge=1, le=32)
    max_dimension_px: int = Field(default=800, ge=16, le=4096)
    drop_background: bool = True
    background_luminance: float = Field(default=0.92, ge=0.0, le=1.0)
    algorithm_options: dict[str, Any] = Field(default_factory=dict)


class BitmapConverter(Converter):
    """Separates a raster image into per-color SVG layers."""

    supported_mimes: ClassVar[frozenset[str]] = frozenset(
        {
            "image/png",
            "image/jpeg",
            "image/tiff",
            "image/webp",
            "image/heic",
            "image/heif",
        }
    )

    def convert(
        self,
        data: bytes,
        *,
        options: dict[str, Any] | None = None,
        fast: bool = False,
    ) -> ConversionResult:
        """Convert image bytes into a layered SVG pivot document.

        Args:
            data: Raw image file bytes.
            options: Optional parameters validated against :class:`BitmapOptions`.
            fast: When ``True``, force a small ``max_dimension_px`` and a single
                k-means initialisation. Used by the ``/preview`` endpoint to
                trade quality for sub-second turnaround.

        Returns:
            A :class:`ConversionResult` whose SVG contains one labeled ``<g>``
            layer per detected color.
        """
        opts = BitmapOptions.model_validate(options or {})
        algorithm = get_algorithm(opts.algorithm)

        max_dim = 128 if fast else opts.max_dimension_px
        n_init = 1 if fast else 10
        image = self._load_rgb(data)
        image = self._fit_within(image, max_dim)
        labels, palette = self._quantize(image, opts.num_colors, n_init=n_init)

        height, width = labels.shape
        warnings: list[str] = []
        groups: list[str] = []

        for cluster in self._layer_order(labels, palette):
            rgb = palette[cluster]
            luminance = float(np.dot(rgb / 255.0, _REC709))
            if opts.drop_background and luminance >= opts.background_luminance:
                continue
            mask = labels == cluster
            color_hex = "#{:02x}{:02x}{:02x}".format(*rgb.astype(int))
            label = f"color-{color_hex.lstrip('#')}"
            groups.append(
                algorithm.render_layer(mask, color_hex, label, options=opts.algorithm_options)
            )

        if not groups:
            warnings.append("No drawable layers detected (image may be entirely background).")

        svg = self._wrap_svg(width, height, groups)
        return ConversionResult(svg=svg, source_mime="image/svg+xml", warnings=warnings)

    @staticmethod
    def _load_rgb(data: bytes) -> Image.Image:
        """Decode image bytes into an RGB Pillow image."""
        return Image.open(io.BytesIO(data)).convert("RGB")

    @staticmethod
    def _fit_within(image: Image.Image, max_dim: int) -> Image.Image:
        """Downscale the image so its longest side is at most ``max_dim``."""
        longest = max(image.width, image.height)
        if longest <= max_dim:
            return image
        scale = max_dim / longest
        size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
        return image.resize(size, Image.Resampling.LANCZOS)

    @staticmethod
    def _quantize(
        image: Image.Image, num_colors: int, *, n_init: int = 10
    ) -> tuple[NDArray[np.intp], NDArray[np.uint8]]:
        """Cluster pixels into ``num_colors`` colors via k-means.

        Args:
            n_init: Number of k-means restarts. The preview path drops this to
                1 to avoid paying ~10× the runtime for a frame the user will
                replace seconds later.

        Returns:
            A ``(labels, palette)`` pair: ``labels`` is a (height, width) array
            of cluster indices, ``palette`` is a (k, 3) array of RGB centroids.
        """
        arr = np.asarray(image, dtype=np.float64).reshape(-1, 3)
        k = min(num_colors, max(1, np.unique(arr, axis=0).shape[0]))
        model = KMeans(n_clusters=k, n_init=n_init, random_state=0)
        flat_labels = model.fit_predict(arr)
        palette = model.cluster_centers_.round().astype(np.uint8)
        labels = flat_labels.reshape(image.height, image.width).astype(np.intp)
        return labels, palette

    @staticmethod
    def _layer_order(labels: NDArray[np.intp], palette: NDArray[np.uint8]) -> list[int]:
        """Order clusters from darkest to lightest centroid."""
        luminance = palette.astype(np.float64) @ _REC709 / 255.0
        return sorted(range(palette.shape[0]), key=lambda c: luminance[c])

    @staticmethod
    def _wrap_svg(width: int, height: int, groups: list[str]) -> str:
        """Assemble layer groups into a complete SVG document."""
        header = (
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
            f'viewBox="0 0 {width} {height}" width="{width}" height="{height}">'
        )
        return header + "".join(groups) + "</svg>"

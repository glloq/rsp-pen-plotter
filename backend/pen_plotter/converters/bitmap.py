"""Bitmap converter.

Loads raster images (PNG/JPG/TIFF/WebP, plus HEIC/HEIF), separates them into a
small set of colors via k-means, and renders each color region to an SVG layer
using a selectable raster algorithm.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any, ClassVar, Literal

import numpy as np
import pillow_heif
from numpy.typing import NDArray
from PIL import Image
from pydantic import BaseModel, Field

from pen_plotter.converters import segmentation
from pen_plotter.converters.algorithms import get_algorithm
from pen_plotter.converters.base import ConversionResult, Converter

pillow_heif.register_heif_opener()

_REC709 = np.array([0.2126, 0.7152, 0.0722])

SegmentationMethod = Literal["kmeans", "luminance_bands", "thresholds", "fixed_palette"]


@dataclass
class SegmentationResult:
    """The parts of a bitmap conversion that survive between requests.

    Stored in the ``/rerender`` cache so the operator can swap a single
    layer's rendering algorithm without paying for the k-means pass again
    (which is the slow step on a Pi).
    """

    labels: NDArray[np.intp]
    palette: NDArray[np.uint8]
    width: int
    height: int


class BitmapOptions(BaseModel):
    """Validated options accepted by :class:`BitmapConverter`."""

    algorithm: str = "direct"
    num_colors: int = Field(default=4, ge=1, le=32)
    max_dimension_px: int = Field(default=800, ge=16, le=4096)
    drop_background: bool = True
    background_luminance: float = Field(default=0.92, ge=0.0, le=1.0)
    algorithm_options: dict[str, Any] = Field(default_factory=dict)
    # Segmentation ("decoupage") configuration. ``kmeans`` keeps the prior
    # behaviour; the other methods plug in via
    # :mod:`pen_plotter.converters.segmentation`. Method-specific arguments
    # ride along in ``segmentation_options`` (e.g. ``num_bands``,
    # ``levels``, ``palette``) — see that module's docstrings.
    segmentation_method: SegmentationMethod = "kmeans"
    segmentation_options: dict[str, Any] = Field(default_factory=dict)
    # Post-processing applied after segmentation regardless of method.
    # ``min_region_pixels`` reassigns connected components below the
    # threshold to their dominant neighbour (anti-noise). ``merge_delta_e``
    # collapses palette entries closer than ``threshold`` in CIE Lab.
    min_region_pixels: int = Field(default=0, ge=0)
    merge_delta_e: float = Field(default=0.0, ge=0.0)
    # Per-band rendering recipes for mono shaded modes. When provided,
    # ``band_recipes[i]`` overrides the uniform ``algorithm`` /
    # ``algorithm_options`` for the i-th produced layer (ordered
    # darkest-first, matching the front-end's ``bandRecipe`` contract).
    # This lets ``/preview`` reflect the per-band variation that mono
    # master styles like Pencil / Halftone / Stippling apply
    # post-/upload via /rerender — without it, the live preview shows
    # only the uniform default and the operator only sees the real
    # result after Apply.
    band_recipes: list[dict[str, Any]] | None = None


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
        result, _seg = self.segment_and_render(data, options=options, fast=fast)
        return result

    def segment_and_render(
        self,
        data: bytes,
        *,
        options: dict[str, Any] | None = None,
        fast: bool = False,
    ) -> tuple[ConversionResult, SegmentationResult]:
        """Same as :meth:`convert` but also returns the segmentation result.

        Used by ``/upload`` to feed the ``/rerender`` cache so the operator
        can change a single layer's algorithm later without paying for the
        segmentation pass again.
        """
        opts = BitmapOptions.model_validate(options or {})
        # ``fast`` keeps the cheap k-means single restart (n_init=1)
        # but no longer overrides ``max_dimension_px``: the operator
        # explicitly picks the segmentation resolution in the editor
        # and expects the live /preview to reflect that choice. Capping
        # to 128 made the detail slider a no-op for the UI even though
        # the backend would honour it at /upload — confusing.
        max_dim = opts.max_dimension_px
        n_init = 1 if fast else 10
        image = self._load_rgb(data)
        image = self._fit_within(image, max_dim)
        labels, palette = self._segment(image, opts, n_init=n_init)
        if opts.min_region_pixels > 0:
            labels = segmentation.drop_small_regions(labels, opts.min_region_pixels)
        if opts.merge_delta_e > 0:
            labels, palette = segmentation.merge_similar_colours(
                labels, palette, opts.merge_delta_e
            )
        height, width = labels.shape
        seg = SegmentationResult(labels=labels, palette=palette, width=width, height=height)
        # Translate ``band_recipes`` (positional, darkest-first) into the
        # label-keyed ``per_layer_overrides`` ``render_from_segmentation``
        # already understands. The frontend builds the recipe list from
        # the master style's ``bandRecipe(i, total)`` so the live preview
        # reflects per-band variation (Pencil's rotating crosshatch
        # angles, Halftone's growing cell size, etc.) without needing a
        # /rerender round-trip after upload.
        overrides: dict[str, dict[str, Any]] | None = None
        if opts.band_recipes:
            overrides = {}
            ordered_clusters = list(BitmapConverter._layer_order(labels, palette))
            # Replicate the drop_background filter ``render_from_segmentation``
            # applies so band_recipes[i] aligns with the i-th *rendered*
            # layer the operator sees, not the i-th raw segmentation cluster.
            rendered_clusters = [
                c for c in ordered_clusters
                if not (
                    opts.drop_background
                    and float(np.dot(palette[c] / 255.0, _REC709)) >= opts.background_luminance
                )
            ]
            for i, cluster in enumerate(rendered_clusters):
                if i >= len(opts.band_recipes):
                    break
                recipe = opts.band_recipes[i] or {}
                color_hex = "#{:02x}{:02x}{:02x}".format(*palette[cluster].astype(int))
                label = f"color-{color_hex.lstrip('#')}"
                overrides[label] = recipe
        svg, warnings = BitmapConverter.render_from_segmentation(
            seg, opts, per_layer_overrides=overrides,
        )
        return (
            ConversionResult(svg=svg, source_mime="image/svg+xml", warnings=warnings),
            seg,
        )

    @classmethod
    def render_from_segmentation(
        cls,
        seg: SegmentationResult,
        opts: BitmapOptions,
        *,
        per_layer_overrides: dict[str, dict[str, Any]] | None = None,
    ) -> tuple[str, list[str]]:
        """Re-run only the rendering step against an existing segmentation.

        ``per_layer_overrides`` maps a layer label (``f"color-{hex}"``) to a
        dict with ``algorithm`` and/or ``algorithm_options`` keys, swapping
        in a different algorithm just for that layer. Layers without an
        override fall back to ``opts.algorithm`` + ``opts.algorithm_options``.
        """
        overrides = per_layer_overrides or {}
        warnings: list[str] = []
        groups: list[str] = []
        for cluster in cls._layer_order(seg.labels, seg.palette):
            rgb = seg.palette[cluster]
            luminance = float(np.dot(rgb / 255.0, _REC709))
            if opts.drop_background and luminance >= opts.background_luminance:
                continue
            mask = seg.labels == cluster
            color_hex = "#{:02x}{:02x}{:02x}".format(*rgb.astype(int))
            label = f"color-{color_hex.lstrip('#')}"
            override = overrides.get(label, {})
            # Multi-pass: stack several algorithms in the same labeled
            # group so the layer is drawn with multiple visual effects
            # (e.g. contours + crosshatch fill) using a single ink. Each
            # pass renders against the same mask; their inner fragments
            # are wrapped in one outer ``<g inkscape:label="color-…">`` so
            # extract_layers still reports one layer per colour.
            passes = override.get("passes") or []
            if passes:
                groups.append(
                    cls._render_passes(mask, color_hex, label, passes, opts, warnings)
                )
                continue
            algo_name = override.get("algorithm") or opts.algorithm
            algo_options = override.get("algorithm_options") or opts.algorithm_options
            try:
                algorithm = get_algorithm(algo_name)
            except KeyError:
                # Unknown override → fall back to the default rather than
                # 500'ing on the operator. Surface it as a warning instead.
                warnings.append(
                    f"Layer {label}: unknown algorithm {algo_name!r}, using {opts.algorithm!r}."
                )
                algorithm = get_algorithm(opts.algorithm)
            groups.append(algorithm.render_layer(mask, color_hex, label, options=algo_options))
        if not groups:
            warnings.append("No drawable layers detected (image may be entirely background).")
        return cls._wrap_svg(seg.width, seg.height, groups), warnings

    @classmethod
    def _render_passes(
        cls,
        mask: NDArray[np.bool_],
        color_hex: str,
        label: str,
        passes: list[dict[str, Any]],
        opts: BitmapOptions,
        warnings: list[str],
    ) -> str:
        """Render a stack of passes against the same mask, wrapped in one labeled group.

        Each pass produces its own ``<g inkscape:label="…">…</g>`` fragment;
        we strip those inner labels (they'd otherwise confuse downstream
        consumers that expect one labeled group per colour) and re-nest the
        bodies under a single outer group carrying the colour label.
        """
        from xml.sax.saxutils import quoteattr

        fragments: list[str] = []
        for idx, raw in enumerate(passes):
            algo_name = (raw.get("algorithm") if isinstance(raw, dict) else None) or opts.algorithm
            algo_options = (raw.get("algorithm_options") if isinstance(raw, dict) else None) or {}
            try:
                algorithm = get_algorithm(algo_name)
            except KeyError:
                warnings.append(
                    f"Layer {label} pass {idx}: unknown algorithm {algo_name!r}, "
                    f"falling back to {opts.algorithm!r}."
                )
                algorithm = get_algorithm(opts.algorithm)
            pass_label = f"{label}-pass-{idx}"
            fragments.append(
                algorithm.render_layer(mask, color_hex, pass_label, options=algo_options)
            )
        if not fragments:
            return f"<g inkscape:label={quoteattr(label)}></g>"
        return (
            f"<g inkscape:label={quoteattr(label)}>" + "".join(fragments) + "</g>"
        )

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
    def _segment(
        image: Image.Image, opts: BitmapOptions, *, n_init: int = 10
    ) -> tuple[NDArray[np.intp], NDArray[np.uint8]]:
        """Dispatch to the segmentation method selected in ``opts``.

        Args:
            n_init: K-means restarts. Only consumed when ``segmentation_method``
                is ``kmeans``; the preview path drops it to 1 for speed.

        Returns:
            ``(labels, palette)``: ``labels`` is a (height, width) array of
            cluster indices, ``palette`` is a (k, 3) array of RGB centroids.
        """
        seg = opts.segmentation_options
        if opts.segmentation_method == "luminance_bands":
            num_bands = int(seg.get("num_bands", opts.num_colors))
            return segmentation.luminance_bands(image, num_bands=num_bands)
        if opts.segmentation_method == "thresholds":
            levels = seg.get("levels", [])
            if not isinstance(levels, list):
                raise ValueError("segmentation_options.levels must be a list of floats")
            return segmentation.thresholds(image, levels=levels)
        if opts.segmentation_method == "fixed_palette":
            palette_hex = seg.get("palette", [])
            if not isinstance(palette_hex, list) or not palette_hex:
                raise ValueError(
                    "segmentation_options.palette must be a non-empty list of hex colours"
                )
            return segmentation.fixed_palette(image, palette_hex=palette_hex)
        return segmentation.kmeans(image, num_colors=opts.num_colors, n_init=n_init)

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

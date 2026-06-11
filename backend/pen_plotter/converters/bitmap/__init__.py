"""Bitmap converter.

Loads raster images (PNG/JPG/TIFF/WebP, plus HEIC/HEIF), separates them into a
small set of colors via k-means (or one of the other segmentation strategies
in :mod:`pen_plotter.converters.segmentation`), and renders each color region
to an SVG layer using a selectable raster algorithm.

Since L9 the implementation lives in sub-modules:

* :mod:`.preprocess` — :class:`PreprocessOptions` + the photo-editor
  pipeline (geometry / colour space / tonal / spatial / dither) plus
  the ``MAX_PIXELS`` bomb guard around image decoding.
* :mod:`.segment` — segmentation strategy dispatch + the Rec.709
  luminance weighting both segmentation and rendering rely on.
* :mod:`.cache` — :class:`SegmentationResult` (the cacheable
  artefact ``/rerender`` keeps between requests).
* :mod:`.render` — :func:`render_from_segmentation` + the picklable
  per-layer worker functions :class:`ProcessPoolExecutor` dispatches.

This module hosts the :class:`BitmapOptions` schema (the wire shape
shared with every endpoint) and the :class:`BitmapConverter` façade
that orchestrates load → preprocess → segment → render. Existing
imports such as ``from pen_plotter.converters.bitmap import
BitmapConverter, BitmapOptions, SegmentationResult, PreprocessOptions``
keep working unchanged thanks to the re-exports below.
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, Field

from pen_plotter.converters.base import ConversionResult, Converter

from .cache import SegmentationResult
from .preprocess import (
    MAX_PIXELS,
    PreprocessOptions,
    Rotation,
    _floyd_steinberg,
    apply_dither,
    apply_preprocess,
    fit_within,
    is_preprocess_neutral,
    load_rgb,
)
from .render import layer_order, render_from_segmentation
from .segment import _REC709, SegmentationMethod, segment_image

__all__ = [
    "BitmapConverter",
    "BitmapOptions",
    "LINE_ART_MIN_DIMENSION_PX",
    "PreprocessOptions",
    "Rotation",
    "SegmentationMethod",
    "SegmentationResult",
    "pick_effective_segmentation",
]


# Segmentation methods the operator has clearly tuned by hand — they
# encode intentional choices (a specific palette, manually-picked
# luminance breakpoints, an explicit binary threshold), so the
# auto-switch leaves them alone. Everything else (``kmeans``,
# ``kmeans_lab``, ``luminance_bands``) is treated as default-ish and
# eligible for the line-art override.
_EXPLICIT_SEGMENTATION_METHODS: frozenset[str] = frozenset(
    {"otsu", "fixed_palette", "palette_dither", "thresholds"}
)


# Minimum segmentation-canvas size when the line-art auto-switch fires.
# Matches the editor's "High" detail tier — empirically the threshold
# where 1-2 px lines on a 3000-wide technical drawing JPG stop being
# smoothed away by the downscale, and Otsu / skeletonisation stay fast
# enough on a Pi-class device. Operators who want even more fidelity
# can pick Max (4800) / Ultra (8192) in the SVG tab; the floor only
# raises, never lowers.
LINE_ART_MIN_DIMENSION_PX = 2400


def pick_effective_segmentation(
    *,
    algorithm: str,
    mono_ink_color: str | None,
    segmentation_method: SegmentationMethod,
) -> SegmentationMethod:
    """Resolve the effective segmentation for a given option set.

    Auto-picks Otsu binary segmentation when the operator combines a
    **line-extraction algorithm** (every member of the
    ``algorithms._KINDS['lines']`` family — centerline, edges,
    contours, lowpoly, grid, brick, truchet) with **monochrome ink
    mode**. The frontend's monochrome master styles default to
    ``luminance_bands`` with ``num_bands=1`` — every pixel ends up in
    a single mid-grey cluster, the centerline of which is a degenerate
    trace through the canvas centre. K-means scatters anti-aliased
    fringes across 3 grey clusters and gets nothing better. Otsu
    collapses every "dark enough" pixel into one solid mask of the
    actual ink so the line trace runs on a faithful binary image and
    the pen draws every stroke exactly once.

    Explicit picks of ``otsu`` / ``fixed_palette`` / ``palette_dither``
    / ``thresholds`` encode an intentional tuning we shouldn't
    second-guess and are returned unchanged.

    Shared between the upload path (``segment_and_render``) and the
    /rerender path (``api.rerender``) so per-layer algorithm overrides
    that change a layer to a line-extraction algorithm trigger the
    same fix instead of silently re-using a stale kmeans segmentation.
    """
    # Late import to keep the algorithms module off this file's
    # top-level import graph (the algorithm modules import from
    # ``converters.algorithms.base`` which has its own dependencies).
    from pen_plotter.converters.algorithms import _KINDS  # noqa: PLC0415

    if mono_ink_color is None:
        return segmentation_method
    if segmentation_method in _EXPLICIT_SEGMENTATION_METHODS:
        return segmentation_method
    if _KINDS.get(algorithm) != "lines":
        return segmentation_method
    return "otsu"


class BitmapOptions(BaseModel):
    """Validated options accepted by :class:`BitmapConverter`."""

    algorithm: str = "direct"
    num_colors: int = Field(default=4, ge=1, le=32)
    # Upper bound bumped from 4096 to 8192 so the editor's "Ultra"
    # detail tier (4800px) and any future "Native" tier have headroom.
    # Higher canvas resolution preserves fine features in text, table
    # grids and dense schematics that the previous 4096 cap was
    # silently smoothing away — the operator reported the picker
    # "doing nothing" past the Max tier because the backend was capping
    # at half of what the UI now offers.
    max_dimension_px: int = Field(default=800, ge=16, le=8192)
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
    # Force every rendered ``<g>`` to use this single ink colour for its
    # ``stroke=`` attribute, regardless of the cluster's source-image
    # palette RGB. Set by the frontend when ``_printMode === 'monochrome'``
    # so the live preview reflects single-pen reality (gray levels come
    # from algorithm density / spacing / angle variation, not from
    # multiple ink colours). ``None`` keeps the legacy per-cluster colour
    # behaviour for multicolour mode. ``color_hex`` continues to drive the
    # per-layer label so ``band_recipes`` indexing and ``extract_layers``
    # round-trip identically; only the visual stroke colour changes.
    mono_ink_color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    # Photo-editor style adjustments applied to the loaded RGB image
    # before the downscale + segmentation pass. Defaults are neutral so
    # the field is safe to omit; the editor's "Image" tab writes the
    # operator's tweaks here. See :class:`PreprocessOptions`.
    preprocess: PreprocessOptions = Field(default_factory=PreprocessOptions)
    # Physical footprint (mm) the rendered drawing will occupy on the
    # sheet. Drives the millimetre → raster-pixel conversion of length
    # options (``spacing_mm``, ``cell_size_mm``, …, see
    # ``convert_mm_options``) so the on-paper pitch the operator dialled
    # in survives across page formats from the very first render —
    # /upload and /preview pass it here, /rerender can override it
    # per-request when the placement was resized since. ``None`` falls
    # back to the A4 reference scale.
    target_width_mm: float | None = Field(default=None, gt=0)
    target_height_mm: float | None = Field(default=None, gt=0)


class BitmapConverter(Converter):
    """Separates a raster image into per-color SVG layers.

    Thin façade since L9: the implementation is decomposed into the
    ``preprocess`` / ``segment`` / ``render`` / ``cache`` sub-modules
    of this package. The class stays as the public entry point so
    every existing caller — ``api/preview``, ``api/rerender``,
    ``application/file_library``, ``converters/pipeline``,
    ``converters/defaults`` and the test suite — keeps its import
    surface unchanged.
    """

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

    # Class attribute re-exported from ``preprocess`` so the existing
    # ``BitmapConverter.MAX_PIXELS`` access pattern in tests keeps
    # working without a churn-PR.
    MAX_PIXELS: ClassVar[int] = MAX_PIXELS

    # Static-method aliases for the preprocess helpers — tests reach
    # in via ``BitmapConverter._preprocess`` and
    # ``BitmapConverter._load_rgb``. Pre-L9 these were static methods
    # on the class; keeping the staticmethod shape avoids churning
    # ``test_bitmap`` and ``test_security_hardening`` just to move
    # one dot. New code should import the module-level helpers
    # directly from ``pen_plotter.converters.bitmap.preprocess``.
    _load_rgb = staticmethod(load_rgb)
    _preprocess = staticmethod(apply_preprocess)
    _is_preprocess_neutral = staticmethod(is_preprocess_neutral)
    _floyd_steinberg = staticmethod(_floyd_steinberg)
    _fit_within = staticmethod(fit_within)

    def convert(
        self,
        data: bytes,
        *,
        options: dict[str, Any] | None = None,
        fast: bool = False,
        n_workers: int = 1,
    ) -> ConversionResult:
        """Convert image bytes into a layered SVG pivot document.

        Args:
            data: Raw image file bytes.
            options: Optional parameters validated against :class:`BitmapOptions`.
            fast: When ``True``, force ``n_init=1`` for the k-means restart
                (single initialisation instead of 10). ``max_dimension_px`` is
                honoured as the operator set it — the ``/preview`` endpoint
                pairs this flag with a tier-specific resolution cap of its own
                rather than overriding the option here.
            n_workers: Number of OS processes to use for per-layer rendering.
                ``1`` (default) keeps everything in-process. Higher values
                dispatch each colour layer to a worker via a forkserver
                ``ProcessPoolExecutor`` — useful on multi-core Pi 4/5 when
                the chosen algorithm is CPU-bound (TSP, 2-opt, streamlines).

        Returns:
            A :class:`ConversionResult` whose SVG contains one labeled ``<g>``
            layer per detected color.
        """
        result, _seg = self.segment_and_render(
            data, options=options, fast=fast, n_workers=n_workers
        )
        return result

    def segment_and_render(
        self,
        data: bytes,
        *,
        options: dict[str, Any] | None = None,
        fast: bool = False,
        n_workers: int = 1,
        progress_callback: Any = None,
    ) -> tuple[ConversionResult, SegmentationResult]:
        """Same as :meth:`convert` but also returns the segmentation result.

        Used by ``/upload`` to feed the ``/rerender`` cache so the operator
        can change a single layer's algorithm later without paying for the
        segmentation pass again.
        """
        from pen_plotter.converters import segmentation as _seg_mod
        from pen_plotter.observability import traced_span

        opts = BitmapOptions.model_validate(options or {})
        # ``fast`` keeps the cheap k-means single restart (n_init=1)
        # but no longer overrides ``max_dimension_px``: the operator
        # explicitly picks the segmentation resolution in the editor
        # and expects the live /preview to reflect that choice. Capping
        # to 128 made the detail slider a no-op for the UI even though
        # the backend would honour it at /upload — confusing.
        max_dim = opts.max_dimension_px
        n_init = 1 if fast else 10
        effective_method = pick_effective_segmentation(
            algorithm=opts.algorithm,
            mono_ink_color=opts.mono_ink_color,
            segmentation_method=opts.segmentation_method,
        )
        # When the line-art auto-switch fires, the operator's intent is
        # "faithfully reproduce every stroke" — and the biggest detail
        # killer is the default 800 px segmentation canvas, which forces
        # a 3000-wide technical-drawing JPG down to ~26 % scale before
        # any pixel sees Otsu. Lift the floor to the High tier (2400 px)
        # — measured ~3× more traced points on a typical mechanical
        # drawing without crossing the threshold where Otsu /
        # skeletonisation get expensive on a Pi. Only raises, so an
        # operator who explicitly picked Max (4800) / Ultra (8192) is
        # respected. Surfaced as a warning so the editor knows the
        # canvas was bumped.
        line_art_warnings: list[str] = []
        if effective_method == "otsu" and max_dim < LINE_ART_MIN_DIMENSION_PX:
            line_art_warnings.append(
                f"Detail tier lifted to {LINE_ART_MIN_DIMENSION_PX} px "
                f"(was {max_dim}) to preserve fine line work — pick a "
                "higher tier in the SVG tab for even more fidelity."
            )
            max_dim = LINE_ART_MIN_DIMENSION_PX
        with traced_span(
            "pipeline.bitmap.load",
            size_bytes=len(data),
            max_dim_px=max_dim,
        ):
            image = load_rgb(data)
        with traced_span("pipeline.bitmap.preprocess"):
            image = apply_preprocess(image, opts.preprocess)
        with traced_span("pipeline.bitmap.fit_within", max_dim_px=max_dim):
            image = fit_within(image, max_dim)
        # Dither *after* the downscale: error diffusion at segmentation
        # resolution is fast, and a pre-downscale dither would be
        # LANCZOS-averaged back to flat grey anyway.
        if opts.preprocess.dither_levels >= 2:
            with traced_span(
                "pipeline.bitmap.dither",
                dither_levels=opts.preprocess.dither_levels,
            ):
                image = apply_dither(image, opts.preprocess)
        with traced_span(
            "pipeline.bitmap.segment",
            method=effective_method,
            num_colors=opts.num_colors,
            n_init=n_init,
        ):
            labels, palette = segment_image(
                image,
                method=effective_method,
                options=opts.segmentation_options,
                num_colors=opts.num_colors,
                drop_background=opts.drop_background,
                background_luminance=opts.background_luminance,
                n_init=n_init,
            )
        # Collapse palette entries with identical RGB before anything keys
        # on the per-cluster hex: duplicates (repeated entries in a manual
        # fixed palette, twin installed pens, k-means centroids rounding to
        # the same triplet) would otherwise emit two layers with the same
        # ``color-{hex}`` label and collide in every label-keyed map
        # (band-recipe overrides, ink/width maps, frontend layer ids).
        labels, palette = _seg_mod.merge_duplicate_colours(labels, palette)
        if opts.min_region_pixels > 0:
            with traced_span(
                "pipeline.bitmap.drop_small_regions",
                min_region_pixels=opts.min_region_pixels,
            ):
                labels = _seg_mod.drop_small_regions(labels, opts.min_region_pixels)
        if opts.merge_delta_e > 0:
            with traced_span(
                "pipeline.bitmap.merge_similar_colours",
                merge_delta_e=opts.merge_delta_e,
            ):
                labels, palette = _seg_mod.merge_similar_colours(
                    labels, palette, opts.merge_delta_e
                )
        height, width = labels.shape
        # Per-pixel luminance of the (preprocessed, downscaled) image — the
        # tonal-spiral renderer samples it to modulate the wobble per pixel.
        # Computed from the same ``image`` segmentation saw so coordinates
        # line up with ``labels``.
        import numpy as _np

        lum_map = (_np.asarray(image, dtype=_np.float64)[..., :3] / 255.0) @ _REC709
        seg = SegmentationResult(
            labels=labels,
            palette=palette,
            width=width,
            height=height,
            luminance=lum_map,
        )
        # Translate ``band_recipes`` (positional, darkest-first) into the
        # label-keyed ``per_layer_overrides`` ``render_from_segmentation``
        # already understands. The frontend builds the recipe list from
        # the master style's ``bandRecipe(i, total)`` so the live preview
        # reflects per-band variation (Pencil's rotating crosshatch
        # angles, Halftone's growing cell size, etc.) without needing a
        # /rerender round-trip after upload.
        overrides: dict[str, dict[str, Any]] | None = None
        if opts.band_recipes:
            import numpy as np

            overrides = {}
            ordered_clusters = layer_order(labels, palette)
            # Replicate the drop_background filter ``render_from_segmentation``
            # applies so band_recipes[i] aligns with the i-th *rendered*
            # layer the operator sees, not the i-th raw segmentation cluster.
            rendered_clusters = [
                c
                for c in ordered_clusters
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
        svg, warnings = self.__class__.render_from_segmentation(
            seg,
            opts,
            per_layer_overrides=overrides,
            n_workers=n_workers,
            progress_callback=progress_callback,
        )
        return (
            ConversionResult(
                svg=svg,
                source_mime="image/svg+xml",
                warnings=[*line_art_warnings, *warnings],
            ),
            seg,
        )

    @classmethod
    def render_from_segmentation(
        cls,
        seg: SegmentationResult,
        opts: BitmapOptions,
        *,
        per_layer_overrides: dict[str, dict[str, Any]] | None = None,
        layer_stroke_widths: dict[str, float] | None = None,
        layer_ink_colors: dict[str, str] | None = None,
        px_per_mm: float | None = None,
        n_workers: int = 1,
        progress_callback: Any = None,
    ) -> tuple[str, list[str]]:
        """Re-run only the rendering step against an existing segmentation.

        Thin wrapper around :func:`render.render_from_segmentation`;
        unpacks the relevant fields of :class:`BitmapOptions` so the
        module function can keep a primitive signature.

        ``px_per_mm`` resolution order: the caller's explicit value (the
        /rerender request, whose placement may have been resized since
        upload) wins; otherwise the target footprint stored in ``opts``
        at /upload / /preview time; otherwise ``None`` (the module-level
        A4 reference fallback applies).
        """
        if px_per_mm is None and opts.target_width_mm and opts.target_height_mm:
            raster_h, raster_w = seg.labels.shape
            px_per_mm = max(raster_w, raster_h) / max(opts.target_width_mm, opts.target_height_mm)
        return render_from_segmentation(
            seg,
            algorithm=opts.algorithm,
            algorithm_options=opts.algorithm_options,
            mono_ink_color=opts.mono_ink_color,
            drop_background=opts.drop_background,
            background_luminance=opts.background_luminance,
            per_layer_overrides=per_layer_overrides,
            layer_stroke_widths=layer_stroke_widths,
            layer_ink_colors=layer_ink_colors,
            px_per_mm=px_per_mm,
            n_workers=n_workers,
            progress_callback=progress_callback,
        )

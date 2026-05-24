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
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from pydantic import BaseModel, Field, field_validator
from pydantic_core import PydanticUndefined

from pen_plotter.converters import segmentation
from pen_plotter.converters.algorithms import get_algorithm
from pen_plotter.converters.base import ConversionResult, Converter

pillow_heif.register_heif_opener()

_REC709 = np.array([0.2126, 0.7152, 0.0722])


def _palette_has_near_white(palette_hex: list[str], threshold: float) -> bool:
    """True if any entry's Rec.709 luminance reaches the drop threshold."""
    for entry in palette_hex:
        try:
            rgb = segmentation._hex_to_rgb(entry)
        except ValueError:
            continue
        if float(np.dot(np.array(rgb) / 255.0, _REC709)) >= threshold:
            return True
    return False


SegmentationMethod = Literal["kmeans", "luminance_bands", "thresholds", "fixed_palette"]
Rotation = Literal[0, 90, 180, 270]


class PreprocessOptions(BaseModel):
    """Image adjustments applied before downscale + segmentation.

    The editor's "Image" tab writes here. Every field defaults to a
    neutral value so omitting the block (older clients, missing in
    ``last_options``) is identical to running the converter unchanged.

    Order of application matches the order operators expect from a
    photo editor: geometry first (crop → rotate → flip), then colour
    space conversions (grayscale, invert), then tonal mapping
    (levels → gamma → brightness → contrast → saturation), then spatial
    filters (blur, sharpen), and finally the optional auto-contrast
    stretch which runs *last* so the operator's manual choices remain
    the dominant signal.
    """

    brightness: float = Field(default=0.0, ge=-1.0, le=1.0)
    contrast: float = Field(default=0.0, ge=-1.0, le=1.0)
    saturation: float = Field(default=1.0, ge=0.0, le=2.0)
    gamma: float = Field(default=1.0, gt=0.0, le=5.0)
    black_point: int = Field(default=0, ge=0, le=255)
    white_point: int = Field(default=255, ge=0, le=255)
    sharpen: float = Field(default=0.0, ge=0.0, le=2.0)
    blur_px: float = Field(default=0.0, ge=0.0, le=10.0)
    invert: bool = False
    grayscale: bool = False
    auto_contrast: bool = False
    rotate_deg: Rotation = 0
    flip_h: bool = False
    flip_v: bool = False
    # Normalised crop rectangle (x, y, width, height) in [0, 1]. ``None``
    # means no crop. Validated so x+w <= 1 and y+h <= 1 — otherwise the
    # PIL crop would silently clamp and the operator's rectangle wouldn't
    # match the preview.
    crop: tuple[float, float, float, float] | None = None

    @field_validator("crop")
    @classmethod
    def _crop_inside_unit(
        cls, value: tuple[float, float, float, float] | None
    ) -> tuple[float, float, float, float] | None:
        if value is None:
            return None
        x, y, w, h = value
        if w <= 0 or h <= 0:
            raise ValueError("crop width and height must be > 0")
        if x < 0 or y < 0 or x + w > 1.0001 or y + h > 1.0001:
            raise ValueError("crop must lie within the [0, 1] unit square")
        return value


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
    # Photo-editor style adjustments applied to the loaded RGB image
    # before the downscale + segmentation pass. Defaults are neutral so
    # the field is safe to omit; the editor's "Image" tab writes the
    # operator's tweaks here. See :class:`PreprocessOptions`.
    preprocess: PreprocessOptions = Field(default_factory=PreprocessOptions)


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
            fast: When ``True``, force ``n_init=1`` for the k-means restart
                (single initialisation instead of 10). ``max_dimension_px`` is
                honoured as the operator set it — the ``/preview`` endpoint
                pairs this flag with a tier-specific resolution cap of its own
                rather than overriding the option here.

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
        image = self._preprocess(image, opts.preprocess)
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
    def _is_preprocess_neutral(opts: PreprocessOptions) -> bool:
        """True when every preprocess field matches its model default.

        Iterates ``PreprocessOptions.model_fields`` so a freshly-added
        field automatically becomes part of the neutrality check. The
        only field without a usable model default is ``crop`` (the
        default is ``None``, which already round-trips correctly through
        the equality check below).
        """
        for name, field_info in PreprocessOptions.model_fields.items():
            default = field_info.default
            current = getattr(opts, name)
            # PydanticUndefined sentinels show up for required fields;
            # PreprocessOptions has none today, but guard so the helper
            # never crashes if one is added later.
            if default is PydanticUndefined:
                return False
            if current != default:
                return False
        return True

    @staticmethod
    def _preprocess(image: Image.Image, opts: PreprocessOptions) -> Image.Image:
        """Apply the operator's photo-editor adjustments to ``image``.

        Returns ``image`` unchanged when every field is neutral so the
        no-op path stays free of allocations / colour conversions.
        Neutrality is computed by comparing each field against the model
        default, so adding a new PreprocessOptions field doesn't require
        updating a hand-maintained checklist (regression risk that bit
        us when ``sharpen`` was added without flipping the gate).
        """
        if BitmapConverter._is_preprocess_neutral(opts):
            return image

        out = image
        if opts.crop is not None:
            x, y, w, h = opts.crop
            left = int(round(x * out.width))
            top = int(round(y * out.height))
            right = min(out.width, max(left + 1, int(round((x + w) * out.width))))
            bottom = min(out.height, max(top + 1, int(round((y + h) * out.height))))
            out = out.crop((left, top, right, bottom))
        if opts.rotate_deg:
            # ``expand=True`` so the canvas grows to fit the rotated image
            # instead of clipping the corners.
            out = out.rotate(-opts.rotate_deg, expand=True)
        if opts.flip_h:
            out = ImageOps.mirror(out)
        if opts.flip_v:
            out = ImageOps.flip(out)
        if opts.grayscale:
            # Keep the RGB mode so downstream segmentation, which expects
            # 3-channel input, doesn't need a special case.
            out = ImageOps.grayscale(out).convert("RGB")
        if opts.invert:
            out = ImageOps.invert(out)
        if opts.black_point > 0 or opts.white_point < 255:
            lo = min(opts.black_point, opts.white_point)
            hi = max(opts.black_point, opts.white_point)
            if hi - lo < 1:
                hi = min(255, lo + 1)
            scale = 255.0 / (hi - lo)
            arr = np.asarray(out, dtype=np.float32)
            arr = (arr - lo) * scale
            arr = np.clip(arr, 0.0, 255.0).astype(np.uint8)
            out = Image.fromarray(arr, mode="RGB")
        if opts.gamma != 1.0:
            inv_gamma = 1.0 / opts.gamma
            lut = (np.linspace(0.0, 1.0, 256) ** inv_gamma * 255.0).clip(0, 255).astype(np.uint8)
            # PIL's point() with a single LUT applies it to each channel.
            out = out.point(lut.tolist() * len(out.getbands()))
        if opts.brightness != 0.0:
            # Map -1..+1 onto a multiplicative factor 0..2 the way most
            # editors do (0 = black, 1 = identity, 2 = fully white).
            out = ImageEnhance.Brightness(out).enhance(1.0 + opts.brightness)
        if opts.contrast != 0.0:
            out = ImageEnhance.Contrast(out).enhance(1.0 + opts.contrast)
        if opts.saturation != 1.0:
            out = ImageEnhance.Color(out).enhance(opts.saturation)
        if opts.blur_px > 0:
            out = out.filter(ImageFilter.GaussianBlur(radius=opts.blur_px))
        if opts.sharpen > 0:
            # Map 0..2 onto unsharp mask percentage 0..200 — gives a
            # noticeable but bounded effect.
            out = out.filter(
                ImageFilter.UnsharpMask(radius=2.0, percent=int(opts.sharpen * 100), threshold=2)
            )
        if opts.auto_contrast:
            out = ImageOps.autocontrast(out, cutoff=1)
        return out

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
            # Preserve white background: when the operator's palette
            # follows their pen rack (typically no white pen), white
            # pixels would otherwise snap to the nearest pen colour
            # (light grey, pale yellow, …) and the resulting layer's
            # luminance is no longer above ``background_luminance`` —
            # so the drop_background filter downstream lets the wrong-
            # colour "background" through. Auto-inject ``#ffffff`` here
            # so white pixels snap to white instead, and the existing
            # filter at the render step drops that layer cleanly.
            if opts.drop_background and not _palette_has_near_white(
                palette_hex, opts.background_luminance
            ):
                palette_hex = ["#ffffff", *palette_hex]
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

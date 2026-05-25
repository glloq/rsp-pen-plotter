"""Pillow-side image adjustments applied before segmentation.

The editor's "Image" tab writes into :class:`PreprocessOptions`; this
module owns the validated schema and the photo-editor pipeline that
walks the operator's tweaks in the order they'd expect from a real
editor (geometry → colour space → tonal → spatial → auto-contrast →
dither).

Kept separate from segmentation / render so the pipeline can be
unit-tested without spinning up a converter, and so the
``MAX_PIXELS`` bomb guard around image decoding lives next to the
``load_rgb`` function that enforces it.
"""

from __future__ import annotations

import io
from typing import Literal

import numpy as np
import pillow_heif
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from pydantic import BaseModel, Field, field_validator
from pydantic_core import PydanticUndefined

pillow_heif.register_heif_opener()

Rotation = Literal[0, 90, 180, 270]

# Upper bound on the number of pixels in an uploaded raster image.
# 16 Mpx covers anything an A3 plotter could conceivably need
# (4000×4000 ≈ A3 at ~300 dpi) and keeps a single image well under
# 200 MB of RGB after decode — enough headroom for the algorithm
# passes without giving a malicious upload a way to OOM the Pi.
MAX_PIXELS = 16_000_000


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
    # Floyd-Steinberg error diffusion: snaps every pixel to the closest
    # entry in an N-level uniform grey ramp while distributing the
    # rounding error across neighbours. Produces the classic Atkinson /
    # newspaper-print stipple texture and pairs particularly well with
    # ``halftone`` / ``stippling`` algorithms downstream by giving them
    # well-separated dot positions instead of soft gradients to bucket.
    # ``0`` (default) skips dithering entirely. ``2`` is pure binary; 4-8
    # are the useful range for shaded mono modes.
    dither_levels: int = Field(default=0, ge=0, le=16)
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


def load_rgb(data: bytes) -> Image.Image:
    """Decode image bytes into an RGB Pillow image.

    Refuses images whose declared dimensions would exceed
    :data:`MAX_PIXELS` before the pixel data is actually materialised.
    Pillow exposes ``size`` after ``Image.open`` without reading the
    full bitmap, so the guard runs in O(header bytes) rather than
    O(width * height) — a 20 000×20 000 PNG bomb is rejected before
    any RAM is committed.
    """
    img = Image.open(io.BytesIO(data))
    width, height = img.size
    total = width * height
    if total > MAX_PIXELS:
        raise ValueError(
            f"Image is too large ({width}×{height} = {total:,} px); "
            f"max is {MAX_PIXELS:,} px. Resize the source "
            "or split it into smaller plots."
        )
    return img.convert("RGB")


def is_preprocess_neutral(opts: PreprocessOptions) -> bool:
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


def apply_preprocess(image: Image.Image, opts: PreprocessOptions) -> Image.Image:
    """Apply the operator's photo-editor adjustments to ``image``.

    Returns ``image`` unchanged when every field is neutral so the
    no-op path stays free of allocations / colour conversions.
    Neutrality is computed by comparing each field against the model
    default, so adding a new PreprocessOptions field doesn't require
    updating a hand-maintained checklist (regression risk that bit
    us when ``sharpen`` was added without flipping the gate).
    """
    if is_preprocess_neutral(opts):
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
    if opts.dither_levels >= 2:
        out = _floyd_steinberg(out, opts.dither_levels)
    return out


def _floyd_steinberg(image: Image.Image, levels: int) -> Image.Image:
    """Floyd-Steinberg error diffusion onto an N-level grey ramp.

    Quantises each pixel to the nearest of ``levels`` evenly-spaced
    grey values (0..255 inclusive) and pushes the rounding error to
    the 4 unprocessed neighbours via the standard Floyd-Steinberg
    kernel (7/16 right, 3/16 down-left, 5/16 down, 1/16 down-right).
    The output is RGB (grey replicated across channels) so the rest
    of the segmentation pipeline keeps its 3-channel assumption.
    """
    levels = max(2, levels)
    # Operate on a single greyscale plane — dithering each RGB
    # channel independently produces colour shimmer that no plotter
    # workflow benefits from, and the downstream segmentation snaps
    # back to a small palette anyway.
    grey = np.asarray(image.convert("L"), dtype=np.float32)
    h, w = grey.shape
    step = 255.0 / (levels - 1)
    for y in range(h):
        for x in range(w):
            old = grey[y, x]
            new = round(old / step) * step
            grey[y, x] = new
            err = old - new
            if x + 1 < w:
                grey[y, x + 1] += err * 7 / 16
            if y + 1 < h:
                if x > 0:
                    grey[y + 1, x - 1] += err * 3 / 16
                grey[y + 1, x] += err * 5 / 16
                if x + 1 < w:
                    grey[y + 1, x + 1] += err * 1 / 16
    clipped = np.clip(grey, 0.0, 255.0).astype(np.uint8)
    rgb = np.stack([clipped, clipped, clipped], axis=-1)
    return Image.fromarray(rgb, mode="RGB")


def fit_within(image: Image.Image, max_dim: int) -> Image.Image:
    """Downscale the image so its longest side is at most ``max_dim``."""
    longest = max(image.width, image.height)
    if longest <= max_dim:
        return image
    scale = max_dim / longest
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    return image.resize(size, Image.Resampling.LANCZOS)

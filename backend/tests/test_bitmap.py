import io
import shutil

import numpy as np
import pytest
from PIL import Image

from pen_plotter.converters.algorithms import available_algorithms, get_algorithm
from pen_plotter.converters.bitmap import BitmapConverter, PreprocessOptions

needs_potrace = pytest.mark.skipif(
    shutil.which("potrace") is None, reason="potrace binary not installed"
)


def _square_mask() -> np.ndarray:
    mask = np.zeros((40, 40), dtype=bool)
    mask[10:30, 10:30] = True
    return mask


def test_registered_algorithm_names() -> None:
    names = {algo.name for algo in available_algorithms()}
    # The original trio plus the 2024 expansion (crosshatch/contours/edges/
    # spiral/scanlines/tsp). The exhaustive list lives in
    # ``test_new_algorithms.test_registry_lists_all_nine_algorithms`` — this
    # assertion just guards the legacy set so old callers keep finding them.
    assert names >= {"direct", "halftone", "stippling"}


def test_get_unknown_algorithm_raises() -> None:
    with pytest.raises(KeyError):
        get_algorithm("nope")


def test_halftone_emits_dots_inside_region() -> None:
    group = get_algorithm("halftone").render_layer(_square_mask(), "#ff0000", "red")
    assert 'inkscape:label="red"' in group
    assert group.count("<circle") > 0


def test_halftone_angle_zero_matches_unrotated_default() -> None:
    """An explicit ``angle_deg=0`` reproduces the legacy axis-aligned grid."""
    algo = get_algorithm("halftone")
    mask = _square_mask()
    default = algo.render_layer(mask, "#ff0000", "red")
    explicit_zero = algo.render_layer(mask, "#ff0000", "red", options={"angle_deg": 0})
    # 180° is the same screen as 0° (dot grid symmetry).
    flipped = algo.render_layer(mask, "#ff0000", "red", options={"angle_deg": 180})
    assert default == explicit_zero == flipped


def test_halftone_rotated_screen_differs_but_still_fills() -> None:
    """A rotated screen turns the dot lattice yet still covers the region."""
    algo = get_algorithm("halftone")
    mask = _square_mask()
    flat = algo.render_layer(mask, "#ff0000", "r", options={"cell_size_px": 5})
    rot = algo.render_layer(mask, "#ff0000", "r", options={"cell_size_px": 5, "angle_deg": 45})
    assert flat != rot
    assert rot.count("<circle") > 0


def test_halftone_rotated_empty_mask_is_empty() -> None:
    empty = np.zeros((24, 24), dtype=bool)
    group = get_algorithm("halftone").render_layer(empty, "#000000", "k", options={"angle_deg": 30})
    assert "<circle" not in group


def test_stippling_is_deterministic() -> None:
    algo = get_algorithm("stippling")
    a = algo.render_layer(_square_mask(), "#ff0000", "red", options={"density": 0.1, "seed": 7})
    b = algo.render_layer(_square_mask(), "#ff0000", "red", options={"density": 0.1, "seed": 7})
    assert a == b
    assert a.count("<circle") > 0


def test_empty_mask_yields_empty_group() -> None:
    empty = np.zeros((20, 20), dtype=bool)
    group = get_algorithm("halftone").render_layer(empty, "#000000", "k")
    assert "<circle" not in group


@needs_potrace
def test_direct_traces_region_to_path() -> None:
    group = get_algorithm("direct").render_layer(_square_mask(), "#ff0000", "red")
    assert "<path" in group
    assert 'fill="#ff0000"' in group
    assert 'inkscape:label="red"' in group


@needs_potrace
def test_bitmap_converter_produces_layered_svg(two_color_png: bytes) -> None:
    result = BitmapConverter().convert(two_color_png, options={"algorithm": "direct"})
    assert result.source_mime == "image/svg+xml"
    assert result.svg.startswith("<svg")
    # White background dropped; the red square remains as one layer.
    assert result.svg.count("<g ") == 1
    assert "ff0000" in result.svg.lower() or "dc1414" in result.svg.lower()


def test_bitmap_converter_halftone_no_potrace_needed(two_color_png: bytes) -> None:
    result = BitmapConverter().convert(
        two_color_png, options={"algorithm": "halftone", "num_colors": 2}
    )
    assert "<circle" in result.svg


def test_bitmap_converter_rejects_unknown_algorithm(two_color_png: bytes) -> None:
    with pytest.raises(KeyError):
        BitmapConverter().convert(two_color_png, options={"algorithm": "bogus"})


# --- Preprocess pipeline ---------------------------------------------------


def _gradient_png() -> bytes:
    """50x50 horizontal grayscale gradient — useful for tonal-mapping checks."""
    arr = np.tile(np.linspace(0, 255, 50, dtype=np.uint8), (50, 1))
    rgb = np.stack([arr, arr, arr], axis=-1)
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="PNG")
    return buf.getvalue()


def _decode_png(data: bytes) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))


def test_preprocess_neutral_is_identity() -> None:
    img = Image.fromarray(_decode_png(_gradient_png()))
    out = BitmapConverter._preprocess(img, PreprocessOptions())
    # Neutral options should bypass every filter — same object handed back.
    assert out is img


def test_preprocess_brightness_pushes_to_white() -> None:
    img = Image.fromarray(_decode_png(_gradient_png()))
    out = BitmapConverter._preprocess(img, PreprocessOptions(brightness=1.0))
    arr = np.asarray(out)
    # +1.0 brightness uses an enhance factor of 2 → mid-gray and above
    # clip to 255; only the dark left edge stays below.
    assert arr.max() == 255
    assert int(arr[0, 25, 0]) >= 200
    assert int(arr[0, 0, 0]) == 0  # pure black is unaffected by multiplicative gain


def test_preprocess_invert_swaps_extremes() -> None:
    img = Image.fromarray(_decode_png(_gradient_png()))
    inverted = BitmapConverter._preprocess(img, PreprocessOptions(invert=True))
    arr = np.asarray(inverted)
    # The gradient went 0..255 left→right; after invert it goes 255..0.
    assert arr[0, 0, 0] > 250
    assert arr[0, -1, 0] < 5


def test_preprocess_crop_returns_expected_size() -> None:
    img = Image.fromarray(_decode_png(_gradient_png()))
    out = BitmapConverter._preprocess(img, PreprocessOptions(crop=(0.25, 0.0, 0.5, 1.0)))
    # Cropped width is roughly half the original (±1 for rounding);
    # height untouched.
    assert 24 <= out.width <= 26
    assert out.height == 50


def test_preprocess_rotate_swaps_dimensions() -> None:
    img = Image.fromarray(np.zeros((20, 40, 3), dtype=np.uint8))
    out = BitmapConverter._preprocess(img, PreprocessOptions(rotate_deg=90))
    assert (out.width, out.height) == (20, 40)


def test_preprocess_grayscale_collapses_channels() -> None:
    arr = np.zeros((10, 10, 3), dtype=np.uint8)
    arr[..., 0] = 200  # pure red
    img = Image.fromarray(arr)
    out = BitmapConverter._preprocess(img, PreprocessOptions(grayscale=True))
    pixels = np.asarray(out)
    # After grayscale collapse the three channels must be equal.
    assert np.all(pixels[..., 0] == pixels[..., 1])
    assert np.all(pixels[..., 1] == pixels[..., 2])


def test_preprocess_levels_stretch() -> None:
    img = Image.fromarray(_decode_png(_gradient_png()))
    out = BitmapConverter._preprocess(img, PreprocessOptions(black_point=64, white_point=192))
    arr = np.asarray(out)
    # Anything <= 64 should clip to 0, anything >= 192 to 255.
    assert arr[0, 0, 0] == 0
    assert arr[0, -1, 0] == 255


def test_preprocess_crop_rejects_out_of_bounds() -> None:
    with pytest.raises(ValueError):
        PreprocessOptions(crop=(0.5, 0.5, 0.8, 0.8))


def test_bitmap_converter_accepts_preprocess(two_color_png: bytes) -> None:
    # End-to-end: a brightness bump should not crash the pipeline and
    # should still produce a layered SVG.
    result = BitmapConverter().convert(
        two_color_png,
        options={
            "algorithm": "halftone",
            "num_colors": 2,
            "preprocess": {"brightness": 0.2, "contrast": 0.3},
        },
    )
    assert result.svg.startswith("<svg")


def test_fixed_palette_preserves_white_background() -> None:
    # When the operator's palette follows their pen rack (no white pen),
    # white pixels would otherwise snap to the nearest pen colour and
    # the resulting layer would survive ``drop_background``. The
    # converter must auto-inject ``#ffffff`` so the white area maps to
    # white and gets dropped, leaving the foreground as the only layer.
    img = Image.new("RGB", (50, 50), "white")
    for y in range(10, 30):
        for x in range(10, 30):
            img.putpixel((x, y), (255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    result = BitmapConverter().convert(
        buf.getvalue(),
        options={
            "segmentation_method": "fixed_palette",
            "segmentation_options": {"palette": ["#ff0000", "#00ff00"]},
            "drop_background": True,
            "background_luminance": 0.92,
            "algorithm": "halftone",
        },
    )
    lowered = result.svg.lower()
    assert "ffffff" not in lowered
    assert "ff0000" in lowered


def test_fixed_palette_chunked_handles_large_image() -> None:
    # Regression for the Ultra-tier OOM: a 5000×5000 input must not
    # blow up the (P, K, 3) broadcast. We just check it completes and
    # returns label shapes that match.
    from pen_plotter.converters.segmentation import fixed_palette

    big = Image.new("RGB", (5000, 5000), "#888888")
    labels, palette = fixed_palette(big, palette_hex=["#000000", "#ffffff"])
    assert labels.shape == (5000, 5000)
    assert palette.shape == (2, 3)


def test_otsu_produces_binary_dark_light_segmentation() -> None:
    """Otsu must return exactly two clusters ordered (dark, light) and
    cover the actual ink content of a thin-line drawing.
    """
    from PIL import ImageDraw

    from pen_plotter.converters.segmentation import otsu

    scale = 4
    w, h = 400, 300
    img4 = Image.new("RGB", (w * scale, h * scale), (250, 248, 244))
    d = ImageDraw.Draw(img4)
    for i in range(20):
        x = (40 + i * 15) * scale
        d.line((x, 30 * scale, x, (h - 30) * scale), fill=(35, 38, 45), width=scale)
    img = img4.resize((w, h), Image.Resampling.LANCZOS)
    labels, palette = otsu(img)
    # Two clusters: dark + light, dark first.
    assert palette.shape == (2, 3)
    rec709 = np.array([0.2126, 0.7152, 0.0722])
    lum = palette.astype(float) @ rec709 / 255.0
    assert lum[0] < lum[1], "otsu must return (dark, light) ordering"
    # Ink mask covers the 20 thin lines (~1 px × ~240 px each) — ~4800 px
    # of actual ink content. Anti-aliased fringe stays out of the ink
    # cluster on purpose (we don't want the pen tracing the halo around
    # every stroke).
    ink_count = int((labels == 0).sum())
    assert 3000 <= ink_count <= 8000, (
        f"otsu ink mask sparsity is off: {ink_count} px "
        f"(expected ~5k for the 20-line test image)"
    )
    # The background cluster should be the rest of the canvas.
    assert int((labels == 1).sum()) == w * h - ink_count


def test_centerline_monochrome_auto_switches_to_otsu() -> None:
    """The user's reported regression: ``centerline`` + monochrome on a
    scanned line drawing dropped most of the detail because k-means
    scattered the anti-aliased ink pixels across 3 mid-grey clusters,
    each producing its own noisy skeleton — the pen ended up drawing
    every line two or three times along the anti-aliased halos around
    the real ink. With the auto-switch the bitmap converter picks Otsu
    when these options line up, so the centerline trace runs on a
    single faithful binary mask of the ink and the pen draws each line
    exactly once.

    The right quality signal isn't raw point count — k-means produces
    *more* points by tracing both sides of every anti-aliased halo —
    but **layer count** and **redundant overlap**: a clean centerline
    of a monochrome drawing should land in a single layer.
    """
    import re

    from PIL import ImageDraw

    scale = 4
    w, h = 600, 400
    img4 = Image.new("RGB", (w * scale, h * scale), (250, 248, 244))
    d = ImageDraw.Draw(img4)
    d.rectangle((30 * scale, 30 * scale, (w - 30) * scale, (h - 30) * scale),
                outline=(35, 38, 45), width=scale)
    for i in range(15):
        x = (60 + i * 30) * scale
        d.line((x, 60 * scale, x, (h - 60) * scale), fill=(35, 38, 45), width=scale)
    img = img4.resize((w, h), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    jpg = buf.getvalue()

    common = {
        "algorithm": "centerline",
        "mono_ink_color": "#000000",
        "max_dimension_px": 400,
    }
    # Force the pre-fix path (kmeans_lab side-steps the auto-switch).
    before = BitmapConverter().convert(jpg, options={**common, "segmentation_method": "kmeans_lab"})
    # Default path with auto-switch enabled.
    after = BitmapConverter().convert(jpg, options=common)

    def layer_count(svg: str) -> int:
        return len(re.findall(r'<g\s+inkscape:label', svg))

    # Auto-switch must produce a SINGLE layer (clean), pre-fix had
    # multiple (one per fringe cluster).
    assert layer_count(after.svg) == 1, (
        f"otsu auto-switch must collapse to 1 layer, got {layer_count(after.svg)}"
    )
    assert layer_count(before.svg) >= 2, (
        f"kmeans_lab control should produce ≥2 layers on this anti-aliased "
        f"input, got {layer_count(before.svg)}"
    )


def test_centerline_explicit_segmentation_is_respected() -> None:
    """An operator who explicitly picks ``luminance_bands`` or any
    non-default segmentation must keep that choice — the auto-switch
    only fires when the bitmap options carry the default ``kmeans``.
    """
    import re

    from PIL import ImageDraw

    scale = 4
    img4 = Image.new("RGB", (200 * scale, 200 * scale), (250, 248, 244))
    d = ImageDraw.Draw(img4)
    d.rectangle((20 * scale, 20 * scale, 180 * scale, 180 * scale),
                outline=(35, 38, 45), width=scale)
    img = img4.resize((200, 200), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    jpg = buf.getvalue()

    # luminance_bands w/ num_colors=3 → at least 2 layers kept (light
    # band dropped as background, dark + mid bands kept).
    result = BitmapConverter().convert(
        jpg,
        options={
            "algorithm": "centerline",
            "mono_ink_color": "#000000",
            "max_dimension_px": 200,
            "segmentation_method": "luminance_bands",
            "num_colors": 3,
        },
    )
    layers = re.findall(r'<g\s+inkscape:label', result.svg)
    # Otsu would collapse to 1 layer — the explicit method must override
    # the auto-switch and produce 2+ luminance bands.
    assert len(layers) >= 2, (
        f"explicit luminance_bands must not be overridden by the otsu auto-switch; "
        f"got {len(layers)} layer(s)"
    )

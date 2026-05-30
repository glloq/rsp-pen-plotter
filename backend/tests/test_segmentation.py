"""Tests for the segmentation ("decoupage") module.

Each method is exercised on a tiny synthetic image so we can assert exact
cluster counts and label assignments — the cheap way to catch regressions
in the dispatcher in ``bitmap.py``.
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image

from pen_plotter.converters import segmentation
from pen_plotter.converters.bitmap import BitmapConverter, BitmapOptions


def _gradient_image(width: int = 16, height: int = 16) -> Image.Image:
    """Horizontal greyscale gradient from black (left) to white (right)."""
    arr = np.tile(np.linspace(0, 255, width, dtype=np.uint8), (height, 1))
    rgb = np.stack([arr, arr, arr], axis=-1)
    return Image.fromarray(rgb, mode="RGB")


def _png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def test_luminance_bands_creates_expected_cluster_count() -> None:
    image = _gradient_image(width=32, height=4)
    labels, palette = segmentation.luminance_bands(image, num_bands=4)
    # Exactly 4 distinct labels expected on a smooth gradient.
    assert len(np.unique(labels)) == 4
    # Palette greyscale from dark to light.
    assert palette[0, 0] < palette[-1, 0]


def test_thresholds_partition_by_breakpoints() -> None:
    image = _gradient_image(width=32, height=2)
    # Two cuts → three bands.
    labels, palette = segmentation.thresholds(image, levels=[0.33, 0.66])
    assert len(np.unique(labels)) == 3
    assert palette.shape == (3, 3)


def test_thresholds_empty_falls_back_to_single_layer() -> None:
    image = _gradient_image()
    labels, palette = segmentation.thresholds(image, levels=[])
    assert np.unique(labels).tolist() == [0]
    assert palette.shape == (1, 3)


def test_fixed_palette_snaps_to_nearest_colour() -> None:
    image = _gradient_image(width=8, height=1)
    labels, palette = segmentation.fixed_palette(image, palette_hex=["#000000", "#ffffff"])
    # 8 pixels going dark→light: roughly half go to black, half to white.
    assert sorted(np.unique(labels).tolist()) == [0, 1]
    assert np.array_equal(palette, np.array([[0, 0, 0], [255, 255, 255]], dtype=np.uint8))


def test_fixed_palette_rejects_empty() -> None:
    import pytest

    with pytest.raises(ValueError):
        segmentation.fixed_palette(_gradient_image(), palette_hex=[])


def _two_colour_image(width: int = 8, height: int = 4) -> Image.Image:
    """Left half pure red, right half pure blue — a crisp 2-colour split."""
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    arr[:, : width // 2] = (255, 0, 0)
    arr[:, width // 2 :] = (0, 0, 255)
    return Image.fromarray(arr, mode="RGB")


def test_kmeans_lab_clusters_two_colours() -> None:
    image = _two_colour_image()
    labels, palette = segmentation.kmeans_lab(image, num_colors=2, n_init=1)
    assert sorted(np.unique(labels).tolist()) == [0, 1]
    # Palette entries are the mean source RGB of each cluster, so they land
    # on (near) pure red and pure blue.
    rows = {tuple(int(c) for c in row) for row in palette}
    assert (255, 0, 0) in rows
    assert (0, 0, 255) in rows


def test_kmeans_lab_palette_is_displayable_rgb() -> None:
    """Centroids come back as real image colours (uint8 RGB), not Lab."""
    image = _gradient_image(width=16, height=16)
    _, palette = segmentation.kmeans_lab(image, num_colors=3, n_init=1)
    assert palette.dtype == np.uint8
    assert palette.shape[1] == 3
    assert (palette >= 0).all() and (palette <= 255).all()


def test_kmeans_lab_caps_k_to_unique_colours() -> None:
    """Asking for more clusters than distinct colours yields fewer layers."""
    image = _two_colour_image()
    labels, palette = segmentation.kmeans_lab(image, num_colors=8, n_init=1)
    assert len(palette) == 2
    assert len(np.unique(labels)) == 2


def test_palette_dither_zero_amount_matches_fixed_palette() -> None:
    """``amount=0`` reduces exactly to the plain nearest-colour snap."""
    image = _gradient_image(width=32, height=8)
    pal = ["#000000", "#ffffff"]
    dithered, _ = segmentation.palette_dither(image, palette_hex=pal, amount=0.0)
    snapped, _ = segmentation.fixed_palette(image, palette_hex=pal)
    assert np.array_equal(dithered, snapped)


def test_palette_dither_breaks_up_flat_midtone() -> None:
    """A flat 50% grey snaps to a single pen, but dithering mixes both."""
    grey = np.full((16, 16, 3), 128, dtype=np.uint8)
    image = Image.fromarray(grey, mode="RGB")
    pal = ["#000000", "#ffffff"]
    snapped, _ = segmentation.fixed_palette(image, palette_hex=pal)
    dithered, _ = segmentation.palette_dither(image, palette_hex=pal, amount=1.0)
    # Plain snap → one label across the whole tile; dither → both pens used.
    assert len(np.unique(snapped)) == 1
    assert len(np.unique(dithered)) == 2


def test_palette_dither_rejects_empty() -> None:
    import pytest

    with pytest.raises(ValueError):
        segmentation.palette_dither(_gradient_image(), palette_hex=[])


def test_drop_small_regions_repaints_isolated_specks() -> None:
    # A 4×4 sea of zeros with a single isolated speck of "1" — that's a
    # 1-pixel region that should be repainted to its neighbours (all 0s).
    labels = np.zeros((4, 4), dtype=np.intp)
    labels[1, 1] = 1
    cleaned = segmentation.drop_small_regions(labels, min_pixels=2)
    assert cleaned[1, 1] == 0
    assert not np.any(cleaned == 1)


def test_drop_small_regions_preserves_large_components() -> None:
    labels = np.zeros((8, 8), dtype=np.intp)
    labels[2:6, 2:6] = 1  # 16-pixel block
    cleaned = segmentation.drop_small_regions(labels, min_pixels=4)
    assert np.array_equal(cleaned, labels)


def test_merge_similar_colours_collapses_near_duplicates() -> None:
    labels = np.array([[0, 1], [2, 0]], dtype=np.intp)
    palette = np.array(
        [
            [255, 0, 0],  # red
            [254, 1, 1],  # very near red → should merge with 0
            [0, 0, 255],  # blue (well apart)
        ],
        dtype=np.uint8,
    )
    new_labels, new_palette = segmentation.merge_similar_colours(labels, palette, threshold=2.0)
    # Three clusters → two after collapse.
    assert len(new_palette) == 2
    # Labels 0 and 1 merged into the lowest-indexed root.
    assert new_labels[0, 0] == new_labels[0, 1]


def test_merge_similar_colours_noop_under_threshold() -> None:
    labels = np.array([[0, 1]], dtype=np.intp)
    palette = np.array([[0, 0, 0], [255, 255, 255]], dtype=np.uint8)
    new_labels, new_palette = segmentation.merge_similar_colours(labels, palette, threshold=1.0)
    assert np.array_equal(new_labels, labels)
    assert np.array_equal(new_palette, palette)


def test_bitmap_converter_routes_through_luminance_bands() -> None:
    """End-to-end: BitmapConverter respects the segmentation method choice."""
    image = _gradient_image(width=16, height=16)
    result = BitmapConverter().convert(
        _png_bytes(image),
        options={
            "algorithm": "direct",
            "segmentation_method": "luminance_bands",
            "segmentation_options": {"num_bands": 3},
            "drop_background": False,
        },
        fast=True,
    )
    # Three layers (one per band) — labelled by their hex colour by the
    # converter, so the SVG should carry three distinct fill colours.
    assert result.svg.count('inkscape:label="color-') == 3


def test_bitmap_converter_applies_band_recipes_in_preview() -> None:
    """End-to-end: ``band_recipes`` overrides per-layer algos so the live
    preview reflects what the post-upload bandRecipe propagation will
    eventually install. Without this the operator only ever sees the
    uniform default algorithm until they hit Apply + /rerender — exactly
    the bug the iter-2 refactor is fixing."""
    image = _gradient_image(width=16, height=16)
    # Three luminance bands → three recipes, each picking a different
    # algo so the resulting SVG carries the corresponding fingerprints.
    # halftone emits <circle>, crosshatch + edges emit <line>/<path>, so
    # a halftone-only band leaves circles inside its label group; a
    # crosshatch-only band has none.
    result = BitmapConverter().convert(
        _png_bytes(image),
        options={
            "algorithm": "direct",
            "segmentation_method": "luminance_bands",
            "segmentation_options": {"num_bands": 3},
            "drop_background": False,
            "band_recipes": [
                {"algorithm": "halftone", "algorithm_options": {"cell_size_px": 3}},
                {
                    "algorithm": "crosshatch",
                    "algorithm_options": {"angle_deg": 45, "spacing_px": 3, "crossed": False},
                },
                {
                    "algorithm": "crosshatch",
                    "algorithm_options": {"angle_deg": 135, "spacing_px": 5, "crossed": False},
                },
            ],
        },
        fast=True,
    )
    # Three rendered band layers (one per luminance band).
    assert result.svg.count('inkscape:label="color-') == 3
    # The first (darkest) band uses halftone → carries <circle> tags
    # somewhere; the two crosshatch bands together carry <line> tags.
    assert "<circle" in result.svg
    assert "<line" in result.svg


def test_bitmap_converter_band_recipes_skip_dropped_background() -> None:
    """``band_recipes`` index aligns with rendered layers, not raw
    segmentation clusters — so dropping the lightest band still
    matches recipes correctly against the surviving bands."""
    image = _gradient_image(width=16, height=16)
    result = BitmapConverter().convert(
        _png_bytes(image),
        options={
            "algorithm": "direct",
            "segmentation_method": "luminance_bands",
            "segmentation_options": {"num_bands": 4},
            "drop_background": True,
            "background_luminance": 0.5,
            "band_recipes": [
                {"algorithm": "halftone", "algorithm_options": {"cell_size_px": 4}},
                {"algorithm": "halftone", "algorithm_options": {"cell_size_px": 4}},
                {"algorithm": "halftone", "algorithm_options": {"cell_size_px": 4}},
                {"algorithm": "halftone", "algorithm_options": {"cell_size_px": 4}},
            ],
        },
        fast=True,
    )
    # drop_background trimmed the lightest band(s); the surviving ones
    # all rendered through the halftone recipe so the SVG has circles
    # and no <line>/<path> from a fallback algorithm.
    assert "<circle" in result.svg


def test_bitmap_converter_fixed_palette_via_options() -> None:
    image = _gradient_image(width=16, height=16)
    result = BitmapConverter().convert(
        _png_bytes(image),
        options={
            "algorithm": "direct",
            "segmentation_method": "fixed_palette",
            "segmentation_options": {"palette": ["#ff0000", "#0000ff"]},
            "drop_background": False,
        },
        fast=True,
    )
    assert "color-ff0000" in result.svg or "color-0000ff" in result.svg


def test_bitmap_converter_routes_through_kmeans_lab() -> None:
    """End-to-end: the ``kmeans_lab`` method reaches the renderer."""
    image = _two_colour_image(width=16, height=16)
    result = BitmapConverter().convert(
        _png_bytes(image),
        options={
            "algorithm": "direct",
            "segmentation_method": "kmeans_lab",
            "num_colors": 2,
            "drop_background": False,
        },
        fast=True,
    )
    assert "color-ff0000" in result.svg or "color-0000ff" in result.svg


def test_bitmap_converter_routes_through_palette_dither() -> None:
    """End-to-end: ``palette_dither`` snaps to the supplied palette."""
    image = _gradient_image(width=16, height=16)
    result = BitmapConverter().convert(
        _png_bytes(image),
        options={
            "algorithm": "direct",
            "segmentation_method": "palette_dither",
            "segmentation_options": {"palette": ["#ff0000", "#0000ff"], "dither_amount": 0.6},
            "drop_background": False,
        },
        fast=True,
    )
    assert "color-ff0000" in result.svg or "color-0000ff" in result.svg


def test_bitmap_converter_rejects_bad_segmentation_args() -> None:
    """Missing/wrong-shaped segmentation_options surface as ValueError."""
    import pytest

    image = _gradient_image()
    with pytest.raises(ValueError):
        BitmapConverter().convert(
            _png_bytes(image),
            options={
                "algorithm": "direct",
                "segmentation_method": "fixed_palette",
                "segmentation_options": {},  # missing 'palette'
            },
            fast=True,
        )


def test_options_validate_defaults() -> None:
    """BitmapOptions defaults match the legacy contract — old callers OK."""
    opts = BitmapOptions.model_validate({})
    assert opts.segmentation_method == "kmeans"
    assert opts.min_region_pixels == 0
    assert opts.merge_delta_e == 0.0

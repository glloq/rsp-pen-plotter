"""Tests for the expert-editor style batch.

Covers the eleven 2026-06 algorithms (ridge_lines … penrose), the
duplicate-consolidation options grafted onto crosshatch / halftone /
truchet, and the ``hidden`` flag that keeps the legacy duplicates
registered but out of the pickers.
"""

from __future__ import annotations

import numpy as np
import pytest

from pen_plotter.converters.algorithms import (
    algorithm_hidden,
    available_algorithms,
    get_algorithm,
)
from pen_plotter.manifests.algorithms import algorithms_manifest

NEW_ALGORITHMS = [
    # 2026-06 batch 1
    "ridge_lines",
    "hitomezashi",
    "cubic_disarray",
    "quadtree",
    "maze",
    "phyllotaxis",
    "voronoi_mosaic",
    "curve_stitching",
    "string_art",
    "space_colonization",
    "penrose",
    # 2026-06 batch 2
    "dither",
    "etch",
    "noise_contours",
    "reaction_diffusion",
    "superpixel_hatch",
    "moire",
    "weave",
    "honeycomb",
    "harmonograph",
    "attractor",
    "text_fill",
    # 2026-06 batch 3
    "lsystem",
    "chladni",
]

_GEOMETRY_TAGS = ("<line", "<polyline", "<circle", "<rect", "<polygon", "<path")

# Reduced budgets for the expensive algorithms so the smoke tests stay
# fast; visual quality is irrelevant here.
_FAST_OPTIONS: dict[str, dict[str, object]] = {
    "string_art": {"pegs": 32, "lines": 60},
    "reaction_diffusion": {"steps": 400},
    "space_colonization": {"attractors": 200},
    "superpixel_hatch": {"regions": 40},
}


def _element_count(svg: str) -> int:
    return sum(svg.count(tag) for tag in _GEOMETRY_TAGS)


def _disk_mask(size: int = 120) -> np.ndarray:
    yy, xx = np.mgrid[0:size, 0:size]
    return (xx - size / 2) ** 2 + (yy - size / 2) ** 2 < (size / 2 - 8) ** 2


def _radial_tone(size: int = 120) -> np.ndarray:
    """Luminance map: dark centre fading to white at the rim."""
    yy, xx = np.mgrid[0:size, 0:size]
    return np.clip(np.hypot(xx - size / 2, yy - size / 2) / (size / 2), 0.0, 1.0)


# ---------------------------------------------------------------------------
# New algorithms — smoke + contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", NEW_ALGORITHMS)
def test_new_algorithm_renders_geometry(name: str) -> None:
    algo = get_algorithm(name)
    options: dict[str, object] = dict(_FAST_OPTIONS.get(name, {}))
    if algo.tone_aware:
        options["_tone"] = _radial_tone()
    svg = algo.render_layer(_disk_mask(), "#102030", "layer", options=options)
    assert svg.startswith("<g ")
    assert svg.endswith("</g>")
    assert 'inkscape:label="layer"' in svg
    assert "#102030" in svg
    assert _element_count(svg) > 0


@pytest.mark.parametrize("name", NEW_ALGORITHMS)
def test_new_algorithm_empty_mask_yields_empty_group(name: str) -> None:
    algo = get_algorithm(name)
    svg = algo.render_layer(np.zeros((40, 40), dtype=bool), "#000000", "e", options={})
    assert _element_count(svg) == 0


@pytest.mark.parametrize("name", ["hitomezashi", "cubic_disarray", "maze",
                                  "voronoi_mosaic", "curve_stitching",
                                  "space_colonization", "etch",
                                  "noise_contours", "harmonograph",
                                  "attractor"])
def test_seeded_algorithms_are_deterministic(name: str) -> None:
    algo = get_algorithm(name)
    mask = _disk_mask()
    opts = dict(_FAST_OPTIONS.get(name, {}))
    first = algo.render_layer(mask, "#000000", "d", options={**opts, "seed": 7})
    second = algo.render_layer(mask, "#000000", "d", options={**opts, "seed": 7})
    assert first == second
    changed = algo.render_layer(mask, "#000000", "d", options={**opts, "seed": 8})
    assert changed != first


def test_string_art_emits_single_polyline() -> None:
    algo = get_algorithm("string_art")
    svg = algo.render_layer(
        _disk_mask(), "#000000", "s",
        options={"_tone": _radial_tone(), "pegs": 32, "lines": 60},
    )
    assert svg.count("<polyline") == 1


def test_ridge_lines_tone_displaces_rows() -> None:
    algo = get_algorithm("ridge_lines")
    mask = np.ones((60, 60), dtype=bool)
    flat = algo.render_layer(mask, "#000", "r", options={"_tone": np.ones((60, 60))})
    peaked = algo.render_layer(mask, "#000", "r", options={"_tone": np.zeros((60, 60))})
    # White tone → no displacement; black tone → rows shifted upward.
    assert flat != peaked


def test_text_fill_renders_custom_text_option() -> None:
    algo = get_algorithm("text_fill")
    # ``text`` is a free-form string knob (OptionSpec type="text").
    spec = {opt.key: opt for opt in algo.options_schema}
    assert spec["text"].type == "text"
    svg = algo.render_layer(
        _disk_mask(), "#000", "t", options={"text": "ABC ", "font_size_px": 10}
    )
    assert "<polyline" in svg


def test_dither_methods_produce_distinct_patterns() -> None:
    algo = get_algorithm("dither")
    mask = np.ones((48, 48), dtype=bool)
    # Horizontal gradient — a flat 0.5 would give the same checkerboard
    # under both error diffusion and ordered dithering.
    tone = np.tile(np.linspace(0.1, 0.9, 48), (48, 1))
    floyd = algo.render_layer(mask, "#000", "d", options={"_tone": tone, "method": "floyd"})
    bayer = algo.render_layer(mask, "#000", "d", options={"_tone": tone, "method": "bayer"})
    assert floyd != bayer
    assert "<circle" in floyd and "<circle" in bayer


def test_hilbert_adaptive_densifies_dark_areas() -> None:
    algo = get_algorithm("hilbert")
    mask = np.ones((128, 128), dtype=bool)
    dark = algo.render_layer(
        mask, "#000", "h", options={"adaptive": True, "_tone": np.zeros((128, 128))}
    )
    light = algo.render_layer(
        mask, "#000", "h",
        options={"adaptive": True, "_tone": np.full((128, 128), 0.85)},
    )
    # Point count tracks darkness; both stay a single connected stroke.
    assert dark.count(",") > 4 * light.count(",")
    assert dark.count("<polyline") == 1


def test_ridge_lines_radial_layout() -> None:
    algo = get_algorithm("ridge_lines")
    mask = np.ones((90, 90), dtype=bool)
    tone = np.tile(np.linspace(0.0, 1.0, 90), (90, 1))
    rows = algo.render_layer(mask, "#000", "r", options={"_tone": tone})
    radial = algo.render_layer(
        mask, "#000", "r", options={"_tone": tone, "layout": "radial"}
    )
    assert "<polyline" in radial
    assert radial != rows


def test_lsystem_presets_render_distinct_figures() -> None:
    algo = get_algorithm("lsystem")
    mask = _disk_mask()
    dragon = algo.render_layer(mask, "#000", "l", options={"preset": "dragon"})
    plant = algo.render_layer(mask, "#000", "l", options={"preset": "plant"})
    assert "<polyline" in dragon and "<polyline" in plant
    assert dragon != plant


def test_chladni_modes_change_figure() -> None:
    algo = get_algorithm("chladni")
    mask = _disk_mask()
    a = algo.render_layer(mask, "#000", "c", options={"m": 3, "n": 5})
    b = algo.render_layer(mask, "#000", "c", options={"m": 2, "n": 7})
    assert "<polyline" in a and "<polyline" in b
    assert a != b


def test_quadtree_subdivides_darker_regions_finer() -> None:
    algo = get_algorithm("quadtree")
    mask = np.ones((64, 64), dtype=bool)
    light = algo.render_layer(mask, "#000", "q", options={"_tone": np.full((64, 64), 0.95)})
    dark = algo.render_layer(mask, "#000", "q", options={"_tone": np.zeros((64, 64))})
    assert dark.count("<rect") > light.count("<rect")


# ---------------------------------------------------------------------------
# Consolidation options on existing algorithms
# ---------------------------------------------------------------------------


def test_crosshatch_joined_delegates_to_boustrophedon() -> None:
    mask = _disk_mask(60)
    plain = get_algorithm("crosshatch").render_layer(mask, "#000", "c", options={})
    joined = get_algorithm("crosshatch").render_layer(
        mask, "#000", "c", options={"joined": True}
    )
    eulerian = get_algorithm("eulerian_hatch").render_layer(mask, "#000", "c", options={})
    assert "<line" in plain and "<polyline" not in plain
    assert "<polyline" in joined and "<line" not in joined
    assert joined == eulerian


def test_truchet_arc_tiles_emit_paths() -> None:
    mask = _disk_mask(60)
    diagonal = get_algorithm("truchet").render_layer(mask, "#000", "t", options={})
    arcs = get_algorithm("truchet").render_layer(mask, "#000", "t", options={"tile": "arc"})
    assert "<line" in diagonal and "<path" not in diagonal
    assert "<path" in arcs and "<line" not in arcs
    assert ' A ' in arcs  # quarter-circle arc commands


def test_halftone_glyph_variants() -> None:
    mask = _disk_mask(60)
    dot = get_algorithm("halftone").render_layer(mask, "#000", "h", options={})
    assert "<circle" in dot and 'fill="#000"' in dot
    square = get_algorithm("halftone").render_layer(
        mask, "#000", "h", options={"glyph": "square"}
    )
    assert "<rect" in square and 'fill="none"' in square
    ring = get_algorithm("halftone").render_layer(mask, "#000", "h", options={"glyph": "ring"})
    assert "<circle" in ring and 'fill="none"' in ring


# ---------------------------------------------------------------------------
# Hidden duplicates
# ---------------------------------------------------------------------------


def test_duplicate_algorithms_are_hidden_but_registered() -> None:
    for name in ("tsp", "grid", "eulerian_hatch", "contours"):
        assert algorithm_hidden(name), name
        # Still resolvable for persisted placements / presets.
        assert get_algorithm(name).name == name
    for name in ("tsp_opt", "crosshatch", "concentric_offset", *NEW_ALGORITHMS):
        assert not algorithm_hidden(name), name


def test_manifest_carries_hidden_flag() -> None:
    by_id = {entry.id: entry for entry in algorithms_manifest().entries}
    assert by_id["tsp"].hidden is True
    assert by_id["grid"].hidden is True
    assert by_id["eulerian_hatch"].hidden is True
    assert by_id["contours"].hidden is True
    assert by_id["tsp_opt"].hidden is False
    assert by_id["ridge_lines"].hidden is False
    # Every registered algorithm still appears in the manifest.
    assert set(by_id) == {a.name for a in available_algorithms()}


# ---------------------------------------------------------------------------
# Full-pipeline integration: every new algorithm through the real converter
# ---------------------------------------------------------------------------


def _gradient_png(size: int = 100) -> bytes:
    import io

    import PIL.Image

    yy, xx = np.mgrid[0:size, 0:size]
    img = (255 * np.clip(np.hypot(xx - size / 2, yy - size / 2) / (size / 2), 0, 1)).astype(
        np.uint8
    )
    img[size // 4 : size // 3, :] = 30
    buf = io.BytesIO()
    PIL.Image.fromarray(img, "L").convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.parametrize("name", NEW_ALGORITHMS)
def test_new_algorithm_via_full_bitmap_pipeline(name: str) -> None:
    """segment_and_render must produce ink for every new algorithm.

    This is the path /upload and /preview take — it exercises tone-map
    injection (``_tone`` for tone_aware algos), option validation and
    the SVG assembly, none of which the render_layer unit tests touch.
    """
    from pen_plotter.converters.bitmap import BitmapConverter

    result, seg = BitmapConverter().segment_and_render(
        _gradient_png(),
        options={
            "algorithm": name,
            "algorithm_options": dict(_FAST_OPTIONS.get(name, {})),
            "segmentation_options": {"method": "luminance_bands", "num_bands": 2},
            "mono_ink_color": "#1d4ed8",
        },
    )
    assert seg.luminance is not None
    assert _element_count(result.svg) > 0, f"{name} produced no geometry via the pipeline"

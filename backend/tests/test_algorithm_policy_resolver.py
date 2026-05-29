"""Tests for the AlgorithmPolicyResolver (roadmap B.1 / audit #4)."""

from __future__ import annotations

import pytest

from pen_plotter.domain.policy import (
    Goal,
    PaletteMode,
    PolicyInput,
    QualityTier,
    SegmentationMethod,
    SourceKind,
    resolve,
)


def _input(**overrides: object) -> PolicyInput:
    payload: dict[str, object] = {
        "source_kind": SourceKind.BITMAP_PHOTO,
        "goal": Goal.FAST,
        "palette_mode": PaletteMode.MACHINE_ONLY,
        "available_colors_count": 4,
        "image_megapixels": 1.0,
        "layer_count_estimate": 4,
        "is_mono_pen_machine": False,
    }
    payload.update(overrides)
    return PolicyInput(**payload)  # type: ignore[arg-type]


# ── Matrix branches — Section A: bitmap_photo ────────────────────────


def test_bitmap_photo_fast_picks_scanlines() -> None:
    d = resolve(_input(goal=Goal.FAST))
    assert d.default_algorithm == "scanlines"
    assert d.quality_tier is QualityTier.DRAFT
    assert d.fallback_chain == ["halftone"]
    assert d.segmentation_method is SegmentationMethod.FIXED_PALETTE
    assert d.default_options["num_colors"] == 4  # min(4, 4)
    assert any(r.rule == "bitmap_photo.fast" for r in d.reasoning)


def test_bitmap_photo_fast_caps_num_colors_to_available() -> None:
    d = resolve(_input(goal=Goal.FAST, available_colors_count=3))
    assert d.default_options["num_colors"] == 3


def test_bitmap_photo_balanced_picks_crosshatch() -> None:
    d = resolve(_input(goal=Goal.BALANCED))
    assert d.default_algorithm == "crosshatch"
    assert d.quality_tier is QualityTier.STANDARD
    assert d.default_options["angle_deg"] == 45
    assert d.default_options["crossed"] is True


def test_bitmap_photo_quality_picks_double_crosshatch() -> None:
    d = resolve(_input(goal=Goal.QUALITY))
    # Quality is now a two-pass fine crosshatch (45° + 15°, pitch 3 px)
    # — strictly denser than the BALANCED single crosshatch at pitch 4.
    # The old single stippling pass read as sparser/worse than balanced.
    assert d.default_algorithm == "crosshatch"
    assert d.quality_tier is QualityTier.FINAL
    assert d.default_options["spacing_px"] == 3
    assert [p["algorithm"] for p in d.default_passes] == ["crosshatch", "crosshatch"]
    assert d.default_passes[0]["algorithm_options"]["angle_deg"] == 45
    assert d.default_passes[1]["algorithm_options"]["angle_deg"] == 15
    assert all(p["algorithm_options"]["spacing_px"] == 3 for p in d.default_passes)


# ── Matrix branches — Section B: bitmap_illustration ─────────────────


def test_bitmap_illustration_fast_picks_direct() -> None:
    d = resolve(_input(source_kind=SourceKind.BITMAP_ILLUSTRATION, available_colors_count=6))
    assert d.default_algorithm == "direct"
    assert d.default_options["num_colors"] == 6
    assert d.fallback_chain == ["edges"]


def test_bitmap_illustration_balanced_picks_contours() -> None:
    d = resolve(
        _input(source_kind=SourceKind.BITMAP_ILLUSTRATION, goal=Goal.BALANCED)
    )
    assert d.default_algorithm == "contours"
    assert d.default_options["max_rings"] == 24


def test_bitmap_illustration_quality_picks_centerline() -> None:
    d = resolve(
        _input(source_kind=SourceKind.BITMAP_ILLUSTRATION, goal=Goal.QUALITY)
    )
    assert d.default_algorithm == "centerline"
    assert d.default_options["smooth"] is True


# ── Matrix branches — Section C: vector_svg ──────────────────────────


def test_vector_svg_fast_passthrough() -> None:
    d = resolve(_input(source_kind=SourceKind.VECTOR_SVG))
    assert d.default_algorithm == "vector_passthrough"
    assert d.segmentation_method is SegmentationMethod.NONE
    assert d.default_options["simplify"] == 0.08


def test_vector_svg_quality_arcs_on() -> None:
    d = resolve(_input(source_kind=SourceKind.VECTOR_SVG, goal=Goal.QUALITY))
    assert d.default_algorithm == "vector_optimize_fine"
    assert d.default_options["arcs"] is True
    assert d.default_options["simplify"] == 0.02


# ── Matrix branches — Section D: pdf_doc ─────────────────────────────


def test_pdf_doc_fast_hybrid() -> None:
    d = resolve(_input(source_kind=SourceKind.PDF_DOC))
    assert d.default_algorithm == "pdf_text_lines_scanlines"
    assert d.default_options["raster_strategy"] == "scanlines"


def test_pdf_doc_quality_hybrid() -> None:
    d = resolve(_input(source_kind=SourceKind.PDF_DOC, goal=Goal.QUALITY))
    assert d.default_algorithm == "pdf_text_stippling"


# ── Matrix branches — Section E: text_typography ─────────────────────


def test_text_typography_fast_uses_hershey_mono() -> None:
    d = resolve(_input(source_kind=SourceKind.TEXT_TYPOGRAPHY))
    assert d.default_algorithm == "hershey_mono"
    assert d.segmentation_method is SegmentationMethod.NONE
    assert d.quality_tier is QualityTier.DRAFT


def test_text_typography_quality_uses_decorative() -> None:
    d = resolve(_input(source_kind=SourceKind.TEXT_TYPOGRAPHY, goal=Goal.QUALITY))
    assert d.default_algorithm == "hershey_decorative"


# ── Palette mode ─────────────────────────────────────────────────────


def test_free_palette_uses_kmeans_for_bitmap() -> None:
    d = resolve(_input(palette_mode=PaletteMode.FREE))
    assert d.segmentation_method is SegmentationMethod.KMEANS
    assert any(r.rule == "palette.free_kmeans" for r in d.reasoning)


def test_machine_only_palette_uses_fixed_palette() -> None:
    d = resolve(_input(palette_mode=PaletteMode.MACHINE_ONLY))
    assert d.segmentation_method is SegmentationMethod.FIXED_PALETTE
    assert any(r.rule == "palette.machine_only" for r in d.reasoning)


def test_vector_input_ignores_palette_mode_for_segmentation() -> None:
    d = resolve(
        _input(source_kind=SourceKind.VECTOR_SVG, palette_mode=PaletteMode.FREE)
    )
    assert d.segmentation_method is SegmentationMethod.NONE


# ── Hard constraints — audit #4 §4 ───────────────────────────────────


def test_large_image_forbids_heavy_algorithm_in_quality_minus_one() -> None:
    # Quality stippling matrix entry would normally apply, but
    # ``image_megapixels > 8`` only triggers when goal != quality, so
    # balanced is the interesting case where the constraint may bite.
    # We use the synthetic heavy algorithm path via FAST + vector
    # path is exempt — pick an illustration + balanced (contours) and
    # check no constraint fires.
    d = resolve(
        _input(
            source_kind=SourceKind.BITMAP_ILLUSTRATION,
            goal=Goal.BALANCED,
            image_megapixels=12.0,
        )
    )
    # contours isn't in the heavy list, so the constraint records the
    # mono-pen check (we set is_mono_pen_machine=False here) — i.e.
    # no override.
    assert d.default_algorithm == "contours"


def test_large_image_overrides_heavy_algorithm() -> None:
    # Manually craft a scenario where a heavy algo is the base
    # recommendation. None of the audit-#4 matrix entries propose a
    # heavy algorithm in non-quality, so the constraint mainly guards
    # the fallback chain. Verify the chain is filtered.
    d = resolve(_input(goal=Goal.BALANCED, image_megapixels=12.0))
    for forbidden in {"tsp", "tsp_opt", "voronoi_stipple", "flowfield"}:
        assert forbidden not in d.fallback_chain


def test_large_image_in_quality_does_not_force_override() -> None:
    d = resolve(_input(goal=Goal.QUALITY, image_megapixels=20.0))
    # QUALITY exempts the heavy-input constraint; the double-crosshatch
    # quality recommendation (and its multi-pass stack) stays.
    assert d.default_algorithm == "crosshatch"
    assert len(d.default_passes) == 2


def test_sparse_palette_constraint_overrides_to_scanlines() -> None:
    # bitmap_illustration / quality → centerline, which isn't a
    # palette-friendly algorithm; with available_colors=2 the resolver
    # forces scanlines. (bitmap_photo/quality is now crosshatch, which
    # *is* palette-friendly, so it would no longer trip this rule.)
    d = resolve(
        _input(
            source_kind=SourceKind.BITMAP_ILLUSTRATION,
            goal=Goal.QUALITY,
            available_colors_count=2,
        )
    )
    assert d.default_algorithm == "scanlines"
    assert any(
        c.constraint == "sparse_palette" for c in d.hard_constraints_applied
    )


def test_sparse_palette_does_not_fire_for_friendly_algo() -> None:
    # bitmap_illustration / fast already proposes 'direct' which is in
    # the friendly list, so the constraint is silent.
    d = resolve(
        _input(source_kind=SourceKind.BITMAP_ILLUSTRATION, available_colors_count=2)
    )
    assert d.default_algorithm == "direct"


def test_mono_pen_machine_constraint_records_explanation() -> None:
    d = resolve(_input(is_mono_pen_machine=True))
    assert any(
        c.constraint == "mono_pen_machine" for c in d.hard_constraints_applied
    )


def test_mono_pen_caps_num_colors_to_one() -> None:
    d = resolve(_input(is_mono_pen_machine=True, available_colors_count=4))
    assert d.default_options["num_colors"] == 1


def test_mono_pen_with_free_palette_falls_back_to_fixed_palette() -> None:
    d = resolve(
        _input(is_mono_pen_machine=True, palette_mode=PaletteMode.FREE)
    )
    assert d.segmentation_method is SegmentationMethod.FIXED_PALETTE


# ── Reasoning trail snapshot ─────────────────────────────────────────


def test_reasoning_is_stable_and_minimal_for_fast_photo() -> None:
    d = resolve(_input(goal=Goal.FAST))
    rule_ids = [hit.rule for hit in d.reasoning]
    assert rule_ids == [
        "bitmap_photo.fast",
        "palette.machine_only",
        "palette.num_colors_capped",
    ]


def test_resolve_is_pure() -> None:
    inp = _input(goal=Goal.BALANCED)
    a = resolve(inp)
    b = resolve(inp)
    assert a.model_dump() == b.model_dump()


# ── Smoke: full matrix is reachable ──────────────────────────────────


@pytest.mark.parametrize("sk", list(SourceKind))
@pytest.mark.parametrize("g", list(Goal))
def test_every_matrix_cell_returns_a_decision(sk: SourceKind, g: Goal) -> None:
    d = resolve(_input(source_kind=sk, goal=g))
    assert d.default_algorithm
    assert d.quality_tier in {QualityTier.DRAFT, QualityTier.STANDARD, QualityTier.FINAL}

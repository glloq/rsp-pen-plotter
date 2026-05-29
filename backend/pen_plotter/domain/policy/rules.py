"""Per-(source_kind, goal) recommendation table — audit #4 §3.

Each entry is the *base* recommendation **before** hard constraints
apply (those live in :mod:`pen_plotter.domain.policy.constraints`).
Keeping the matrix as plain data, indexed by ``(source_kind, goal)``,
keeps it readable and easy to snapshot in tests.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pen_plotter.domain.policy.types import (
    Goal,
    PaletteMode,
    QualityTier,
    RuleHit,
    SegmentationMethod,
    SourceKind,
)


@dataclass(frozen=True)
class _BaseRule:
    """One cell of the matrix."""

    algorithm: str
    quality: QualityTier
    fallback_chain: tuple[str, ...]
    # Segmentation override. ``None`` keeps the default
    # (``FIXED_PALETTE`` for bitmaps, ``NONE`` for vector / text).
    segmentation: SegmentationMethod | None = None
    options: Mapping[str, Any] = field(default_factory=dict)
    # Optional multi-pass stack. When non-empty the renderer draws this
    # ordered sequence of (algorithm, options) passes against each colour
    # mask instead of the single ``algorithm`` above — used by the
    # QUALITY tier to layer several treatments for maximum detail. The
    # ``algorithm`` / ``options`` fields stay populated with the first
    # pass so single-algorithm consumers (and fallbacks) still work.
    passes: tuple[Mapping[str, Any], ...] = ()
    rationale: str = ""


# Audit #4 §3 — matrix tables A through E.
#
# Notes preserved verbatim from the audit:
# - section A bitmap_photo: scanlines/crosshatch/stippling
# - section B bitmap_illustration: direct/contours/centerline
# - section C vector_svg: simplify+optimize chain at three intensities
# - section D pdf_doc: hybrid strategy per goal
# - section E text_typography: Hershey at three intensities
_MATRIX: dict[tuple[SourceKind, Goal], _BaseRule] = {
    # ── A) bitmap_photo ───────────────────────────────────────────────
    (SourceKind.BITMAP_PHOTO, Goal.FAST): _BaseRule(
        algorithm="scanlines",
        quality=QualityTier.DRAFT,
        fallback_chain=("halftone",),
        options={"spacing_px": 5, "wave_amp_px": 0},
        rationale="Photo + objectif rapidité : scanlines en palette fixée.",
    ),
    (SourceKind.BITMAP_PHOTO, Goal.BALANCED): _BaseRule(
        algorithm="crosshatch",
        quality=QualityTier.STANDARD,
        fallback_chain=("scanlines",),
        options={"spacing_px": 4, "angle_deg": 45, "crossed": True},
        rationale="Photo + objectif équilibré : crosshatch à 45°.",
    ),
    (SourceKind.BITMAP_PHOTO, Goal.QUALITY): _BaseRule(
        # Two-pass fine crosshatch: a 45° base layer plus a 15° layer so
        # the result reads as four hatch directions at a tighter pitch
        # than BALANCED (spacing 3 vs 4, two passes vs one). The old
        # single stippling pass at density 0.018 was sparser than
        # BALANCED and read as worse, not better (operator report).
        algorithm="crosshatch",
        quality=QualityTier.FINAL,
        fallback_chain=("scanlines",),
        options={"spacing_px": 3, "angle_deg": 45, "crossed": True},
        passes=(
            {
                "algorithm": "crosshatch",
                "algorithm_options": {"spacing_px": 3, "angle_deg": 45, "crossed": True},
            },
            {
                "algorithm": "crosshatch",
                "algorithm_options": {"spacing_px": 3, "angle_deg": 15, "crossed": True},
            },
        ),
        rationale=(
            "Photo + objectif qualité : double passe crosshatch fine "
            "(45° + 15°, pitch 3 px) pour un maximum de détail."
        ),
    ),
    # ── B) bitmap_illustration ────────────────────────────────────────
    (SourceKind.BITMAP_ILLUSTRATION, Goal.FAST): _BaseRule(
        algorithm="direct",
        quality=QualityTier.DRAFT,
        fallback_chain=("edges",),
        rationale="Illustration + rapidité : direct sur aplats.",
    ),
    (SourceKind.BITMAP_ILLUSTRATION, Goal.BALANCED): _BaseRule(
        algorithm="contours",
        quality=QualityTier.STANDARD,
        fallback_chain=("direct",),
        options={"spacing_px": 4, "max_rings": 24},
        rationale="Illustration + équilibré : contours + passe crosshatch.",
    ),
    (SourceKind.BITMAP_ILLUSTRATION, Goal.QUALITY): _BaseRule(
        algorithm="centerline",
        quality=QualityTier.FINAL,
        fallback_chain=("contours",),
        options={"min_branch_px": 2, "smooth": True},
        rationale="Illustration + qualité : centerline (concentric_offset si pas de formes fines).",
    ),
    # ── C) vector_svg ─────────────────────────────────────────────────
    (SourceKind.VECTOR_SVG, Goal.FAST): _BaseRule(
        algorithm="vector_passthrough",
        segmentation=SegmentationMethod.NONE,
        quality=QualityTier.DRAFT,
        fallback_chain=("vector_simplify_high",),
        options={"optimize": True, "simplify": 0.08},
        rationale="Vecteur + rapidité : pas de rerender, simplify 0.08.",
    ),
    (SourceKind.VECTOR_SVG, Goal.BALANCED): _BaseRule(
        algorithm="vector_optimize",
        segmentation=SegmentationMethod.NONE,
        quality=QualityTier.STANDARD,
        fallback_chain=("vector_passthrough",),
        options={"optimize": True, "simplify": 0.05},
        rationale="Vecteur + équilibré : optimize vpype, simplify 0.05.",
    ),
    (SourceKind.VECTOR_SVG, Goal.QUALITY): _BaseRule(
        algorithm="vector_optimize_fine",
        segmentation=SegmentationMethod.NONE,
        quality=QualityTier.FINAL,
        fallback_chain=("vector_optimize",),
        options={"optimize": True, "simplify": 0.02, "arcs": True},
        rationale="Vecteur + qualité : optimize fin + arc-fit.",
    ),
    # ── D) pdf_doc ────────────────────────────────────────────────────
    (SourceKind.PDF_DOC, Goal.FAST): _BaseRule(
        algorithm="pdf_text_lines_scanlines",
        quality=QualityTier.DRAFT,
        fallback_chain=("pdf_text_only",),
        options={"raster_strategy": "scanlines", "num_colors": 3},
        rationale="PDF + rapidité : texte/lignes en vecteur, images en scanlines.",
    ),
    (SourceKind.PDF_DOC, Goal.BALANCED): _BaseRule(
        algorithm="pdf_text_crosshatch",
        quality=QualityTier.STANDARD,
        fallback_chain=("pdf_text_lines_scanlines",),
        options={"raster_strategy": "crosshatch"},
        rationale="PDF + équilibré : texte vecteur, images en crosshatch.",
    ),
    (SourceKind.PDF_DOC, Goal.QUALITY): _BaseRule(
        algorithm="pdf_text_stippling",
        quality=QualityTier.FINAL,
        fallback_chain=("pdf_text_crosshatch",),
        options={"raster_strategy": "stippling"},
        rationale="PDF + qualité : texte vecteur, images en stippling/contours.",
    ),
    # ── E) text_typography ────────────────────────────────────────────
    (SourceKind.TEXT_TYPOGRAPHY, Goal.FAST): _BaseRule(
        algorithm="hershey_mono",
        segmentation=SegmentationMethod.NONE,
        quality=QualityTier.DRAFT,
        fallback_chain=(),
        rationale="Texte + rapidité : Hershey mono-stroke + mono pen.",
    ),
    (SourceKind.TEXT_TYPOGRAPHY, Goal.BALANCED): _BaseRule(
        algorithm="hershey_grouped",
        segmentation=SegmentationMethod.NONE,
        quality=QualityTier.STANDARD,
        fallback_chain=("hershey_mono",),
        rationale="Texte + équilibré : Hershey avec layer grouping par blocs.",
    ),
    (SourceKind.TEXT_TYPOGRAPHY, Goal.QUALITY): _BaseRule(
        algorithm="hershey_decorative",
        segmentation=SegmentationMethod.NONE,
        quality=QualityTier.FINAL,
        fallback_chain=("hershey_grouped",),
        rationale="Texte + qualité : Hershey + passes décoratifs légers.",
    ),
}


def lookup(source_kind: SourceKind, goal: Goal) -> _BaseRule:
    """Return the matrix cell for ``(source_kind, goal)``."""
    return _MATRIX[(source_kind, goal)]


def derive_segmentation(
    rule: _BaseRule,
    source_kind: SourceKind,
    palette_mode: PaletteMode,
) -> tuple[SegmentationMethod, RuleHit | None]:
    """Resolve the segmentation method for a recommendation.

    Vector / text sources always use ``NONE``. For bitmaps, the audit
    requires ``fixed_palette`` whenever ``palette_mode == machine_only``
    and allows ``kmeans`` otherwise.
    """
    if rule.segmentation is not None:
        return rule.segmentation, None
    if source_kind in {SourceKind.VECTOR_SVG, SourceKind.TEXT_TYPOGRAPHY}:
        return SegmentationMethod.NONE, None
    if palette_mode is PaletteMode.MACHINE_ONLY:
        return (
            SegmentationMethod.FIXED_PALETTE,
            RuleHit(
                rule="palette.machine_only",
                description=(
                    "palette_mode = machine_only → segmentation fixed_palette "
                    "imposée sur les couleurs disponibles."
                ),
            ),
        )
    return (
        SegmentationMethod.KMEANS,
        RuleHit(
            rule="palette.free_kmeans",
            description="palette libre → segmentation kmeans.",
        ),
    )

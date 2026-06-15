"""Typed inputs and outputs of the algorithm policy resolver."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SourceKind(StrEnum):
    """Source classifier — audit #4 § Entrées."""

    BITMAP_PHOTO = "bitmap_photo"
    BITMAP_ILLUSTRATION = "bitmap_illustration"
    VECTOR_SVG = "vector_svg"
    PDF_DOC = "pdf_doc"
    TEXT_TYPOGRAPHY = "text_typography"


class Goal(StrEnum):
    """Operator intent — audit #4 § Entrées."""

    FAST = "fast"
    BALANCED = "balanced"
    QUALITY = "quality"


class PaletteMode(StrEnum):
    """How the resolver is allowed to spend colours."""

    MACHINE_ONLY = "machine_only"
    """Stick to whichever pens are physically installed in the magazine."""

    UNION = "union"
    """Allow colours available across all magazines / users."""

    FREE = "free"
    """No constraint — the renderer picks its preferred palette."""


class QualityTier(StrEnum):
    """Preview-time quality tier the renderer should target."""

    DRAFT = "draft"
    STANDARD = "standard"
    FINAL = "final"


class SegmentationMethod(StrEnum):
    """Segmentation strategy on the way into the renderer."""

    FIXED_PALETTE = "fixed_palette"
    KMEANS = "kmeans"
    NONE = "none"
    """Vector input — no raster segmentation needed."""


class RuleHit(BaseModel):
    """One rule from the matrix that contributed to the decision."""

    rule: str
    """Stable identifier — e.g. ``bitmap_photo.fast``."""

    description: str
    """Short human-readable explanation, used by the modal's
    "Pourquoi ce choix ?" surface."""


class ConstraintHit(BaseModel):
    """One safety constraint (audit #4 §4) that fired."""

    constraint: str
    description: str
    forbidden_algorithms: list[str] = Field(default_factory=list)


class PolicyInput(BaseModel):
    """Everything the resolver needs to pick defaults."""

    source_kind: SourceKind
    goal: Goal = Goal.FAST
    # The editor is no longer capped to the pens physically mounted in
    # the magazine: the operator picks any ink they own and the loading
    # is handled at print time (load modal for magazines, manual swap
    # prompts otherwise). ``union`` — pens ∪ available-colours inventory —
    # is therefore the default so the resolver chooses the best-matching
    # owned inks for the requested layer count instead of limiting to the
    # mounted slots.
    palette_mode: PaletteMode = PaletteMode.UNION
    available_colors_count: int = Field(ge=0, default=1)
    image_megapixels: float | None = None
    layer_count_estimate: int = Field(ge=0, default=1)
    is_mono_pen_machine: bool = False


class PolicyDecision(BaseModel):
    """The resolver's recommendation."""

    segmentation_method: SegmentationMethod
    default_algorithm: str
    default_options: dict[str, Any] = Field(default_factory=dict)
    default_passes: list[dict[str, Any]] = Field(default_factory=list)
    """Optional ordered multi-pass stack. Each item is
    ``{"algorithm": str, "algorithm_options": dict}``. Empty for
    single-algorithm recommendations; populated for QUALITY tiers that
    layer several passes per colour mask. ``default_algorithm`` /
    ``default_options`` always mirror the first pass for back-compat."""

    quality_tier: QualityTier
    fallback_chain: list[str] = Field(default_factory=list)
    reasoning: list[RuleHit] = Field(default_factory=list)
    hard_constraints_applied: list[ConstraintHit] = Field(default_factory=list)

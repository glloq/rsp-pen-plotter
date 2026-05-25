"""Print-plan entities: the single pivot exchanged between front, services and engines.

``PrintPlan`` is what the client sends when it wants something rendered or
checked. ``ResolvedPlan`` is what the application services emit after
applying profile defaults, validating invariants and computing a stable
hash — this is the snapshot the engines actually consume and the one we
archive for traceability.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PausePolicy = Literal["auto", "always", "never"]
ScaleMode = Literal["fit", "actual"]


class PlacementPlan(BaseModel):
    """Sheet placement inside the machine workspace.

    Mirrors :class:`pen_plotter.models.Placement` — kept as a separate
    domain model so the pivot is self-contained and doesn't pull legacy
    types into the new package boundary.
    """

    sheet_width_mm: float = Field(gt=0.0)
    sheet_height_mm: float = Field(gt=0.0)
    offset_x_mm: float = 0.0
    offset_y_mm: float = 0.0


class LayerPlan(BaseModel):
    """Per-layer print settings — the unified pivot type.

    Replaces the old ``GenerateLayer`` Pydantic model and
    ``LayerGeneration`` dataclass. Every field is optional except
    ``layer_id``; defaults are filled in later by
    :func:`pen_plotter.application.plan_resolver.resolve_plan` using
    the active machine profile.
    """

    layer_id: str
    target_pen_slot: int | None = None
    drawing_speed_mm_s: float | None = None
    source_color: str | None = None
    color_label: str | None = None
    pause_before: PausePolicy = "auto"


class PlanMetadata(BaseModel):
    """Provenance information attached to a plan.

    The client may set ``client_version`` so a stored snapshot can later
    be correlated with the UI release that produced it.
    """

    model_config = ConfigDict(extra="ignore")

    client_version: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PrintPlan(BaseModel):
    """What the operator wants drawn, before profile defaults apply.

    The same instance flows through ``/preflight`` and ``/generate`` so
    both endpoints provably operate on identical inputs.
    """

    svg: str
    profile_name: str
    layers: list[LayerPlan] = Field(default_factory=list)
    scale_mode: ScaleMode = "fit"
    margin_mm: float = 10.0
    placement: PlacementPlan | None = None
    metadata: PlanMetadata = Field(default_factory=PlanMetadata)


class ResolvedLayer(BaseModel):
    """A layer with every setting resolved against the active profile.

    No ``None`` survives here: ``drawing_speed_mm_s`` falls back to the
    profile speed, and ``pause_before`` is replaced by the literal
    decision (``"pause"`` / ``"skip"``) the engine will follow.
    """

    layer_id: str
    target_pen_slot: int | None
    drawing_speed_mm_s: float
    source_color: str | None
    color_label: str | None
    pause_before: PausePolicy
    pen_slot_installed: bool


class ResolvedPlan(BaseModel):
    """The plan after defaults + validation, ready to feed the engines.

    Carries the original ``PrintPlan`` plus the per-layer resolution and
    a deterministic content hash. Engines never re-read the raw plan;
    they read the resolved one. Snapshots stored in SQLite are exactly
    instances of this model.
    """

    plan: PrintPlan
    layers: list[ResolvedLayer]
    plan_hash: str
    profile_name: str
    profile_drawing_speed_mm_s: float
    mono_pen: bool

"""Pure-business entities and invariants shared by every pipeline stage.

This package is the single source of truth for the data contracts that
flow through ``preflight`` and ``generate``. Endpoints, application
services and the core engines all consume the same models — there is no
parallel dataclass/Pydantic split anymore.
"""

from pen_plotter.domain.print_plan import (
    LayerPlan,
    PlacementPlan,
    PlanMetadata,
    PrintPlan,
    ResolvedLayer,
    ResolvedPlan,
)

__all__ = [
    "LayerPlan",
    "PlacementPlan",
    "PlanMetadata",
    "PrintPlan",
    "ResolvedLayer",
    "ResolvedPlan",
]

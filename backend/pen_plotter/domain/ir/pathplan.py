"""Path-plan IR — geometry after optimization, ready for gcode emission.

Adds per-layer routing metrics (draw length, pen-up travel, sort order)
that the optimizer produces. The geometry shape itself is the same as
:class:`pen_plotter.domain.ir.geometry.GeometryIR` but the polylines are
**ordered** (the optimizer's job) and carry a routing cost summary.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from pen_plotter.domain.ir.artifacts import Artifact
from pen_plotter.domain.ir.geometry import Polyline


class PlannedLayer(BaseModel):
    """Ordered polylines for one layer + post-optimization metrics."""

    layer_id: str
    color: str = "#000000"
    label: str = ""
    polylines: list[Polyline] = Field(default_factory=list)
    draw_length_mm: float = 0.0
    pen_up_length_mm: float = 0.0


class PathPlanIR(Artifact):
    """The contract between optimize and gcode-emit.

    Holds the layers in execution order. ``total_pen_up_length_mm`` is
    the sum across layers plus inter-layer travel.
    """

    kind: Literal["path_plan"] = "path_plan"
    geometry_hash: str
    layers: list[PlannedLayer] = Field(default_factory=list)
    total_draw_length_mm: float = 0.0
    total_pen_up_length_mm: float = 0.0

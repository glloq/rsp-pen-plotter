"""Geometry / path-plan / machine-program IR (roadmap A.3).

This subpackage introduces a typed, content-addressed intermediate
representation that runs **in parallel** with the existing SVG-string
pipeline. The two are bridged by adapters in :mod:`pen_plotter.domain.ir.adapter`
so callers can opt in via ``OMNIPLOT_IR_ENABLED=1`` without breaking
anything.

Pipeline shape (audit #1)::

    SourceAsset
      -> SegmentationArtifact
      -> GeometryIR
      -> PathPlanIR
      -> MachineProgram
      -> ExecutionRun

Each artifact has a deterministic :func:`artifact_hash` derived from its
serialized content + the IR schema version. Phase B builds a DAG cache
keyed on those hashes (audit #1 §3).
"""

from __future__ import annotations

from pen_plotter.domain.ir.artifacts import (
    IR_SCHEMA_VERSION,
    Artifact,
    ExecutionRun,
    MachineProgram,
    SourceAsset,
    artifact_hash,
)
from pen_plotter.domain.ir.geometry import (
    GeometryIR,
    LayerGeometry,
    Polyline,
    SegmentationArtifact,
)
from pen_plotter.domain.ir.pathplan import (
    PathPlanIR,
    PlannedLayer,
)

__all__ = [
    "IR_SCHEMA_VERSION",
    "Artifact",
    "ExecutionRun",
    "GeometryIR",
    "LayerGeometry",
    "MachineProgram",
    "PathPlanIR",
    "PlannedLayer",
    "Polyline",
    "SegmentationArtifact",
    "SourceAsset",
    "artifact_hash",
]

"""Algorithm + segmentation policy resolver (roadmap B.1).

Given a description of what the operator is about to plot (source kind,
goal, available colours, machine, image size, …) the resolver picks a
default algorithm, segmentation method and parameter set **without any
user input**. Audit #4's decision matrix is the spec.

The resolver is **pure** — same inputs, same outputs — so the modal V2
(audit #3 / phase C) can ask it for a recommendation, show the
``reasoning`` trail next to the proposed defaults, and let an expert
override any of the fields.
"""

from __future__ import annotations

from pen_plotter.domain.policy.resolver import resolve
from pen_plotter.domain.policy.types import (
    ConstraintHit,
    Goal,
    PaletteMode,
    PolicyDecision,
    PolicyInput,
    QualityTier,
    RuleHit,
    SegmentationMethod,
    SourceKind,
)

__all__ = [
    "ConstraintHit",
    "Goal",
    "PaletteMode",
    "PolicyDecision",
    "PolicyInput",
    "QualityTier",
    "RuleHit",
    "SegmentationMethod",
    "SourceKind",
    "resolve",
]

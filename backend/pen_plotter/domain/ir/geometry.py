"""Typed geometry IR — polyline-set per layer.

This is the strongly-typed counterpart of the SVG pivot string that
flows through the v0.1 pipeline. Each layer carries a list of
polylines (sequences of ``(x, y)`` points in millimetres), a colour,
and a stable layer id. Bezier / arc primitives are flattened on the way
in so the downstream optimizer and gcode generator can work on a single
representation.

A second artifact, :class:`SegmentationArtifact`, captures the output
of the segmentation phase for bitmap sources — a labelled image plus
the palette that produced it. The geometry IR is derived from it (or
from a vector source) by the renderer.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from pen_plotter.domain.ir.artifacts import Artifact


class Polyline(BaseModel):
    """An open or closed polyline in millimetres."""

    points: list[tuple[float, float]] = Field(min_length=2)
    closed: bool = False


class LayerGeometry(BaseModel):
    """All polylines for one logical layer."""

    layer_id: str
    color: str = "#000000"
    label: str = ""
    polylines: list[Polyline] = Field(default_factory=list)


class GeometryIR(Artifact):
    """Layered polyline geometry, the contract between render and optimize."""

    kind: Literal["geometry"] = "geometry"
    source_hash: str
    viewbox: tuple[float, float, float, float] | None = None
    layers: list[LayerGeometry] = Field(default_factory=list)


class SegmentationArtifact(Artifact):
    """Output of the segmentation phase for bitmap sources.

    Stores the **palette** (RGB tuples) and the resolved per-pixel label
    image is **referenced** by hash rather than embedded — keeping the
    artifact small enough to ship in a manifest while still letting
    downstream cache lookups verify it's the right segmentation.
    """

    kind: Literal["segmentation"] = "segmentation"
    source_hash: str
    palette: list[tuple[int, int, int]]
    width_px: int
    height_px: int
    label_image_sha256: str
    method: str = "kmeans"

"""Shared Pydantic data contracts for the OmniPlot pipeline.

These models are the stable contracts every later phase relies on: machine
profiles describe target hardware, layers describe separated drawing content,
and jobs track a single conversion-to-plot lifecycle.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class WorkspaceBounds(BaseModel):
    """Rectangular drawable area of a machine, expressed in profile units."""

    x_min: float
    y_min: float
    x_max: float
    y_max: float


class BoundingBox(BaseModel):
    """Axis-aligned bounding box of a layer's geometry, in millimeters."""

    x_min: float
    y_min: float
    x_max: float
    y_max: float


class EbbConfig(BaseModel):
    """EiBotBoard (AxiDraw-class) motion parameters.

    Required only for profiles whose ``gcode_dialect`` is ``"ebb"``. The two
    motors form an H-bot, so a Cartesian move maps to mixed motor steps.
    """

    steps_per_mm: float = 80.0
    servo_up: int = 16000
    servo_down: int = 12000
    servo_rate: int = 400
    serial_terminator: Literal["cr", "lf", "crlf"] = "cr"


class MachineProfile(BaseModel):
    """Describes a target pen plotter.

    All machine-specific behavior lives in profile files rather than code, so a
    new plotter can be supported by writing one of these (typically loaded from
    YAML) without touching the application.
    """

    name: str
    units: Literal["mm", "inch"]
    workspace: WorkspaceBounds
    origin: Literal["top_left", "bottom_left", "center"]
    gcode_dialect: Literal["grbl", "marlin", "klipper", "ebb", "custom"]
    pen_up_command: str
    pen_down_command: str
    tool_change_method: Literal["manual_pause", "carousel", "rack", "none"]
    tool_change_command: str
    drawing_speed_mm_s: float
    travel_speed_mm_s: float
    acceleration_mm_s2: float
    pen_slot_count: int
    supports_arcs: bool = False
    arc_tolerance_mm: float = 0.1
    ebb: EbbConfig | None = None


class LayerInfo(BaseModel):
    """A single separated drawing layer and its plotting parameters."""

    layer_id: str
    source_color: str
    target_pen_slot: int | None
    draw_order: int
    total_length_mm: float
    path_count: int
    bbox: BoundingBox
    optimize: bool = True
    simplify_tolerance_mm: float = 0.05
    drawing_speed_mm_s: float | None = None


class Job(BaseModel):
    """Tracks a single file through the conversion-to-plot lifecycle."""

    job_id: str = Field(default_factory=lambda: str(uuid4()))
    source_file: str
    source_mime: str
    profile_name: str
    layers: list[LayerInfo] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: Literal["pending", "processing", "ready", "running", "done", "error"] = "pending"

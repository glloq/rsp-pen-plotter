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


class Point(BaseModel):
    """A point in the machine's coordinate space, in profile units."""

    x: float
    y: float


class PenSlot(BaseModel):
    """A physical pen position in the machine's magazine."""

    index: int
    name: str = ""
    color: str = "#000000"
    installed: bool = True
    position: Point | None = None
    # Optional per-slot calibration: override the pen-up/pen-down commands for
    # this pen (e.g. a different servo depth). Falls back to the profile when
    # unset.
    pen_up_command: str | None = None
    pen_down_command: str | None = None


class EbbConfig(BaseModel):
    """EiBotBoard (AxiDraw-class) motion parameters.

    Required only for profiles whose ``gcode_dialect`` is ``"ebb"``. The two
    motors form an H-bot, so a Cartesian move maps to mixed motor steps.
    """

    steps_per_mm: float = Field(
        default=80.0, gt=0.0, description="Motor steps per millimeter of Cartesian travel."
    )
    servo_up: int = Field(
        default=16000,
        description="Servo pulse width for the pen-up position, in 83.3 ns units (EBB SP).",
    )
    servo_down: int = Field(
        default=12000,
        description="Servo pulse width for the pen-down position, in 83.3 ns units (EBB SP).",
    )
    servo_rate: int = Field(
        default=400, gt=0, description="Servo travel rate between up/down, in EBB SC units."
    )
    serial_terminator: Literal["cr", "lf", "crlf"] = Field(
        default="cr", description="Line terminator the board expects; EiBotBoard uses CR."
    )


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
    pens: list[PenSlot] | None = None

    def effective_pens(self) -> list[PenSlot]:
        """Return the configured magazine, deriving defaults when unset.

        Profiles that predate per-slot configuration only carry
        ``pen_slot_count``; in that case one default :class:`PenSlot` is
        synthesized per slot so callers always get a consistent list.
        """
        if self.pens:
            return self.pens
        return [PenSlot(index=i, name=f"Pen {i}") for i in range(self.pen_slot_count)]


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


class PreflightReport(BaseModel):
    """Pre-run safety and estimation checks for a placed drawing."""

    ok: bool
    within_bounds: bool
    width_mm: float
    height_mm: float
    scale: float
    drawing_length_mm: float
    travel_length_mm: float
    estimated_seconds: float
    pen_changes: int
    layer_count: int
    path_count: int
    missing_pen_slots: list[int] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Macro(BaseModel):
    """A user-defined sequence of raw plotter commands triggerable as one action."""

    # Names address the macro in the URL path (/macros/{name}/run), so they must
    # stay within a single path segment: no slashes or control characters.
    name: str = Field(min_length=1, pattern=r"^[\w \-.]+$")
    description: str = ""
    commands: list[str] = Field(default_factory=list)


class Job(BaseModel):
    """Tracks a single file through the conversion-to-plot lifecycle."""

    job_id: str = Field(default_factory=lambda: str(uuid4()))
    source_file: str
    source_mime: str
    profile_name: str
    layers: list[LayerInfo] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: Literal["pending", "processing", "ready", "running", "done", "error"] = "pending"

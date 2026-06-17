"""Shared Pydantic data contracts for the OmniPlot pipeline.

These models are the stable contracts every later phase relies on: machine
profiles describe target hardware, layers describe separated drawing content,
and jobs track a single conversion-to-plot lifecycle.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from pen_plotter.domain.capability import MachineCapabilities, derive_capabilities


class WorkspaceBounds(BaseModel):
    """Rectangular drawable area of a machine, expressed in profile units."""

    x_min: float
    y_min: float
    x_max: float
    y_max: float


class Placement(BaseModel):
    """Sheet placement inside the machine workspace.

    The sheet is the physical paper the operator has loaded; it can be smaller
    than the machine workspace. ``offset_x_mm`` / ``offset_y_mm`` position the
    sheet's top-left corner inside the workspace (relative to ``workspace.x_min``
    / ``y_min``). When omitted from the API, generation falls back to using the
    workspace itself as the drawable region — preserves backwards compat.
    """

    sheet_width_mm: float = Field(gt=0.0)
    sheet_height_mm: float = Field(gt=0.0)
    offset_x_mm: float = 0.0
    offset_y_mm: float = 0.0


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
    # Optional per-pen XY offset (machine mm) added to every stroke drawn with
    # this pen, compensating for where this pen's tip sits relative to the
    # reference pen so multi-pen layers register against one origin. Applied
    # ONLY when the profile opts in via ``apply_pen_offsets``; defaults to
    # (0, 0) so offset-unaware magazines emit byte-identical G-code. See
    # ``docs/camera_tip_offset.md`` / ADR 0005.
    xy_offset_mm: Point = Field(default_factory=lambda: Point(x=0.0, y=0.0))
    # Provenance of ``xy_offset_mm`` so the UI can distinguish a hand-typed
    # value from a (future) camera measurement and prompt re-measurement.
    offset_source: Literal["unset", "manual", "vision"] = "unset"


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


class TipCameraRoi(BaseModel):
    """Pixel region of the camera frame where a presented tip will appear."""

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class TipCalibrationConfig(BaseModel):
    """Dedicated-station camera setup for measuring per-pen XY offsets.

    Optional on a profile; present only when the machine has a tip-measuring
    station wired up (ADR 0005, phase 2). The vision pipeline reuses the
    timelapse frame grabber against ``camera_url``. Offsets are measured
    *relative to* ``reference_slot``, so the absolute station-to-bed
    registration cancels out.
    """

    camera_url: str
    # Machine-coordinate point where a pen is presented to the station. Stored
    # for the (future) guided travel; not required to take a measurement.
    station_position: Point | None = None
    reference_slot: int = Field(default=0, ge=0)
    mm_per_pixel: float = Field(gt=0.0)
    detector: Literal["dark_blob"] = "dark_blob"
    # Luminance cutoff (0–255): pixels darker than this are taken as "tip".
    dark_threshold: int = Field(default=80, ge=0, le=255)
    roi: TipCameraRoi | None = None


class MachineProfile(BaseModel):
    """Describes a target pen plotter.

    All machine-specific behavior lives in profile files rather than code, so a
    new plotter can be supported by writing one of these (typically loaded from
    YAML) without touching the application.
    """

    name: str
    units: Literal["mm", "inch"]
    workspace: WorkspaceBounds
    origin: Literal["top_left", "bottom_left"]
    gcode_dialect: Literal["grbl", "marlin", "klipper", "ebb", "custom"]
    pen_up_command: str
    pen_down_command: str
    tool_change_method: Literal["manual_pause", "carousel", "rack", "none"]
    tool_change_command: str
    drawing_speed_mm_s: float
    travel_speed_mm_s: float
    acceleration_mm_s2: float
    # Time (ms) for one pen lift or one pen drop — i.e. how long the
    # servo / solenoid takes to physically settle after the up/down
    # command is sent. Two transitions happen per drawn polyline
    # (down at start, up at end), and on a drawing with many short
    # strokes this dominates the wall-clock time: ignoring it makes
    # the preflight estimate optimistic by several minutes.
    # 0 = instant (steppered Z-axis, solenoid that lands during
    # the next move). Typical SG90/EBB servos sit around 150–250 ms.
    pen_lift_time_ms: float = Field(default=0.0, ge=0.0)
    pen_slot_count: int
    supports_arcs: bool = False
    arc_tolerance_mm: float = 0.1
    ebb: EbbConfig | None = None
    pens: list[PenSlot] | None = None
    # Machine-coordinate point the head parks at before a *manual* pen swap
    # (``manual_pause`` mode) or a magazine load pause, so the operator can
    # reach the holder without the head sitting over the drawing. ``None``
    # falls back to the workspace home corner (``x_min`` / ``y_min``).
    # Carousel / rack profiles ignore this — they travel to the calibrated
    # slot position (carousel) or drive their own swap macro (rack) instead.
    pen_change_position: Point | None = None
    # Opt-in switch for per-pen XY tip-offset compensation. When ``True`` each
    # pen's :attr:`PenSlot.xy_offset_mm` is added to its strokes during G-code
    # generation so different pens register against one origin. Defaults to
    # ``False`` so existing profiles emit byte-identical G-code — the feature
    # is strictly opt-in (the operator chooses to turn it on). See
    # ``docs/camera_tip_offset.md`` / ADR 0005.
    apply_pen_offsets: bool = False
    # Optional dedicated-station camera setup for measuring per-pen offsets
    # automatically (ADR 0005, phase 2). When present, the magazine editor
    # surfaces a "Measure" action per slot. ``None`` → manual entry only.
    tip_calibration: TipCalibrationConfig | None = None
    # v0.2 Capability Model (roadmap A.5). Optional in YAML — when
    # absent we derive a default from ``tool_change_method`` so legacy
    # profiles load unchanged. When set, the explicit block wins and
    # the orchestrator (roadmap B.2) routes through it.
    capabilities: MachineCapabilities | None = None

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_fields(cls, data: Any) -> Any:
        """Coerce retired field values so older profiles keep loading.

        ``origin: "center"`` was only ever treated as ``"bottom_left"`` (a Y-axis
        flip with no real re-centring), so map it forward to preserve behaviour
        now that the canonical set is ``top_left`` / ``bottom_left``.
        """
        if isinstance(data, dict) and data.get("origin") == "center":
            data = {**data, "origin": "bottom_left"}
        return data

    @model_validator(mode="after")
    def _populate_capabilities(self) -> MachineProfile:
        """Derive capabilities from legacy fields when not set explicitly."""
        if self.capabilities is None:
            self.capabilities = derive_capabilities(self.tool_change_method, self.pen_slot_count)
        return self

    def effective_capabilities(self) -> MachineCapabilities:
        """Return the resolved capability block (never ``None``)."""
        if self.capabilities is None:
            self.capabilities = derive_capabilities(self.tool_change_method, self.pen_slot_count)
        return self.capabilities

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
    # Editable operator label for the colour, surfaced in the pause prompt
    # ("Change pen to {color_label}"). Falls back to ``source_color`` when
    # ``None`` so legacy jobs deserialize cleanly.
    color_label: str | None = None
    # Pause policy for the *beginning* of this layer:
    #   - "auto": pause if the slot/colour differs from the previous layer
    #     (the existing default behaviour, plus colour-change tracking for
    #     mono-pen machines);
    #   - "always": always insert a pause (useful when an operator wants a
    #     break on a layer of the same colour);
    #   - "never": never pause, even if the slot or colour changed.
    pause_before: Literal["auto", "always", "never"] = "auto"
    # Operator-facing colour pick: which hex from the active pool (pens /
    # available / union) this layer should be drawn with. Populated by the
    # auto-attribution step at /upload + /rerender time using the cluster
    # centroid's nearest match (CIE Lab ΔE). The operator can override it
    # per layer through the editor's picker. ``None`` falls back to
    # ``source_color`` — the legacy path stays intact for placements that
    # predate the assignment surface.
    assigned_color_hex: str | None = None
    # Tracks whether the current ``assigned_color_hex`` came from the
    # auto-nearest step or from a manual operator override. Used by the
    # "↻ reset to auto" affordance on the layer card so re-running the
    # auto step is idempotent: it skips layers the operator pinned and
    # only refreshes ``"auto"`` rows.
    color_assignment: Literal["auto", "manual"] = "auto"
    # Visual opacity applied at render time (0 = invisible, 100 = solid).
    # Distinct from ``visible``: opacity-50 still plots but with the SVG
    # ``stroke-opacity`` attribute halved, so the preview previews the
    # lighter density a future watercolor / dilute-ink pass would
    # produce. The G-code generator doesn't consume this — opacity is a
    # *preview* hint, not a hardware parameter. Defaults to 100 so
    # legacy placements deserialize without the field.
    opacity_percent: int = Field(default=100, ge=0, le=100)


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
    # Stable hash of the resolved plan that produced this report. Lets the
    # frontend correlate a preflight result with the matching ``/generate``
    # call: both endpoints route through ``resolve_plan`` so equal inputs
    # MUST yield equal hashes. Optional so historical callers that don't
    # mind the field keep deserialising.
    plan_hash: str | None = None


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

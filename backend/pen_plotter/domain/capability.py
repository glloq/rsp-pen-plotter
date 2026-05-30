"""Capability Model for machine profiles (roadmap A.5).

Audit #2 calls out the v0.1 ``tool_change_method`` literal as too thin:
it conflates *how the swap happens* (firmware, host macro, manual,
none) with *who emits the command* (machine, host, operator) and with
*how recovery works* if the swap fails mid-run.

The v0.2 model splits those concerns:

- :class:`ToolingMode`   — the **strategy** the orchestrator runs.
- :class:`CommandSource` — who actually emits the commands.
- :class:`RecoveryPolicy` — what happens when the swap fails or the
  operator aborts mid-swap.
- :class:`ToolChangeStrategy` — bundles the three above plus
  strategy-specific knobs (macros, prompts, timeouts).
- :class:`MachineCapabilities` — top-level container; carries the
  strategy plus any future capability flags (magazine slots, sheet
  feed, sensors, …).

These types are introduced **additively**: the new
``capabilities`` field on :class:`MachineProfile` is optional, and a
default is derived from the legacy ``tool_change_method`` so every
existing profile keeps loading without warning. Operators who want
explicit control can populate ``capabilities`` in their YAML.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class ToolingMode(StrEnum):
    """Top-level orchestration strategy (audit #2)."""

    FIRMWARE = "firmware"
    """The microcontroller's firmware handles the tool change directly."""

    HOST_MACRO = "host_macro"
    """The host emits a YAML-defined macro sequence (G-code / EBB)."""

    MANUAL = "manual"
    """The machine parks, the operator swaps the pen, then confirms."""

    SINGLE_PEN = "single_pen"
    """No tool change — mono-pen workflow."""


class CommandSource(StrEnum):
    """Who emits the actual commands for the swap."""

    MACHINE = "machine"
    HOST = "host"
    OPERATOR = "operator"


class RecoveryPolicy(StrEnum):
    """What happens when a swap fails or is aborted mid-flight."""

    ABORT = "abort"
    """Abort the run and surface the failure to the operator."""

    PAUSE_AND_PROMPT = "pause_and_prompt"
    """Pause indefinitely and let the operator resolve, then resume."""

    SKIP_LAYER = "skip_layer"
    """Skip the offending layer and continue with the next."""


class ManualSwapPrompt(BaseModel):
    """Operator-facing prompt template used by :class:`ToolingMode.MANUAL`.

    Three optional bodies cover the two real-world scenarios:
    - ``multipen_body``: slot-based prompt for multi-pen profiles
      (carousel / rack with explicit slot index). Substitutions:
      ``{slot}``, ``{label}``, ``{color}``, ``{layer}``.
    - ``monopen_body``: color-based prompt for mono-pen profiles
      where the operator swaps the pen between layers. Same
      substitutions; ``{slot}`` is empty for mono-pen.
    - ``body``: legacy fallback when neither of the above is set
      (kept for back-compat with v0.1 profile YAMLs).

    The strategy picks the right body for each ``SwapContext``
    based on ``context.slot_index`` — None → mono, non-None → multi.
    """

    title: str = "Change pen"
    body: str = "Insert pen {color} into the holder, then press Resume."
    multipen_body: str | None = None
    monopen_body: str | None = None
    timeout_s: int | None = None


class HostMacroStep(BaseModel):
    """One line of a host-emitted swap macro.

    ``send`` is a literal command line written verbatim to the
    transport; ``wait_ms`` is an optional pause **after** the send.
    """

    send: str
    wait_ms: int = 0


class HostSwapStep(BaseModel):
    """One high-level step of a host-driven pen swap.

    The operator builds the swap from these blocks instead of writing
    G-code; :class:`~pen_plotter.domain.toolchange.strategies.HostMacroStrategy`
    compiles them to concrete commands at plan time, filling in each
    pen's calibrated position. ``raw`` is the escape hatch for exotic
    hardware.

    Kinds:
      - ``head_up`` / ``head_down``: emit the profile pen-up/-down command.
      - ``grab`` / ``release``: emit the plan's ``grab_command`` /
        ``drop_command`` (the clamp / gripper primitive). On a ``dock``
        mechanism these mean lock / unlock the coupling; with
        ``lock_mode == "motion"`` they emit nothing (the advance/retract
        motion is the lock).
      - ``move_to_old_slot`` / ``move_to_new_slot``: travel to the
        outgoing / incoming pen's *approach* point (the slot position
        offset by the clearance vector), safe for lateral motion.
      - ``advance_to_slot`` / ``retract_from_slot``: move in/out of the
        slot along the clearance vector (approach ↔ engagement) so the
        head doesn't crash the neighbouring pens. They act on the most
        recent ``move_to_*_slot``.
      - ``dwell``: pause ``wait_ms`` host-side (no command sent).
      - ``raw``: send ``send`` verbatim.
    """

    kind: Literal[
        "head_up",
        "head_down",
        "grab",
        "release",
        "move_to_old_slot",
        "move_to_new_slot",
        "advance_to_slot",
        "retract_from_slot",
        "dwell",
        "raw",
    ]
    # Host-side pause applied after the step (for ``dwell`` this is the
    # whole point; for the others it's an optional settle time).
    wait_ms: int = 0
    # Only meaningful for ``raw`` — the literal G-code line.
    send: str = ""


class HostSwapPlan(BaseModel):
    """Structured, G-code-free description of a host-driven pen swap.

    Stored on the profile and compiled to commands at plan time so the
    operator configures positions + actions, never raw G-code (except the
    optional ``raw`` step). ``grab_command`` / ``drop_command`` are the
    one machine primitive that needs a literal command (a servo / gripper
    line), surfaced under an "advanced" affordance with sane defaults.
    """

    # Which physical mechanism the host drives. Both compile through the
    # same step engine; the field selects the editor preset / labels and
    # (with ``lock_mode``) how the coupling is driven:
    #   - ``rack``: a single carriage tool-holder with a clamp/gripper that
    #     picks a pen out of / drops it into a linear rack (vertical engage).
    #   - ``dock``: a kinematic tool-changer — each pen+holder is a full
    #     tool parked in a fixed dock; the head couples to one at a time by
    #     sliding in/out horizontally (``advance``/``retract``), so the
    #     ``grab``/``release`` steps mean *lock*/*unlock* the coupling.
    mechanism: Literal["rack", "dock"] = "rack"
    # How a ``dock`` coupling is locked / unlocked:
    #   - ``command``: a servo / motorised latch — ``grab``/``release`` emit
    #     ``grab_command`` / ``drop_command``.
    #   - ``motion``: a purely kinematic / magnetic coupling — no command is
    #     sent; the lock *is* the advance/retract motion, so ``grab`` and
    #     ``release`` are suppressed at compile time even if a command is
    #     left over on the plan. Ignored for the ``rack`` mechanism.
    lock_mode: Literal["command", "motion"] = "command"
    grab_command: str = ""
    drop_command: str = ""
    # Feed for the magazine travel moves; falls back to the profile's
    # travel speed when unset.
    travel_speed_mm_s: float | None = None
    # Clearance vector for engaging / disengaging a slot. A pen's stored
    # ``position`` is its *engagement* point (where the gripper closes);
    # the *approach* point sits ``clearance_mm`` away from it along
    # ``clearance_axis`` in the ``clearance_dir`` direction. Lateral moves
    # between slots happen at the approach point so the head clears the
    # neighbouring pens; ``advance_to_slot`` / ``retract_from_slot`` travel
    # the short hop between the two. ``clearance_mm = 0`` disables the hop
    # (approach == engagement) for racks that need no insertion move.
    clearance_axis: Literal["x", "y"] = "y"
    clearance_dir: Literal["+", "-"] = "+"
    clearance_mm: float = 0.0
    # Optional servo positions for the *magazine* head height, used by the
    # ``head_up`` / ``head_down`` steps during a swap. The magazine often
    # sits higher than the paper, so the servo angle to raise above /
    # lower into the rack differs from the normal pen-up/-down. When set,
    # these take precedence over the profile's pen-up/-down commands; when
    # ``None`` the profile commands are used. ``safe_z_mm`` / ``engage_z_mm``
    # (below) win over both when the machine has a real Z axis.
    head_up_command: str | None = None
    head_down_command: str | None = None
    # Optional Z heights (mm) for machines with a real motorised Z axis.
    # ``safe_z`` is the travel height the head rises to before moving
    # between slots; ``engage_z`` is the depth it descends to inside the
    # magazine to grab / release a pen. When set, ``head_up`` / ``head_down``
    # emit ``G0 Z<height>``; otherwise the servo commands above (or the
    # profile's) are used — so simple servo machines need not touch these.
    safe_z_mm: float | None = None
    engage_z_mm: float | None = None
    # Machine Z travel limits (mm), informational — the editor warns when a
    # height falls outside, but generation does not clamp.
    z_min_mm: float | None = None
    z_max_mm: float | None = None
    steps: list[HostSwapStep] = Field(default_factory=list)


class ToolChangeStrategy(BaseModel):
    """Bundles the swap mode and its strategy-specific knobs."""

    mode: ToolingMode = ToolingMode.MANUAL
    command_source: CommandSource = CommandSource.OPERATOR
    recovery_policy: RecoveryPolicy = RecoveryPolicy.PAUSE_AND_PROMPT
    manual_prompt: ManualSwapPrompt | None = None
    host_macro: list[HostMacroStep] = Field(default_factory=list)
    # Structured visual swap builder (preferred for host magazines). When
    # set with steps, the strategy compiles it instead of ``host_macro``.
    host_swap: HostSwapPlan | None = None


class MachineCapabilities(BaseModel):
    """Top-level capability container exposed on :class:`MachineProfile`."""

    tool_change: ToolChangeStrategy = Field(default_factory=ToolChangeStrategy)
    has_pen_sensor: bool = False
    has_sheet_loader: bool = False
    max_pens_in_magazine: int = 1


# Mapping from the legacy ``tool_change_method`` literal to the new
# (mode, command_source) pair. The recovery policy defaults to PAUSE
# in every case — the legacy behaviour was always to halt and wait for
# the operator.
_LEGACY_MAP: dict[str, tuple[ToolingMode, CommandSource]] = {
    "manual_pause": (ToolingMode.MANUAL, CommandSource.OPERATOR),
    "carousel": (ToolingMode.FIRMWARE, CommandSource.MACHINE),
    "rack": (ToolingMode.HOST_MACRO, CommandSource.HOST),
    "none": (ToolingMode.SINGLE_PEN, CommandSource.MACHINE),
}


_DEFAULT_MULTIPEN_BODY = "Insert pen slot {slot}: {label}"
"""Slot-based prompt format inherited from the v0.1 legacy regex.

The orchestrator emits this verbatim for any context that carries a
``slot_index``; matches the operator wording the runtime tests pin.
"""

_DEFAULT_MONOPEN_BODY = "Change pen to {label}"
"""Color-based prompt format for mono-pen profiles.

``pen_label`` is pre-computed by the comment parser to either
``"{label} ({color})"`` (when a human label exists) or ``"{color}"``
(when label and color collapse to the same hex), so this single
template covers both legacy outputs.
"""


def default_manual_prompt(pen_slot_count: int) -> ManualSwapPrompt:
    """Manual-swap template aligned with the legacy runtime prompts.

    Multi-pen profiles get the slot-based ``multipen_body``; all
    profiles get the color-based ``monopen_body`` so a mono-pen colour
    change still produces a usable prompt even on a multi-pen machine.
    The legacy ``body`` field stays at its v0.1 default so explicit
    consumers that ignore the new fields keep working.
    """
    return ManualSwapPrompt(
        multipen_body=_DEFAULT_MULTIPEN_BODY if pen_slot_count > 1 else None,
        monopen_body=_DEFAULT_MONOPEN_BODY,
    )


def derive_capabilities(
    tool_change_method: str,
    pen_slot_count: int,
) -> MachineCapabilities:
    """Derive a default :class:`MachineCapabilities` from legacy fields.

    Used during YAML migration so an existing profile that does not
    carry an explicit ``capabilities`` block still loads with a
    coherent strategy populated.
    """
    mode, source = _LEGACY_MAP.get(tool_change_method, (ToolingMode.MANUAL, CommandSource.OPERATOR))
    prompt = default_manual_prompt(pen_slot_count) if mode == ToolingMode.MANUAL else None
    strategy = ToolChangeStrategy(
        mode=mode,
        command_source=source,
        recovery_policy=RecoveryPolicy.PAUSE_AND_PROMPT,
        manual_prompt=prompt,
    )
    return MachineCapabilities(
        tool_change=strategy,
        max_pens_in_magazine=max(1, pen_slot_count),
    )

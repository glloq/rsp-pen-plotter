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


class ToolChangeStrategy(BaseModel):
    """Bundles the swap mode and its strategy-specific knobs."""

    mode: ToolingMode = ToolingMode.MANUAL
    command_source: CommandSource = CommandSource.OPERATOR
    recovery_policy: RecoveryPolicy = RecoveryPolicy.PAUSE_AND_PROMPT
    manual_prompt: ManualSwapPrompt | None = None
    host_macro: list[HostMacroStep] = Field(default_factory=list)


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

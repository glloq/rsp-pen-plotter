"""The four strategy implementations registered with the orchestrator."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from pen_plotter.domain.capability import (
    HostSwapPlan,
    MachineCapabilities,
    ManualSwapPrompt,
    ToolingMode,
)
from pen_plotter.domain.toolchange.orchestrator import (
    PauseKind,
    SwapCommand,
    SwapContext,
    SwapPlan,
)
from pen_plotter.models import MachineProfile


class ToolChangeStrategy(ABC):
    """Abstract base — implementations are stateless w.r.t. the swap event.

    The strategy receives the bound profile at construction so it can
    cache things like the legacy ``tool_change_command`` once.
    """

    mode: ClassVar[ToolingMode]

    def __init__(self, profile: MachineProfile) -> None:
        """Bind the strategy to a machine profile."""
        self.profile = profile

    @abstractmethod
    def plan(self, context: SwapContext, capabilities: MachineCapabilities) -> SwapPlan:
        """Produce the :class:`SwapPlan` for one swap event."""


class FirmwareStrategy(ToolChangeStrategy):
    """The firmware handles the swap; we only emit a trigger.

    Trigger source preference:
      1. ``capabilities.tool_change.host_macro`` (lets the operator
         override the legacy single-line trigger with an explicit
         sequence).
      2. ``profile.tool_change_command`` (legacy field).
    """

    mode: ClassVar[ToolingMode] = ToolingMode.FIRMWARE

    def plan(self, context: SwapContext, capabilities: MachineCapabilities) -> SwapPlan:
        """Emit the firmware trigger, then hand off to the controller."""
        macro = capabilities.tool_change.host_macro
        if macro:
            commands = [_render(step.send, context, step.wait_ms) for step in macro]
        else:
            trigger = self.profile.tool_change_command.strip() or "M6"
            commands = [SwapCommand(send=_substitute(trigger, context))]
        return SwapPlan(
            mode=self.mode,
            pause_kind=PauseKind.FIRMWARE,
            commands=commands,
            recovery_policy=capabilities.tool_change.recovery_policy,
        )


class HostMacroStrategy(ToolChangeStrategy):
    """The host emits a swap sequence.

    Two authoring paths, in preference order:
      1. ``host_swap`` — the structured, G-code-free visual builder
         (move-to-slot / grab / release / head up-down / dwell), compiled
         here using each pen's calibrated position.
      2. ``host_macro`` — a raw G-code line list (legacy / power users).
    """

    mode: ClassVar[ToolingMode] = ToolingMode.HOST_MACRO

    def plan(self, context: SwapContext, capabilities: MachineCapabilities) -> SwapPlan:
        """Compile the structured swap (preferred) or render the raw macro."""
        tc = capabilities.tool_change
        if tc.host_swap is not None and tc.host_swap.steps:
            commands = self._compile_swap(tc.host_swap, context)
        elif tc.host_macro:
            commands = [_render(step.send, context, step.wait_ms) for step in tc.host_macro]
        else:
            raise ValueError(
                "ToolingMode.HOST_MACRO requires capabilities.tool_change.host_swap "
                "(steps) or host_macro to be set; profile is missing the swap definition."
            )
        return SwapPlan(
            mode=self.mode,
            pause_kind=PauseKind.HOST_TIMED,
            commands=commands,
            recovery_policy=tc.recovery_policy,
        )

    def _compile_swap(self, swap: HostSwapPlan, context: SwapContext) -> list[SwapCommand]:
        """Turn high-level swap steps into concrete G-code commands.

        Per-pen positions come from the bound profile's magazine, the
        pen-up/-down primitives from the profile, and grab/release from
        the plan. A ``dwell`` adds host-side wait without sending a line;
        a step whose action can't be produced (e.g. an uncalibrated slot)
        is skipped but keeps its settle time.
        """
        pens = {pen.index: pen for pen in self.profile.effective_pens()}
        travel_feed = (swap.travel_speed_mm_s or self.profile.travel_speed_mm_s) * 60.0
        out: list[SwapCommand] = []
        lead_wait = 0

        def emit(send: str, wait_ms: int) -> None:
            nonlocal lead_wait
            out.append(SwapCommand(send=send, wait_ms=wait_ms + lead_wait))
            lead_wait = 0

        for step in swap.steps:
            if step.kind == "dwell":
                if out:
                    out[-1].wait_ms += step.wait_ms
                else:
                    lead_wait += step.wait_ms
                continue

            send: str | None = None
            if step.kind == "head_up":
                # Real Z axis: rise to the safe travel height. Otherwise
                # fall back to the servo pen-up command.
                send = (
                    f"G0 Z{swap.safe_z_mm:.3f} F{travel_feed:.1f}"
                    if swap.safe_z_mm is not None
                    else self.profile.pen_up_command
                )
            elif step.kind == "head_down":
                # Real Z axis: descend to the engage depth inside the
                # magazine. Otherwise the servo pen-down command.
                send = (
                    f"G0 Z{swap.engage_z_mm:.3f} F{travel_feed:.1f}"
                    if swap.engage_z_mm is not None
                    else self.profile.pen_down_command
                )
            elif step.kind == "grab":
                send = (
                    _substitute(swap.grab_command, context) if swap.grab_command.strip() else None
                )
            elif step.kind == "release":
                send = (
                    _substitute(swap.drop_command, context) if swap.drop_command.strip() else None
                )
            elif step.kind in ("move_to_old_slot", "move_to_new_slot"):
                slot = (
                    context.from_slot_index
                    if step.kind == "move_to_old_slot"
                    else context.slot_index
                )
                pen = pens.get(slot) if slot is not None else None
                if pen is not None and pen.position is not None:
                    send = f"G0 X{pen.position.x:.3f} Y{pen.position.y:.3f} F{travel_feed:.1f}"
            elif step.kind == "raw":
                send = _substitute(step.send, context) if step.send.strip() else None

            if send is not None:
                emit(send, step.wait_ms)
            elif step.wait_ms and out:
                out[-1].wait_ms += step.wait_ms

        return out


class ManualStrategy(ToolChangeStrategy):
    """The machine parks, the UI prompts, the operator confirms.

    The operator-facing message is rendered from the
    :class:`ManualSwapPrompt` template on the profile (or the v0.2
    default if none is set). Placeholders ``{color}``, ``{slot}``,
    ``{label}``, ``{layer}`` are substituted from the
    :class:`SwapContext`.
    """

    mode: ClassVar[ToolingMode] = ToolingMode.MANUAL

    def plan(self, context: SwapContext, capabilities: MachineCapabilities) -> SwapPlan:
        """Park the machine, build the operator prompt, request a confirm."""
        prompt_template = capabilities.tool_change.manual_prompt or ManualSwapPrompt()
        prompt = _format_prompt(prompt_template, context)
        return SwapPlan(
            mode=self.mode,
            pause_kind=PauseKind.OPERATOR_CONFIRM,
            commands=[],
            operator_prompt=prompt,
            recovery_policy=capabilities.tool_change.recovery_policy,
            timeout_s=prompt_template.timeout_s,
        )


class SinglePenStrategy(ToolChangeStrategy):
    """Mono-pen workflow — no swap, no pause, no commands."""

    mode: ClassVar[ToolingMode] = ToolingMode.SINGLE_PEN

    def plan(self, context: SwapContext, capabilities: MachineCapabilities) -> SwapPlan:
        """Return an empty plan; the streamer just keeps going."""
        return SwapPlan(
            mode=self.mode,
            pause_kind=PauseKind.NONE,
            commands=[],
            recovery_policy=capabilities.tool_change.recovery_policy,
        )


_STRATEGIES: dict[ToolingMode, type[ToolChangeStrategy]] = {
    ToolingMode.FIRMWARE: FirmwareStrategy,
    ToolingMode.HOST_MACRO: HostMacroStrategy,
    ToolingMode.MANUAL: ManualStrategy,
    ToolingMode.SINGLE_PEN: SinglePenStrategy,
}


def for_mode(mode: ToolingMode) -> type[ToolChangeStrategy]:
    """Return the strategy class registered for ``mode``."""
    return _STRATEGIES[mode]


# ── helpers ──────────────────────────────────────────────────────────


def _substitute(template: str, context: SwapContext) -> str:
    """Substitute the swap-context placeholders into a single line."""
    slot = "" if context.slot_index is None else str(context.slot_index)
    return (
        template.replace("{slot}", slot)
        .replace("{color}", context.pen_color)
        .replace("{label}", context.pen_label or context.pen_color)
        .replace("{layer}", context.layer_id)
    )


def _render(send_template: str, context: SwapContext, wait_ms: int) -> SwapCommand:
    return SwapCommand(send=_substitute(send_template, context), wait_ms=wait_ms)


def _format_prompt(template: ManualSwapPrompt, context: SwapContext) -> str:
    # Pick the right body for the context: ``slot_index`` set → the
    # operator is performing a slot-based swap on a multi-pen
    # machine; not set → a colour-only swap on a mono-pen machine.
    # The template's ``multipen_body``/``monopen_body`` fields cover
    # the two cases; we fall through to the legacy ``body`` when
    # neither is configured so v0.1 profiles still work.
    if context.slot_index is not None and template.multipen_body:
        chosen = template.multipen_body
    elif context.slot_index is None and template.monopen_body:
        chosen = template.monopen_body
    else:
        chosen = template.body
    body = _substitute(chosen, context)
    title = _substitute(template.title, context)
    if title and title != "Change pen":
        return f"{title} — {body}"
    return body

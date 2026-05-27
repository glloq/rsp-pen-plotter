"""Top-level orchestrator + the shared :class:`SwapPlan` contract."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from pen_plotter.domain.capability import (
    MachineCapabilities,
    RecoveryPolicy,
    ToolingMode,
)
from pen_plotter.models import MachineProfile


class PauseKind(StrEnum):
    """How the streamer is expected to pause for this swap, if at all."""

    NONE = "none"
    """No pause — the swap (if any) happens inline through emitted commands."""

    FIRMWARE = "firmware"
    """Emit the trigger and let the firmware handle the pause itself."""

    HOST_TIMED = "host_timed"
    """Stream commands with explicit ``wait_ms`` between them."""

    OPERATOR_CONFIRM = "operator_confirm"
    """Halt streaming and wait for the operator to confirm via the UI."""


class SwapCommand(BaseModel):
    """One line of output for a swap, with optional dwell after sending."""

    send: str
    wait_ms: int = 0


class SwapContext(BaseModel):
    """Inputs the orchestrator needs to plan one swap.

    The exact identity of the next pen is intentionally **opaque**:
    consumers pass whatever label / hex / slot the UI knows about,
    and the strategy decides what to do with it (substitute into a
    prompt, into a macro template, drop on the floor, etc.).
    """

    slot_index: int | None = None
    pen_label: str = ""
    pen_color: str = ""
    layer_id: str = ""


class SwapPlan(BaseModel):
    """Uniform description of what the streamer should do at a swap point."""

    mode: ToolingMode
    pause_kind: PauseKind
    commands: list[SwapCommand] = Field(default_factory=list)
    operator_prompt: str | None = None
    """Set when ``pause_kind == OPERATOR_CONFIRM``."""

    recovery_policy: RecoveryPolicy
    timeout_s: int | None = None


class ToolChangeOrchestrator:
    """Selects a strategy based on the profile's capabilities.

    The orchestrator is stateless; it can be reused across jobs.
    Strategies are looked up once by mode and may carry per-machine
    state (e.g. cached templates) inside the instance.
    """

    def __init__(self, profile: MachineProfile) -> None:
        """Bind the orchestrator to a machine profile."""
        from pen_plotter.domain.toolchange.strategies import for_mode

        caps: MachineCapabilities = profile.effective_capabilities()
        self.profile = profile
        self.capabilities = caps
        self._strategy = for_mode(caps.tool_change.mode)(profile)

    @property
    def mode(self) -> ToolingMode:
        """Return the active strategy's :class:`ToolingMode`."""
        return self.capabilities.tool_change.mode

    def plan(self, context: SwapContext) -> SwapPlan:
        """Produce the :class:`SwapPlan` for a single swap event."""
        return self._strategy.plan(context, self.capabilities)

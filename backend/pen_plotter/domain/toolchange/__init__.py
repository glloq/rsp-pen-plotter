"""Tool-change orchestrator + four strategies (roadmap B.2 / audit #2).

Audit #2 calls out four distinct ways a swap can happen, each with its
own command source and operator interaction model:

- **Firmware** — the controller's firmware handles it (e.g. an M6 / T<n>
  on a CNC-class carousel). The host just emits the trigger.
- **Host macro** — the host emits a YAML-defined macro sequence
  (multiple lines + waits) and lets the firmware execute them.
- **Manual** — the machine parks, the operator swaps the pen, then
  confirms via the UI before streaming resumes.
- **Single pen** — no swap at all (mono-pen workflow).

The :class:`ToolChangeOrchestrator` reads the
:class:`pen_plotter.domain.capability.MachineCapabilities` block on
the profile and routes through the right strategy. Consumers (queue,
streamer, UI) only see :class:`SwapPlan` — a uniform description of
what to send, how to pause, what to show the operator.
"""

from __future__ import annotations

from pen_plotter.domain.toolchange.orchestrator import (
    PauseKind,
    SwapContext,
    SwapPlan,
    ToolChangeOrchestrator,
)
from pen_plotter.domain.toolchange.strategies import (
    FirmwareStrategy,
    HostMacroStrategy,
    ManualStrategy,
    SinglePenStrategy,
)
from pen_plotter.domain.toolchange.strategies import (
    ToolChangeStrategy as ToolChangeStrategyBase,
)

__all__ = [
    "FirmwareStrategy",
    "HostMacroStrategy",
    "ManualStrategy",
    "PauseKind",
    "SinglePenStrategy",
    "SwapContext",
    "SwapPlan",
    "ToolChangeOrchestrator",
    "ToolChangeStrategyBase",
]

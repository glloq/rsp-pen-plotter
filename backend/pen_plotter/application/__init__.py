"""Use-case services that sit between API adapters and the core engines.

The endpoints under ``adapters/api`` (and the legacy ``api/`` package)
should not import from ``core`` directly anymore — they hand a
:class:`PrintPlan` to a service, which resolves defaults, validates
invariants, calls the engine and returns the result alongside the
resolved snapshot used for traceability.
"""

from pen_plotter.application.generate_service import (
    GenerateOutcome,
    run_generate,
)
from pen_plotter.application.plan_resolver import (
    PlanResolutionError,
    resolve_plan,
)
from pen_plotter.application.preflight_service import (
    PreflightOutcome,
    run_preflight,
)

__all__ = [
    "GenerateOutcome",
    "PlanResolutionError",
    "PreflightOutcome",
    "resolve_plan",
    "run_generate",
    "run_preflight",
]

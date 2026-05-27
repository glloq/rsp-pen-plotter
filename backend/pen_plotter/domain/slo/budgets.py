"""SLO budgets table + evaluator.

A budget is a constraint of the form "p95 of metric ``X`` must stay
under ``Y`` ms". The evaluator counts how many samples breach the
threshold and returns one of three statuses:

- ``healthy``  — no breach.
- ``warning``  — breach rate ≤ ``warn_breach_ratio`` (default 5 %).
- ``breach``   — breach rate above the warning threshold.

Budget values are **calibrated from the perf baseline** captured in
roadmap D.2. Adjusting them requires updating the perf-report.
"""

from __future__ import annotations

import logging
from enum import StrEnum

from pydantic import BaseModel, Field

from pen_plotter.observability import bind_context, clear_context

_log = logging.getLogger("pen_plotter.slo")


class Severity(StrEnum):
    """Outcome of evaluating one budget."""

    HEALTHY = "healthy"
    WARNING = "warning"
    BREACH = "breach"


class MetricSample(BaseModel):
    """One measured value of a metric (ms unless otherwise noted)."""

    metric: str
    value_ms: float = Field(ge=0)


class Budget(BaseModel):
    """One SLO row."""

    metric: str
    label: str
    p95_ms: float = Field(gt=0)
    """The threshold the p95 must stay under."""

    min_samples: int = Field(ge=1, default=10)
    """No verdict until at least this many samples land — avoids
    alerting on a single slow request after a fresh deploy."""

    warn_breach_ratio: float = Field(ge=0, le=1, default=0.05)
    alert_on_breach: bool = True


class BudgetStatus(BaseModel):
    """Result of evaluating one budget."""

    budget: Budget
    severity: Severity
    observed_p95_ms: float = 0.0
    breach_count: int = 0
    sample_count: int = 0


class BudgetReport(BaseModel):
    """The dashboard payload — all budgets + a roll-up severity."""

    statuses: list[BudgetStatus]
    overall: Severity


# Budgets calibrated from docs/perf-baseline.md + docs/perf-report.md
# entry-state. They're deliberately on the loose side so the first
# alerts don't drown the team; tighten as quick wins from D.2 land.
DEFAULT_BUDGETS: list[Budget] = [
    Budget(
        metric="preview.draft",
        label="Preview (draft) p95",
        p95_ms=600.0,
    ),
    Budget(
        metric="preview.standard",
        label="Preview (standard) p95",
        p95_ms=1500.0,
    ),
    Budget(
        metric="preview.final",
        label="Preview (final) p95",
        p95_ms=4000.0,
    ),
    Budget(
        metric="upload.editable",
        label="Upload → first editable result p95",
        p95_ms=1500.0,
    ),
    Budget(
        metric="gcode.generate",
        label="Generate G-code p95",
        p95_ms=400.0,
    ),
    Budget(
        metric="queue.start_delay",
        label="Queue start delay p95 (machine idle)",
        p95_ms=2000.0,
    ),
    Budget(
        metric="stream.stall_timeout",
        label="Streaming stall timeout max",
        p95_ms=10_000.0,
        min_samples=1,
        warn_breach_ratio=0.0,
    ),
]


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, int(round((p / 100) * (len(ordered) - 1)))))
    return ordered[k]


def evaluate_budget(budget: Budget, samples: list[MetricSample]) -> BudgetStatus:
    """Evaluate one budget against its samples."""
    relevant = [s.value_ms for s in samples if s.metric == budget.metric]
    if len(relevant) < budget.min_samples:
        return BudgetStatus(
            budget=budget,
            severity=Severity.HEALTHY,
            sample_count=len(relevant),
        )
    p95 = _percentile(relevant, 95)
    breaches = sum(1 for v in relevant if v > budget.p95_ms)
    breach_ratio = breaches / len(relevant) if relevant else 0.0
    if breach_ratio == 0.0:
        severity = Severity.HEALTHY
    elif breach_ratio <= budget.warn_breach_ratio:
        severity = Severity.WARNING
    else:
        severity = Severity.BREACH
    return BudgetStatus(
        budget=budget,
        severity=severity,
        observed_p95_ms=p95,
        breach_count=breaches,
        sample_count=len(relevant),
    )


def evaluate_budgets(
    samples: list[MetricSample], budgets: list[Budget] | None = None
) -> BudgetReport:
    """Evaluate every budget; raise a structured alert per breach."""
    table = budgets if budgets is not None else DEFAULT_BUDGETS
    statuses = [evaluate_budget(b, samples) for b in table]

    overall = Severity.HEALTHY
    for status in statuses:
        if status.severity is Severity.BREACH:
            overall = Severity.BREACH
            if status.budget.alert_on_breach:
                tokens = bind_context()
                try:
                    _log.warning(
                        "slo_breach",
                        extra={
                            "metric": status.budget.metric,
                            "label": status.budget.label,
                            "observed_p95_ms": status.observed_p95_ms,
                            "threshold_ms": status.budget.p95_ms,
                            "breach_count": status.breach_count,
                            "sample_count": status.sample_count,
                        },
                    )
                finally:
                    clear_context(tokens)
        elif status.severity is Severity.WARNING and overall is Severity.HEALTHY:
            overall = Severity.WARNING

    return BudgetReport(statuses=statuses, overall=overall)

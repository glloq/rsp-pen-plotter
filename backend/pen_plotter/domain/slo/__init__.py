"""Service Level Objectives + budget evaluation (roadmap D.4).

Audit #6 calls out a fixed set of SLOs to enforce:
- preview draft / standard / final p95 budgets
- upload → first editable result p95
- generate gcode p95 on a reference fixture
- queue start delay p95 on an idle machine
- streaming stall timeout max

This module owns the **schema** + **evaluator**. The data source is
the v0.2 perf samples (frontend `usePerfStore` for UX metrics, OTel
spans for backend metrics). The evaluator is pure: given a list of
``MetricSample`` and the budget table, it returns a ``BudgetReport``
the dashboard renders.

Alerting is intentionally **declarative**: a budget marked
``alert_on_breach`` raises a structured log line via the A.1 logger
when the evaluator returns a ``breach``. Routing that to an external
alertmanager / pagerduty / email is left to the deployment layer
(``OMNIPLOT_OTLP_ENDPOINT`` already covers the OTel side).
"""

from __future__ import annotations

from pen_plotter.domain.slo.budgets import (
    DEFAULT_BUDGETS,
    Budget,
    BudgetReport,
    BudgetStatus,
    MetricSample,
    Severity,
    evaluate_budget,
    evaluate_budgets,
)

__all__ = [
    "DEFAULT_BUDGETS",
    "Budget",
    "BudgetReport",
    "BudgetStatus",
    "MetricSample",
    "Severity",
    "evaluate_budget",
    "evaluate_budgets",
]

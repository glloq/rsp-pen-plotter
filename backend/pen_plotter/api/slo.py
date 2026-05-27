"""HTTP surface for the SLO budget evaluator (roadmap D.4)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from pen_plotter.domain.slo import (
    DEFAULT_BUDGETS,
    Budget,
    BudgetReport,
    MetricSample,
    evaluate_budgets,
    record_samples,
)

router = APIRouter()


class EvaluateRequest(BaseModel):
    """Payload for ``POST /slo/evaluate`` — accepts a sample list."""

    samples: list[MetricSample]
    budgets: list[Budget] | None = None


@router.get("/slo/budgets")
async def list_budgets() -> list[Budget]:
    """Return the configured SLO budget table.

    Used by the frontend dashboard to render the threshold rows even
    when there are no samples yet.
    """
    return DEFAULT_BUDGETS


@router.post("/slo/evaluate")
async def evaluate(request: EvaluateRequest) -> BudgetReport:
    """Evaluate the SLO budgets against ``request.samples``.

    Also feeds the samples into the runtime accumulator so the
    background evaluator (when enabled) sees the same data. A breach
    on an ``alert_on_breach=True`` budget emits one structured log
    line; the deployment is responsible for routing those to an
    external alertmanager.
    """
    record_samples(request.samples)
    return evaluate_budgets(request.samples, request.budgets)

"""Tests for the SLO budget evaluator + endpoint (roadmap D.4)."""

from __future__ import annotations

import logging

import httpx
import pytest
from httpx import ASGITransport

from pen_plotter.domain.slo import (
    DEFAULT_BUDGETS,
    Budget,
    MetricSample,
    Severity,
    evaluate_budget,
    evaluate_budgets,
)
from pen_plotter.main import app


def _samples(metric: str, values: list[float]) -> list[MetricSample]:
    return [MetricSample(metric=metric, value_ms=v) for v in values]


# ── evaluate_budget ──────────────────────────────────────────────────


def test_below_min_samples_stays_healthy() -> None:
    budget = Budget(metric="m", label="m", p95_ms=100, min_samples=10)
    status = evaluate_budget(budget, _samples("m", [9999] * 3))
    assert status.severity is Severity.HEALTHY
    assert status.sample_count == 3


def test_no_breach_stays_healthy() -> None:
    budget = Budget(metric="m", label="m", p95_ms=100, min_samples=4)
    status = evaluate_budget(budget, _samples("m", [50.0, 60.0, 70.0, 80.0]))
    assert status.severity is Severity.HEALTHY
    assert status.breach_count == 0


def test_warning_at_low_breach_rate() -> None:
    # 1 / 20 = 5 % — exactly at warn_breach_ratio.
    budget = Budget(metric="m", label="m", p95_ms=100, min_samples=10)
    values = [50.0] * 19 + [200.0]
    status = evaluate_budget(budget, _samples("m", values))
    assert status.severity is Severity.WARNING
    assert status.breach_count == 1


def test_breach_at_high_breach_rate() -> None:
    budget = Budget(metric="m", label="m", p95_ms=100, min_samples=10)
    values = [50.0] * 10 + [200.0] * 10
    status = evaluate_budget(budget, _samples("m", values))
    assert status.severity is Severity.BREACH
    assert status.breach_count == 10


def test_observed_p95_is_returned() -> None:
    budget = Budget(metric="m", label="m", p95_ms=100, min_samples=4)
    status = evaluate_budget(budget, _samples("m", [10.0, 20.0, 30.0, 40.0]))
    assert status.observed_p95_ms > 0


# ── evaluate_budgets roll-up ─────────────────────────────────────────


def test_evaluate_budgets_returns_one_status_per_budget() -> None:
    report = evaluate_budgets([], DEFAULT_BUDGETS)
    assert len(report.statuses) == len(DEFAULT_BUDGETS)
    assert report.overall is Severity.HEALTHY


def test_overall_breach_when_any_budget_breached() -> None:
    budgets = [
        Budget(metric="a", label="a", p95_ms=100, min_samples=4),
        Budget(metric="b", label="b", p95_ms=100, min_samples=4),
    ]
    samples = _samples("a", [50.0] * 4) + _samples("b", [200.0] * 4)
    report = evaluate_budgets(samples, budgets)
    assert report.overall is Severity.BREACH


def test_overall_warning_when_only_warnings() -> None:
    budgets = [Budget(metric="a", label="a", p95_ms=100, min_samples=10)]
    # 1/20 breach, warn ratio default 0.05 → warning, not breach.
    samples = _samples("a", [50.0] * 19 + [200.0])
    report = evaluate_budgets(samples, budgets)
    assert report.overall is Severity.WARNING


def test_breach_emits_structured_log(caplog: pytest.LogCaptureFixture) -> None:
    budgets = [
        Budget(
            metric="a",
            label="A budget",
            p95_ms=100,
            min_samples=4,
            alert_on_breach=True,
        ),
    ]
    samples = _samples("a", [200.0] * 4)
    caplog.set_level(logging.WARNING, logger="pen_plotter.slo")
    evaluate_budgets(samples, budgets)
    assert any(r.message == "slo_breach" for r in caplog.records)
    record = next(r for r in caplog.records if r.message == "slo_breach")
    assert record.metric == "a"  # type: ignore[attr-defined]
    assert record.threshold_ms == 100  # type: ignore[attr-defined]


def test_alert_on_breach_false_suppresses_log(caplog: pytest.LogCaptureFixture) -> None:
    budgets = [
        Budget(
            metric="a",
            label="A budget",
            p95_ms=100,
            min_samples=4,
            alert_on_breach=False,
        ),
    ]
    samples = _samples("a", [200.0] * 4)
    caplog.set_level(logging.WARNING, logger="pen_plotter.slo")
    evaluate_budgets(samples, budgets)
    assert all(r.message != "slo_breach" for r in caplog.records)


# ── HTTP surface ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_slo_budgets_returns_defaults() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/slo/budgets")
    assert response.status_code == 200
    metrics = {row["metric"] for row in response.json()}
    assert "preview.draft" in metrics
    assert "gcode.generate" in metrics


@pytest.mark.asyncio
async def test_post_slo_evaluate_returns_report() -> None:
    transport = ASGITransport(app=app)
    samples = [
        {"metric": "preview.draft", "value_ms": 100.0},
        {"metric": "preview.draft", "value_ms": 200.0},
    ]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/slo/evaluate", json={"samples": samples})
    assert response.status_code == 200
    body = response.json()
    assert body["overall"] in {"healthy", "warning", "breach"}
    assert len(body["statuses"]) == len(DEFAULT_BUDGETS)

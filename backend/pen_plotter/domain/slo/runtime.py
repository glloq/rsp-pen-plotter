"""Runtime samples accumulator + background SLO evaluator (E.4 wire).

Counterpart to :func:`evaluate_budgets`: instead of taking a request-
scoped sample list from the frontend, the runtime evaluator keeps a
bounded in-memory deque per metric and periodically evaluates the
budget table against the accumulated samples. Breaches are emitted
as ``slo_breach`` structured log lines exactly the way the HTTP
evaluate path does — same downstream consumer.

The background task is opt-in via ``OMNIPLOT_SLO_EVAL_ENABLED=1`` so
deployments that don't want the periodic noise can stay out of it.
Default interval: 60s.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections import deque
from collections.abc import Iterable

from pen_plotter.domain.slo.budgets import (
    DEFAULT_BUDGETS,
    MetricSample,
    evaluate_budgets,
)

_log = logging.getLogger(__name__)

# Per-metric ring buffer cap. Sized to comfortably cover the
# ``min_samples`` of every default budget without growing
# unbounded; tighten / loosen as the budget table evolves.
_RING_CAP = 500

_samples: dict[str, deque[float]] = {}


def record_sample(metric: str, value_ms: float) -> None:
    """Push one observation for ``metric`` into the ring buffer."""
    bucket = _samples.get(metric)
    if bucket is None:
        bucket = deque(maxlen=_RING_CAP)
        _samples[metric] = bucket
    bucket.append(float(value_ms))


def reset_samples_for_tests() -> None:
    """Drop every accumulated sample. Test-only helper."""
    _samples.clear()


def collect_samples() -> list[MetricSample]:
    """Snapshot the current ring buffers as a flat sample list."""
    out: list[MetricSample] = []
    for metric, values in _samples.items():
        for v in values:
            out.append(MetricSample(metric=metric, value_ms=v))
    return out


def _truthy(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def evaluator_enabled() -> bool:
    """``True`` when the background evaluator should run this process."""
    return _truthy(os.environ.get("OMNIPLOT_SLO_EVAL_ENABLED"))


def evaluator_interval_seconds() -> float:
    """Resolved tick interval from env, floored at 5s."""
    raw = os.environ.get("OMNIPLOT_SLO_EVAL_INTERVAL", "60")
    try:
        v = float(raw)
    except ValueError:
        return 60.0
    return max(5.0, v)


async def evaluator_loop(
    interval_seconds: float | None = None,
    *,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Background task: evaluate budgets every ``interval_seconds``.

    Cancels cleanly on lifespan shutdown. Each iteration runs
    :func:`evaluate_budgets` synchronously (small CPU footprint) and
    relies on :func:`evaluate_budgets` itself to emit ``slo_breach``
    structured logs for breaches.
    """
    interval = interval_seconds if interval_seconds is not None else evaluator_interval_seconds()
    _log.info("slo_evaluator_started", extra={"interval_s": interval})
    try:
        while True:
            if stop_event is not None and stop_event.is_set():
                break
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            samples = collect_samples()
            if not samples:
                continue
            try:
                evaluate_budgets(samples, list(DEFAULT_BUDGETS))
            except Exception:  # noqa: BLE001 — evaluator failure must not crash app
                _log.exception("slo_evaluator_iteration_failed")
    finally:
        _log.info("slo_evaluator_stopped")


def record_samples(samples: Iterable[MetricSample]) -> None:
    """Convenience: push a batch of typed samples at once."""
    for s in samples:
        record_sample(s.metric, s.value_ms)

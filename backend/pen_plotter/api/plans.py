"""Read-only access to archived :class:`ResolvedPlan` snapshots.

Every successful ``/generate`` call writes one row into
``planshapshotrecord`` keyed by the plan's deterministic hash. The
endpoint here lets an operator retrieve that exact snapshot — useful
when a print misbehaves and we need to know what was actually sent to
the engine.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from pen_plotter.domain.print_plan import ResolvedPlan
from pen_plotter.persistence import get_plan_snapshot

router = APIRouter()


@router.get("/plans/{plan_hash}", response_model=ResolvedPlan)
async def get_plan(plan_hash: str) -> ResolvedPlan:
    """Return the resolved plan archived under ``plan_hash``.

    Raises:
        HTTPException: 404 if no snapshot exists for that hash.
    """
    record = get_plan_snapshot(plan_hash)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Unknown plan_hash: {plan_hash!r}")
    return ResolvedPlan.model_validate_json(record.plan_json)


__all__ = ["router"]

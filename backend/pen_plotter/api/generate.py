"""G-code generation endpoint (thin adapter over ``run_generate``)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from pen_plotter.application.generate_service import run_generate
from pen_plotter.application.plan_resolver import PlanResolutionError
from pen_plotter.domain.print_plan import PrintPlan, ResolvedPlan
from pen_plotter.persistence import save_plan_snapshot
from pen_plotter.profiles import get_profile

router = APIRouter()


class GenerateRequest(PrintPlan):
    """Wire model for ``POST /generate``.

    Identical to :class:`PrintPlan` — kept as a named subclass so the
    OpenAPI schema (and therefore the generated TypeScript types) reads
    ``GenerateRequest`` at the endpoint boundary, while the rest of the
    backend manipulates the domain type.
    """


class GenerateResponse(BaseModel):
    """Generated G-code, its line count, and the resolved plan snapshot."""

    gcode: str
    line_count: int
    plan_hash: str
    resolved_plan: ResolvedPlan


@router.post("/generate")
async def generate(request: GenerateRequest) -> GenerateResponse:
    """Generate G-code for a print plan.

    Returns the program plus the resolved-plan snapshot (and its hash)
    that produced it — the snapshot is also persisted to SQLite for
    later inspection via ``GET /plans/{hash}``.

    Raises:
        HTTPException: 404 if the profile is unknown; 400 if the plan
            fails business validation; 422 if generation itself fails.
    """
    profile = get_profile(request.profile_name)
    if profile is None:
        raise HTTPException(
            status_code=404, detail=f"Unknown profile: {request.profile_name!r}"
        )
    try:
        outcome = run_generate(request, profile)
    except PlanResolutionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # template / geometry failures
        raise HTTPException(status_code=422, detail=f"Generation failed: {exc}") from exc

    # Best-effort persistence: snapshots are a diagnostics aid, not a
    # blocking concern. If the DB is unreachable we still return the
    # G-code so the operator's print isn't held hostage by traceability.
    save_plan_snapshot(outcome.resolved)

    return GenerateResponse(
        gcode=outcome.gcode,
        line_count=outcome.line_count,
        plan_hash=outcome.resolved.plan_hash,
        resolved_plan=outcome.resolved,
    )


__all__ = ["GenerateRequest", "GenerateResponse", "router"]

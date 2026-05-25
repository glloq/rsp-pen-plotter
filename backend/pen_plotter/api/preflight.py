"""Pre-run check endpoint (thin adapter over ``run_preflight``)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from pen_plotter.application.plan_resolver import PlanResolutionError
from pen_plotter.application.preflight_service import run_preflight
from pen_plotter.domain.print_plan import PrintPlan
from pen_plotter.models import PreflightReport
from pen_plotter.profiles import get_profile

router = APIRouter()


class PreflightRequest(PrintPlan):
    """Wire model for ``POST /preflight`` — same shape as a print plan."""


@router.post("/preflight", response_model=PreflightReport)
async def preflight(request: PreflightRequest) -> PreflightReport:
    """Validate and estimate a placed drawing before generating it.

    The response is a :class:`PreflightReport` with ``plan_hash`` set so
    the frontend can verify it later matches the ``/generate`` hash.

    Raises:
        HTTPException: 404 if the profile is unknown; 400 if the SVG
            cannot be parsed or the plan fails business validation.
    """
    profile = get_profile(request.profile_name)
    if profile is None:
        raise HTTPException(
            status_code=404, detail=f"Unknown profile: {request.profile_name!r}"
        )
    try:
        outcome = run_preflight(request, profile)
    except PlanResolutionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return outcome.report.model_copy(update={"plan_hash": outcome.resolved.plan_hash})


__all__ = ["PreflightRequest", "router"]

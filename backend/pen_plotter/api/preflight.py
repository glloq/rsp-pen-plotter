"""Pre-run check endpoint (thin adapter over ``run_preflight``)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from pen_plotter.application.plan_resolver import PlanResolutionError
from pen_plotter.application.preflight_service import run_preflight
from pen_plotter.core.preflight import preflight_report
from pen_plotter.domain.print_plan import PrintPlan
from pen_plotter.models import PreflightReport
from pen_plotter.profiles import get_profile

router = APIRouter()


class PreflightRequest(PrintPlan):
    """Wire model for ``POST /preflight`` — same shape as a print plan."""


class PreflightSvgRequest(BaseModel):
    """Lightweight wire model for ``POST /preflight/svg``.

    Accepts just an already-rendered SVG + a profile name; skips the
    full :class:`PrintPlan` ceremony. Used by the Compare drawer to
    compute per-candidate metrics (drawing length, travel length,
    estimated time, pen-change count) without building a fake plan
    around each variant.
    """

    svg: str
    profile_name: str


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
        raise HTTPException(status_code=404, detail=f"Unknown profile: {request.profile_name!r}")
    try:
        # Plan resolution + SVG parsing + path estimation are synchronous
        # CPU-bound work; keep them off the event loop.
        outcome = await run_in_threadpool(run_preflight, request, profile)
    except PlanResolutionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return outcome.report.model_copy(update={"plan_hash": outcome.resolved.plan_hash})


@router.post("/preflight/svg", response_model=PreflightReport)
async def preflight_svg(request: PreflightSvgRequest) -> PreflightReport:
    """Estimate metrics for a standalone SVG against a profile.

    Lightweight variant that skips plan resolution / TypographyPlan
    re-rendering / placement composition. Returns the same
    :class:`PreflightReport` shape as the full ``/preflight`` so
    consumers (e.g. the Compare drawer) can read
    ``drawing_length_mm``, ``travel_length_mm``,
    ``estimated_seconds`` and ``pen_changes`` straight from the
    report.

    Raises:
        HTTPException: 404 if the profile is unknown; 400 if the SVG
            cannot be parsed.
    """
    profile = get_profile(request.profile_name)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Unknown profile: {request.profile_name!r}")
    try:
        # Same threadpool treatment as /preflight — SVG metric extraction
        # is synchronous and can be heavy for dense drawings.
        return await run_in_threadpool(preflight_report, request.svg, profile)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


__all__ = ["PreflightRequest", "PreflightSvgRequest", "router"]

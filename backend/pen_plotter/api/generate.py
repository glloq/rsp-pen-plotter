"""G-code generation endpoint (thin adapter over ``run_generate``)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from jinja2 import UndefinedError
from pydantic import BaseModel

from pen_plotter.application.generate_service import MissingPenSlotsError, run_generate
from pen_plotter.application.plan_resolver import PlanResolutionError
from pen_plotter.domain.print_plan import PrintPlan, ResolvedPlan
from pen_plotter.persistence import save_plan_snapshot
from pen_plotter.profiles import get_profile

router = APIRouter()


class GenerateRequest(PrintPlan):
    """Wire model for ``POST /generate``.

    Identical to :class:`PrintPlan` plus an explicit override flag.
    Kept as a named subclass so the OpenAPI schema (and therefore the
    generated TypeScript types) reads ``GenerateRequest`` at the
    endpoint boundary, while the rest of the backend manipulates the
    domain type.
    """

    allow_missing_slots: bool = False
    """Operator override for the missing-pen-slot guard.

    Default ``False`` blocks generation if any layer targets a slot
    that is not installed in the magazine; the response carries the
    missing slots so the UI can prompt for installation. Set this to
    ``True`` after the operator has acknowledged they will swap pens
    manually during the firmware M0 pauses.
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
        raise HTTPException(status_code=404, detail=f"Unknown profile: {request.profile_name!r}")
    try:
        outcome = run_generate(
            request,
            profile,
            allow_missing_slots=request.allow_missing_slots,
        )
    except PlanResolutionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MissingPenSlotsError as exc:
        # 409 Conflict + structured detail so the UI can offer the
        # operator a deliberate override path instead of silently
        # streaming G-code that asks for pens the magazine does not
        # have. ``reason`` is machine-readable so the frontend can
        # branch on it without parsing the human-readable message.
        raise HTTPException(
            status_code=409,
            detail={
                "reason": "missing_pen_slots",
                "slots": exc.slots,
                "message": str(exc),
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except UndefinedError as exc:
        # A Jinja ``UndefinedError`` reaching here means the boot-time
        # template-contract check missed something — either a brand-new
        # variable that ``_TEMPLATE_EXPECTED_VARS`` doesn't declare, or
        # a runtime path that conditionally uses an extra binding. The
        # detail steers the operator to the deployment-desync fix path
        # instead of a bare ``'feed' is undefined`` that reads like a
        # mystery firmware error.
        raise HTTPException(
            status_code=422,
            detail=(
                f"Generation failed: {exc}. This usually means the backend "
                "templates and compiled Python are out of sync — purge "
                "``__pycache__`` + restart the backend after a git pull."
            ),
        ) from exc
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

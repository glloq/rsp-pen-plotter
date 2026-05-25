"""HTTP adapter for ``POST /rerender`` — re-render selected bitmap layers.

All disk I/O, segmentation caching and rehydration live in
:mod:`pen_plotter.application.file_library`. This module owns only the
wire model and the HTTP error mapping.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from pen_plotter.application import file_library as _lib
from pen_plotter.application.file_library import (
    forget_job,
    get_cached,
    remember_job,
    try_rehydrate,
)
from pen_plotter.converters.bitmap import BitmapConverter
from pen_plotter.core.sanitize import sanitize_svg

router = APIRouter()


# Re-exports — keep the import surface stable for callers (notably
# ``api/files.py`` and the tests) that historically imported these
# from this module. New code should import them from
# ``application.file_library`` directly.
_CACHE = _lib._CACHE
_clear_cache_for_tests = _lib.clear_cache_for_tests

__all__ = [
    "LayerAlgorithm",
    "LayerPass",
    "RerenderRequest",
    "RerenderResponse",
    "_CACHE",
    "_clear_cache_for_tests",
    "forget_job",
    "remember_job",
    "router",
]


class LayerPass(BaseModel):
    """One rendering pass within a multi-pass layer override.

    A single colour can be drawn with several stacked algorithms — e.g.
    ``contours`` for the outline followed by ``crosshatch`` for the fill
    — so the operator gets the visual effect of multiple inks while
    keeping the layer on one physical pen.
    """

    algorithm: str
    algorithm_options: dict[str, Any] = Field(default_factory=dict)


class LayerAlgorithm(BaseModel):
    """A per-layer algorithm override applied on top of the cached defaults.

    Backwards compatible: callers can still pass a single ``algorithm`` /
    ``algorithm_options`` pair (the legacy shape). When ``passes`` is set
    and non-empty, it overrides the single-algorithm fields and the layer
    is rendered as the stack of passes in order.
    """

    layer_id: str
    algorithm: str = ""
    algorithm_options: dict[str, Any] = Field(default_factory=dict)
    passes: list[LayerPass] = Field(default_factory=list)


class RerenderRequest(BaseModel):
    """Request body for ``POST /rerender``."""

    job_id: str
    layers: list[LayerAlgorithm] = Field(default_factory=list)


class RerenderResponse(BaseModel):
    """The freshly rendered SVG plus any non-fatal warnings."""

    svg: str
    warnings: list[str] = Field(default_factory=list)


@router.post("/rerender", response_model=RerenderResponse)
async def rerender(request: RerenderRequest) -> RerenderResponse:
    """Re-render the cached bitmap job with optional per-layer algorithm overrides.

    Args:
        request: The job id and per-layer algorithm choices.

    Returns:
        The freshly rendered SVG (sanitized) plus rendering warnings.

    Raises:
        HTTPException: 404 with a structured ``{reason, job_id, message}``
            detail when no cached segmentation exists and rehydration
            cannot reconstruct one — see
            ``application.file_library.REHYDRATE_*`` for the reason codes.
    """
    entry = get_cached(request.job_id)
    if entry is None:
        entry, reason = try_rehydrate(request.job_id)
        if entry is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "reason": reason,
                    "job_id": request.job_id,
                    "message": (
                        f"No cached segmentation for job {request.job_id!r}; "
                        "re-upload to refresh."
                    ),
                },
            )

    overrides: dict[str, dict[str, Any]] = {}
    for item in request.layers:
        spec: dict[str, Any] = {}
        if item.passes:
            spec["passes"] = [
                {"algorithm": p.algorithm, "algorithm_options": p.algorithm_options}
                for p in item.passes
            ]
        if item.algorithm:
            spec["algorithm"] = item.algorithm
            spec["algorithm_options"] = item.algorithm_options
        if spec:
            overrides[item.layer_id] = spec
    try:
        svg, warnings = BitmapConverter.render_from_segmentation(
            entry.segmentation, entry.options, per_layer_overrides=overrides
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover — algorithm/runtime failures
        raise HTTPException(status_code=422, detail=f"Re-render failed: {exc}") from exc

    return RerenderResponse(svg=sanitize_svg(svg), warnings=warnings)

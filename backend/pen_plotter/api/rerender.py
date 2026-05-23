"""Re-render selected bitmap layers with new per-layer algorithms.

The full ``/upload`` flow runs k-means + per-cluster rendering, which can
take a few seconds on a Pi. When the operator changes the algorithm for
a single layer in the UI, we don't want to re-segment — only re-render.
This module caches the segmentation result (labels + palette) of each
bitmap job by ``job_id`` so a second pass only pays for the rendering.

The cache is bounded (LRU, ~16 entries) and lives in process memory, so
it's lost on backend restart. The UI tolerates a 404 from ``/rerender``
by falling back to a fresh upload — the only consequence of a miss is
slower latency, not a broken state.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from pen_plotter.converters.bitmap import BitmapConverter, BitmapOptions, SegmentationResult
from pen_plotter.core.sanitize import sanitize_svg

router = APIRouter()

_CACHE_SIZE = 16


class _CacheEntry:
    """One cached bitmap job: its segmentation + the original options."""

    __slots__ = ("segmentation", "options")

    def __init__(self, segmentation: SegmentationResult, options: BitmapOptions) -> None:
        self.segmentation = segmentation
        self.options = options


_CACHE: "OrderedDict[str, _CacheEntry]" = OrderedDict()


def remember_job(job_id: str, segmentation: SegmentationResult, options: BitmapOptions) -> None:
    """Stash a bitmap job's segmentation result for later ``/rerender`` calls."""
    _CACHE[job_id] = _CacheEntry(segmentation, options)
    _CACHE.move_to_end(job_id)
    while len(_CACHE) > _CACHE_SIZE:
        _CACHE.popitem(last=False)


def forget_job(job_id: str) -> None:
    """Drop a cached job (e.g. when ``/upload`` replaces it)."""
    _CACHE.pop(job_id, None)


def _clear_cache_for_tests() -> None:
    """Test-only hook so the cache doesn't leak between cases."""
    _CACHE.clear()


class LayerAlgorithm(BaseModel):
    """A per-layer algorithm override applied on top of the cached defaults."""

    layer_id: str
    algorithm: str
    algorithm_options: dict[str, Any] = Field(default_factory=dict)


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
        HTTPException: 404 if no segmentation cache exists for the job
            (e.g. after a backend restart or LRU eviction); the UI then
            re-uploads instead.
    """
    entry = _CACHE.get(request.job_id)
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail=f"No cached segmentation for job {request.job_id!r}; re-upload to refresh.",
        )
    # Refresh LRU position so frequently-tweaked jobs stay hot.
    _CACHE.move_to_end(request.job_id)

    overrides: dict[str, dict[str, Any]] = {
        item.layer_id: {
            "algorithm": item.algorithm,
            "algorithm_options": item.algorithm_options,
        }
        for item in request.layers
    }
    try:
        svg, warnings = BitmapConverter.render_from_segmentation(
            entry.segmentation, entry.options, per_layer_overrides=overrides
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover — algorithm/runtime failures
        raise HTTPException(status_code=422, detail=f"Re-render failed: {exc}") from exc

    return RerenderResponse(svg=sanitize_svg(svg), warnings=warnings)

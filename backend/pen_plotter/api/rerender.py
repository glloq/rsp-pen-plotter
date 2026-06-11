"""HTTP adapter for ``POST /rerender`` — re-render selected bitmap layers.

All disk I/O, segmentation caching and rehydration live in
:mod:`pen_plotter.application.file_library`. This module owns only the
wire model and the HTTP error mapping.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from pen_plotter.application import file_library as _lib
from pen_plotter.application.file_library import (
    CacheEntry,
    find_original,
    forget_job,
    get_cached,
    remember_job,
    try_rehydrate,
)
from pen_plotter.converters.bitmap import (
    BitmapConverter,
    _requested_num_bands,
    pick_effective_segmentation,
)
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
    # Per-layer pen tip width in the layer's SVG user units (viewBox
    # space), keyed by layer label (``color-{hex}``). Derived by the
    # frontend from the assigned colour's ``stroke_width_mm`` and the
    # placement scale; applied to every layer (default + override) so the
    # rendered stroke matches the real pen and fill spacing is floored at
    # one pen width. Omitted layers keep the historical 0.8 default.
    layer_stroke_widths: dict[str, float] = Field(default_factory=dict)
    # Per-layer ink hex keyed by layer label (``color-{hex}``). The hex
    # the operator assigned to each layer from the magazine / inventory
    # pool; sent so the rendered SVG uses the colour that will actually
    # be drawn instead of the segmentation centroid. Omitted layers fall
    # back to the cluster's source colour (legacy behaviour).
    layer_ink_colors: dict[str, str] = Field(default_factory=dict)
    # Physical footprint (mm) the rendered drawing will occupy on the
    # sheet. Used to derive the raster's px-per-mm scale so millimetre
    # algorithm options (``spacing_mm``, ``cell_size_mm``, …) keep the
    # same on-paper pitch whatever page format the operator picked —
    # a bigger page gets proportionally more lines, not the same
    # geometry scaled up. Omitted → the A4 reference fallback applies
    # (see ``convert_mm_options``).
    target_width_mm: float | None = Field(default=None, gt=0)
    target_height_mm: float | None = Field(default=None, gt=0)


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
        # Rehydration re-reads the original bytes and re-runs the full
        # segmentation — CPU-bound work that would freeze the event loop
        # (and /plotter/emergency_stop) if run inline.
        entry, reason = await run_in_threadpool(try_rehydrate, request.job_id)
        if entry is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "reason": reason,
                    "job_id": request.job_id,
                    "message": (
                        f"No cached segmentation for job {request.job_id!r}; re-upload to refresh."
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

    # Re-segment from disk when a per-layer override flips the layer to a
    # line-extraction algorithm in monochrome mode but the cached
    # segmentation isn't already Otsu. Without this, the cached kmeans /
    # luminance_bands clusters trace the anti-aliased halo around every
    # stroke instead of the ink itself — the same regression the upload
    # auto-switch was added to fix, just hidden behind the editor's
    # per-layer algorithm picker. Best-effort: if the source bytes have
    # been GC'd or the new options don't round-trip, fall through to the
    # legacy cached-render path.
    entry = await run_in_threadpool(
        _maybe_reseg_for_line_art_overrides, entry, request.job_id, overrides
    )

    # Raster scale of the placement footprint: compare long sides so an
    # operator-stretched placement (aspect drifted from the raster's)
    # still yields a sane uniform scale for the mm-option conversion.
    px_per_mm: float | None = None
    if request.target_width_mm and request.target_height_mm:
        raster_h, raster_w = entry.segmentation.labels.shape
        px_per_mm = max(raster_w, raster_h) / max(request.target_width_mm, request.target_height_mm)

    try:
        # Rendering is synchronous geometry/raster work — keep it off the
        # event loop for the same reason as the rehydration above.
        svg, warnings = await run_in_threadpool(
            BitmapConverter.render_from_segmentation,
            entry.segmentation,
            entry.options,
            per_layer_overrides=overrides,
            layer_stroke_widths=request.layer_stroke_widths,
            layer_ink_colors=request.layer_ink_colors,
            px_per_mm=px_per_mm,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover — algorithm/runtime failures
        raise HTTPException(status_code=422, detail=f"Re-render failed: {exc}") from exc

    return RerenderResponse(svg=sanitize_svg(svg), warnings=warnings)


def _maybe_reseg_for_line_art_overrides(
    entry: CacheEntry,
    job_id: str,
    overrides: dict[str, dict[str, Any]],
) -> CacheEntry:
    """Re-segment from disk when an override needs Otsu but the cache doesn't have it.

    The upload auto-switch only fires when the operator picked a
    line-extraction algorithm at /upload time. The editor's per-layer
    algorithm picker can flip a layer to ``centerline`` / ``edges`` /
    ``contours`` AFTER the fact — and /rerender would otherwise serve the
    stale segmentation. Trigger a fresh ``segment_and_render`` pass when:

    * any override picks a member of the ``lines`` algorithm family,
    * the cached options carry ``mono_ink_color`` (monochrome mode), and
    * the cached segmentation method isn't already explicit / Otsu.

    Falls back silently to the cached entry when the source bytes can't
    be read or the resegmentation fails — preserving the legacy
    behaviour so /rerender never starts 500'ing on edge cases.
    """
    if not overrides:
        return entry
    cached_opts = entry.options
    if cached_opts.mono_ink_color is None:
        return entry
    # Look for an override that would trigger the line-art auto-switch.
    # ``num_bands`` rides along: a cached multi-band luminance
    # segmentation is intentional tonal structure the auto-switch must
    # not collapse (mirrors ``pick_effective_segmentation``'s rule).
    cached_bands = _requested_num_bands(cached_opts.segmentation_options)
    needs_resegment = False
    for spec in overrides.values():
        algo = spec.get("algorithm")
        if (
            isinstance(algo, str)
            and pick_effective_segmentation(
                algorithm=algo,
                mono_ink_color=cached_opts.mono_ink_color,
                segmentation_method=cached_opts.segmentation_method,
                num_bands=cached_bands,
            )
            == "otsu"
            and cached_opts.segmentation_method != "otsu"
        ):
            needs_resegment = True
            break
        for sub in spec.get("passes", []) or []:
            sub_algo = sub.get("algorithm") if isinstance(sub, dict) else None
            if (
                isinstance(sub_algo, str)
                and pick_effective_segmentation(
                    algorithm=sub_algo,
                    mono_ink_color=cached_opts.mono_ink_color,
                    segmentation_method=cached_opts.segmentation_method,
                    num_bands=cached_bands,
                )
                == "otsu"
                and cached_opts.segmentation_method != "otsu"
            ):
                needs_resegment = True
                break
        if needs_resegment:
            break
    if not needs_resegment:
        return entry
    original = find_original(job_id)
    if original is None or not original.is_file():
        return entry
    try:
        data = original.read_bytes()
        # Rebuild options with segmentation_method='otsu' so the cached
        # entry reflects the line-art segmentation; subsequent /rerender
        # calls land directly on the right cache without paying for
        # another segmentation pass.
        new_opts = cached_opts.model_copy(update={"segmentation_method": "otsu"})
        _result, segmentation = BitmapConverter().segment_and_render(
            data, options=new_opts.model_dump()
        )
    except Exception:  # noqa: BLE001 — degrade to cached render rather than 500
        return entry
    fresh = CacheEntry(segmentation, new_opts)
    remember_job(job_id, segmentation, new_opts)
    return fresh

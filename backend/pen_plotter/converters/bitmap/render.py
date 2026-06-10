"""SVG assembly + per-layer rendering for the bitmap converter.

Consumes a :class:`SegmentationResult` (the slow clustering output)
plus a render configuration and emits an Inkscape-flavoured SVG with
one ``<g inkscape:label="...">`` per cluster. The actual mask →
strokes work is delegated to the registered algorithms via
``pen_plotter.converters.algorithms.get_algorithm``; this module is
purely the orchestrator + the worker-pool plumbing for parallel
per-layer rendering.

``_render_layer_unpack`` and ``_render_one_layer`` stay at module
scope so :class:`concurrent.futures.ProcessPoolExecutor` can pickle
them — moving them inside a class would re-introduce the
"instance not picklable" failure mode the original code carefully
avoided.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from typing import Any

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms import get_algorithm
from pen_plotter.converters.algorithms._style import A4_LONG_SIDE_MM, convert_mm_options

from .cache import SegmentationResult
from .segment import _REC709

# Signature: (index, total, layer_label). Called after each rendered
# layer in the sequential branch. The parallel branch fires it once at
# the end with `(total, total, "")` because the worker pool ordering
# guarantees only batch completion, not per-layer progress.
ProgressCallback = Callable[[int, int, str], None]


def _wants_tone(algo_name: Any) -> bool:
    """True when ``algo_name`` is registered and opts into ``_tone``."""
    if not isinstance(algo_name, str):
        return False
    try:
        return get_algorithm(algo_name).tone_aware
    except KeyError:
        return False


def _render_layer_unpack(
    job: tuple[
        NDArray[np.bool_],
        str,
        str,
        str,
        str,
        dict[str, Any],
        list[dict[str, Any]] | None,
        str,
    ],
) -> tuple[str, list[str]]:
    """Adapter for :meth:`ProcessPoolExecutor.map` which only takes 1 arg."""
    mask, color_hex, ink_hex, label, algo_name, algo_options, passes, fallback = job
    return _render_one_layer(
        mask, color_hex, ink_hex, label, algo_name, algo_options, passes, fallback
    )


def _render_one_layer(
    mask: NDArray[np.bool_],
    color_hex: str,
    ink_hex: str,
    label: str,
    algo_name: str,
    algo_options: dict[str, Any],
    passes: list[dict[str, Any]] | None,
    fallback_algo: str,
) -> tuple[str, list[str]]:
    """Render a single colour layer to an SVG group, picklable for workers.

    Lives at module scope so :class:`concurrent.futures.ProcessPoolExecutor`
    can pickle and dispatch it. Algorithm instances are re-resolved here
    rather than passed in — they're stateless singletons in the registry,
    so the lookup is free, and we sidestep "instance not picklable"
    surprises that the registered classes might develop later.
    """
    warnings: list[str] = []
    if passes:
        from xml.sax.saxutils import quoteattr

        fragments: list[str] = []
        for idx, raw in enumerate(passes):
            pass_algo = (raw.get("algorithm") if isinstance(raw, dict) else None) or fallback_algo
            pass_opts = (raw.get("algorithm_options") if isinstance(raw, dict) else None) or {}
            try:
                pass_algorithm = get_algorithm(pass_algo)
            except KeyError:
                warnings.append(
                    f"Layer {label} pass {idx}: unknown algorithm {pass_algo!r}, "
                    f"falling back to {fallback_algo!r}."
                )
                pass_algorithm = get_algorithm(fallback_algo)
            fragments.append(
                pass_algorithm.render_layer(mask, ink_hex, f"{label}-pass-{idx}", options=pass_opts)
            )
        if not fragments:
            return f"<g inkscape:label={quoteattr(label)}></g>", warnings
        return (
            f"<g inkscape:label={quoteattr(label)}>" + "".join(fragments) + "</g>",
            warnings,
        )
    try:
        algorithm = get_algorithm(algo_name)
    except KeyError:
        warnings.append(f"Layer {label}: unknown algorithm {algo_name!r}, using {fallback_algo!r}.")
        algorithm = get_algorithm(fallback_algo)
    return (
        algorithm.render_layer(mask, ink_hex, label, options=algo_options),
        warnings,
    )


def layer_order(labels: NDArray[np.intp], palette: NDArray[np.uint8]) -> list[int]:
    """Order clusters from darkest to lightest centroid."""
    luminance = palette.astype(np.float64) @ _REC709 / 255.0
    return sorted(range(palette.shape[0]), key=lambda c: luminance[c])


def wrap_svg(width: int, height: int, groups: list[str]) -> str:
    """Assemble layer groups into a complete SVG document."""
    header = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        f'viewBox="0 0 {width} {height}" width="{width}" height="{height}">'
    )
    return header + "".join(groups) + "</svg>"


def render_from_segmentation(  # noqa: C901 — sequential vs parallel branches
    seg: SegmentationResult,
    *,
    algorithm: str,
    algorithm_options: dict[str, Any],
    mono_ink_color: str | None,
    drop_background: bool,
    background_luminance: float,
    per_layer_overrides: dict[str, dict[str, Any]] | None = None,
    layer_stroke_widths: dict[str, float] | None = None,
    layer_ink_colors: dict[str, str] | None = None,
    px_per_mm: float | None = None,
    n_workers: int = 1,
    progress_callback: ProgressCallback | None = None,
) -> tuple[str, list[str]]:
    """Re-run only the rendering step against an existing segmentation.

    ``per_layer_overrides`` maps a layer label (``f"color-{hex}"``) to a
    dict with ``algorithm`` and/or ``algorithm_options`` keys, swapping
    in a different algorithm just for that layer. Layers without an
    override fall back to ``algorithm`` + ``algorithm_options``.

    ``px_per_mm`` is the raster scale of the placement's physical
    footprint (raster pixels per plotted millimetre). Every ``*_mm``
    option — top-level, override or pass — is converted into its
    ``*_px`` twin at this scale before reaching the algorithms, so a
    millimetre knob keeps the same on-paper pitch whatever page format
    the drawing is placed on. ``None`` falls back to mapping the
    raster's long side onto an A4 long side (297 mm).

    ``layer_ink_colors`` maps a layer label to the actual ink hex the
    layer should be rendered with — the operator's assigned colour from
    the magazine / inventory pool rather than the cluster's source
    centroid. Wins over ``mono_ink_color`` so a per-layer pick still
    shows in mono-machine previews. Missing entries fall back to
    ``mono_ink_color`` then to the cluster centroid (legacy behaviour).

    ``n_workers > 1`` dispatches each colour layer to a separate
    process via :class:`ProcessPoolExecutor` (forkserver context so
    scikit-image / scipy imports stay isolated). ``executor.map``
    preserves layer order so the result is deterministic regardless
    of worker count — important for the cache keys downstream.
    Falls back to in-process rendering when worker init fails or
    ``n_workers <= 1``.
    """
    overrides = per_layer_overrides or {}
    stroke_widths = layer_stroke_widths or {}
    ink_colors = layer_ink_colors or {}
    raster_h, raster_w = seg.labels.shape
    scale_px_per_mm = (
        px_per_mm
        if px_per_mm is not None and px_per_mm > 0
        else max(raster_w, raster_h) / A4_LONG_SIDE_MM
    )
    algorithm_options = convert_mm_options(algorithm_options, scale_px_per_mm)
    warnings: list[str] = []
    # (mask, color_hex, ink_hex, label, algo_name, algo_options, passes)
    # Local type alias; uppercase matches the convention for type
    # constructions even though Ruff's N806 flags it as a variable.
    _LayerJob = tuple[  # noqa: N806
        NDArray[np.bool_],
        str,
        str,
        str,
        str,
        dict[str, Any],
        list[dict[str, Any]] | None,
    ]
    jobs: list[_LayerJob] = []
    for cluster in layer_order(seg.labels, seg.palette):
        rgb = seg.palette[cluster]
        luminance = float(np.dot(rgb / 255.0, _REC709))
        if drop_background and luminance >= background_luminance:
            continue
        mask = seg.labels == cluster
        color_hex = "#{:02x}{:02x}{:02x}".format(*rgb.astype(int))
        label = f"color-{color_hex.lstrip('#')}"
        # Priority for the actual stroke colour:
        #   1. per-layer assigned ink (from the magazine / inventory) —
        #      so the preview shows the colour that will really be drawn,
        #   2. global mono ink (a one-pen machine forcing every layer
        #      onto the same nib),
        #   3. the cluster's source centroid (legacy fallback).
        # The label (which keys band_recipes / extract_layers) still
        # uses the source centroid so cache lookups stay stable.
        ink_hex = ink_colors.get(label) or mono_ink_color or color_hex
        override = overrides.get(label, {})
        # Multi-pass: stack several algorithms in the same labeled
        # group so the layer is drawn with multiple visual effects
        # (e.g. contours + crosshatch fill) using a single ink.
        passes_raw = override.get("passes") or []
        # Millimetre → raster-pixel conversion for pass options; the
        # top-level ``algorithm_options`` were converted once above and
        # per-layer override options get converted just below.
        passes: list[dict[str, Any]] | None = (
            [
                {
                    **p,
                    "algorithm_options": convert_mm_options(
                        p.get("algorithm_options"), scale_px_per_mm
                    ),
                }
                if isinstance(p, dict)
                else p
                for p in passes_raw
            ]
            if passes_raw
            else None
        )
        algo_name = override.get("algorithm") or algorithm
        override_options = override.get("algorithm_options")
        algo_options = (
            convert_mm_options(override_options, scale_px_per_mm)
            if override_options
            else algorithm_options
        )
        # Tone-aware algorithms (``tone_aware`` ClassVar — tonal spiral,
        # ridge lines, string art, …) modulate their geometry from the
        # per-pixel luminance map, so they render as one continuous,
        # smoothly-shaded texture over the whole image rather than a
        # uniform binary fill. Inject the map (when available) into their
        # options; other algorithms never read ``_tone``.
        if seg.luminance is not None:
            if _wants_tone(algo_name):
                algo_options = {**algo_options, "_tone": seg.luminance}
            if passes:
                passes = [
                    {
                        **p,
                        "algorithm_options": {
                            **(p.get("algorithm_options") or {}),
                            "_tone": seg.luminance,
                        },
                    }
                    if isinstance(p, dict) and _wants_tone(p.get("algorithm"))
                    else p
                    for p in passes
                ]
        # Physical pen width (viewBox units) for this layer, injected by
        # the frontend from the assigned colour's ``stroke_width_mm``.
        # Threading it into the options makes the rendered stroke match
        # the real pen and floors the fill spacing at one pen width.
        # Applies to default + override + multi-pass layers alike.
        pen_sw = stroke_widths.get(label)
        if pen_sw is not None and pen_sw > 0:
            algo_options = {**algo_options, "stroke_width": pen_sw}
            if passes:
                passes = [
                    {
                        **p,
                        "algorithm_options": {
                            **(p.get("algorithm_options") or {}),
                            "stroke_width": pen_sw,
                        },
                    }
                    if isinstance(p, dict)
                    else p
                    for p in passes
                ]
        jobs.append((mask, color_hex, ink_hex, label, algo_name, algo_options, passes))

    groups: list[str] = []
    max_workers = min(max(1, n_workers), max(1, (os.cpu_count() or 1)))
    fallback = algorithm
    worker_jobs = [(*job, fallback) for job in jobs]
    total = len(worker_jobs)
    if max_workers > 1 and total > 1:
        try:
            ctx = get_context("forkserver")
            with _traced_span(
                "pipeline.bitmap.render_parallel",
                layer_count=total,
                workers=max_workers,
                algorithm=algorithm,
            ):
                with ProcessPoolExecutor(max_workers=max_workers, mp_context=ctx) as pool:
                    results = list(pool.map(_render_layer_unpack, worker_jobs))
            for svg, layer_warnings in results:
                groups.append(svg)
                warnings.extend(layer_warnings)
            if progress_callback is not None:
                progress_callback(total, total, "")
        except (OSError, RuntimeError, ValueError) as exc:
            # Worker init / pickling failed — degrade to serial.
            warnings.append(f"Parallel render disabled ({exc}); falling back to serial.")
            groups = []
            for i, job in enumerate(worker_jobs):
                with _traced_span(
                    "pipeline.bitmap.render_layer",
                    algorithm=job[4],
                    layer_label=job[3],
                ):
                    svg, layer_warnings = _render_layer_unpack(job)
                groups.append(svg)
                warnings.extend(layer_warnings)
                if progress_callback is not None:
                    progress_callback(i + 1, total, job[3])
    else:
        for i, job in enumerate(worker_jobs):
            with _traced_span(
                "pipeline.bitmap.render_layer",
                algorithm=job[4],
                layer_label=job[3],
            ):
                svg, layer_warnings = _render_layer_unpack(job)
            groups.append(svg)
            warnings.extend(layer_warnings)
            if progress_callback is not None:
                progress_callback(i + 1, total, job[3])
    if not groups:
        warnings.append("No drawable layers detected (image may be entirely background).")
    with _traced_span("pipeline.bitmap.compose_svg", layer_count=len(groups)):
        return wrap_svg(seg.width, seg.height, groups), warnings


def _traced_span(name: str, **attrs: Any) -> Any:
    """Defer OTel import until first call to keep cold start cheap."""
    from pen_plotter.observability import traced_span

    return traced_span(name, **attrs)

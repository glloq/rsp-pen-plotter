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
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from typing import Any

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms import get_algorithm

from .cache import SegmentationResult
from .segment import _REC709


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
                pass_algorithm.render_layer(
                    mask, ink_hex, f"{label}-pass-{idx}", options=pass_opts
                )
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
        warnings.append(
            f"Layer {label}: unknown algorithm {algo_name!r}, using {fallback_algo!r}."
        )
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


def render_from_segmentation(
    seg: SegmentationResult,
    *,
    algorithm: str,
    algorithm_options: dict[str, Any],
    mono_ink_color: str | None,
    drop_background: bool,
    background_luminance: float,
    per_layer_overrides: dict[str, dict[str, Any]] | None = None,
    n_workers: int = 1,
) -> tuple[str, list[str]]:
    """Re-run only the rendering step against an existing segmentation.

    ``per_layer_overrides`` maps a layer label (``f"color-{hex}"``) to a
    dict with ``algorithm`` and/or ``algorithm_options`` keys, swapping
    in a different algorithm just for that layer. Layers without an
    override fall back to ``algorithm`` + ``algorithm_options``.

    ``n_workers > 1`` dispatches each colour layer to a separate
    process via :class:`ProcessPoolExecutor` (forkserver context so
    scikit-image / scipy imports stay isolated). ``executor.map``
    preserves layer order so the result is deterministic regardless
    of worker count — important for the cache keys downstream.
    Falls back to in-process rendering when worker init fails or
    ``n_workers <= 1``.
    """
    overrides = per_layer_overrides or {}
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
        # Substitute the single mono ink at the last moment so the
        # label (which keys band_recipes / extract_layers) keeps
        # using the cluster's source colour.
        ink_hex = mono_ink_color or color_hex
        override = overrides.get(label, {})
        # Multi-pass: stack several algorithms in the same labeled
        # group so the layer is drawn with multiple visual effects
        # (e.g. contours + crosshatch fill) using a single ink.
        passes_raw = override.get("passes") or []
        passes: list[dict[str, Any]] | None = list(passes_raw) if passes_raw else None
        algo_name = override.get("algorithm") or algorithm
        algo_options = override.get("algorithm_options") or algorithm_options
        jobs.append((mask, color_hex, ink_hex, label, algo_name, algo_options, passes))

    groups: list[str] = []
    max_workers = min(max(1, n_workers), max(1, (os.cpu_count() or 1)))
    fallback = algorithm
    worker_jobs = [(*job, fallback) for job in jobs]
    if max_workers > 1 and len(worker_jobs) > 1:
        try:
            ctx = get_context("forkserver")
            with ProcessPoolExecutor(max_workers=max_workers, mp_context=ctx) as pool:
                results = list(pool.map(_render_layer_unpack, worker_jobs))
            for svg, layer_warnings in results:
                groups.append(svg)
                warnings.extend(layer_warnings)
        except (OSError, RuntimeError, ValueError) as exc:
            # Worker init / pickling failed — degrade to serial.
            warnings.append(f"Parallel render disabled ({exc}); falling back to serial.")
            groups = []
            for job in worker_jobs:
                svg, layer_warnings = _render_layer_unpack(job)
                groups.append(svg)
                warnings.extend(layer_warnings)
    else:
        for job in worker_jobs:
            svg, layer_warnings = _render_layer_unpack(job)
            groups.append(svg)
            warnings.extend(layer_warnings)
    if not groups:
        warnings.append("No drawable layers detected (image may be entirely background).")
    return wrap_svg(seg.width, seg.height, groups), warnings

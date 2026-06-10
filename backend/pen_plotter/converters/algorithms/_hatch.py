"""Shared sweep-line rasteriser for the hatching family.

``crosshatch._line_segments`` and ``eulerian_hatch._sweep_segments``
used to carry near-identical Python loops that walked the rasterised
``valid`` array element-by-element — millions of iterations per angle
on a 2400 px canvas. Both now delegate to :func:`sweep_segments`,
which detects on-mask runs with a vectorised diff/flatnonzero pass.
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray


def sweep_segments(
    mask: NDArray[np.bool_],
    angle_deg: float,
    spacing_px: float,
) -> list[list[tuple[float, float, float, float]]]:
    """Sweep parallel lines at ``angle_deg`` and return per-sweep segments.

    Each entry of the result corresponds to one sweep line (walking the
    perpendicular axis in ``spacing_px`` steps) and lists the maximal
    on-mask runs along it as ``(x1, y1, x2, y2)`` segments. Callers that
    don't care about the grouping (crosshatch) simply flatten the list;
    ``eulerian_hatch`` uses the grouping to chain consecutive sweeps
    into boustrophedon polylines.
    """
    height, width = mask.shape
    diag = math.hypot(width, height)
    theta = math.radians(angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    centre_x, centre_y = width / 2.0, height / 2.0
    samples = max(2, int(diag * 2))
    # ``along`` walks the line, ``across`` walks the spacing axis.
    along_t = np.linspace(-diag, diag, samples)
    spacing = max(1.0, spacing_px)
    across_t = np.arange(-diag, diag + spacing, spacing)
    per_sweep: list[list[tuple[float, float, float, float]]] = []
    for s in across_t:
        ox = centre_x + s * -sin_t
        oy = centre_y + s * cos_t
        xs = ox + along_t * cos_t
        ys = oy + along_t * sin_t
        # Convert to integer pixel indices, then collect the consecutive
        # runs where the rasterised pixel is inside the mask.
        ix = np.round(xs).astype(np.intp)
        iy = np.round(ys).astype(np.intp)
        inside = (ix >= 0) & (ix < width) & (iy >= 0) & (iy < height)
        valid = np.zeros_like(inside)
        valid[inside] = mask[iy[inside], ix[inside]]
        # Vectorised run detection: pad with zeros so a run touching the
        # array edge still produces a matching +1/-1 transition pair.
        delta = np.diff(np.concatenate(([0], valid.astype(np.int8), [0])))
        starts = np.flatnonzero(delta == 1)
        ends = np.flatnonzero(delta == -1)  # exclusive end index
        per_sweep.append(
            [
                (float(xs[a]), float(ys[a]), float(xs[b - 1]), float(ys[b - 1]))
                for a, b in zip(starts, ends, strict=True)
            ]
        )
    return per_sweep

"""Flow field streamline algorithm.

Builds a 2D vector field over the mask bounding box and integrates a
set of seeded streamlines forward + backward via RK2, stopping each
streamline when it exits the mask, collides with another streamline,
or reaches the step cap. Each streamline becomes one polyline — long,
continuous trajectories that look natural and lift the pen far less
than a dense halftone or stipple. Inspired by ``vpype-flow-imager``
(MIT, https://github.com/serycjon/vpype-flow-imager).

Two field sources:

- ``gradient``: Sobel gradient of the mask distance transform, rotated
  90° so streamlines flow *along* the mask rather than into its
  boundaries.
- ``perlin``: smooth procedural noise field for an organic look,
  independent of the mask shape.

When ``options["intensity"]`` is supplied (2D float array, same shape
as the mask) and ``mode="gradient"`` is selected, the gradient is
computed from that intensity instead of the mask — produces tonal
streamlines following the source image's brightness gradient.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar
from xml.sax.saxutils import quoteattr

import numpy as np
from numpy.typing import NDArray

from pen_plotter.converters.algorithms.base import RasterAlgorithm


def _gradient_field(
    intensity: NDArray[np.float32],
) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
    """Return (vx, vy): unit vectors perpendicular to ``∇intensity``."""
    try:
        from skimage.filters import sobel_h, sobel_v  # type: ignore[import-untyped]
        gy = sobel_h(intensity).astype(np.float32)
        gx = sobel_v(intensity).astype(np.float32)
    except ImportError:
        gy, gx = np.gradient(intensity)
        gy = gy.astype(np.float32)
        gx = gx.astype(np.float32)
    # Rotate 90° so streamlines run along iso-intensity lines.
    vx, vy = -gy, gx
    norm = np.sqrt(vx * vx + vy * vy) + 1e-9
    return (vx / norm).astype(np.float32), (vy / norm).astype(np.float32)


def _perlin_field(
    shape: tuple[int, int],
    *,
    scale: float,
    seed: int,
) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
    """Cheap value-noise-based smooth flow field.

    True Perlin would be nicer but pulls in a dep we don't need: a
    bilinearly-interpolated random grid is visually indistinguishable
    at the scales the plotter uses.
    """
    rng = np.random.default_rng(seed)
    h, w = shape
    grid_h = max(2, int(h / max(4.0, scale)))
    grid_w = max(2, int(w / max(4.0, scale)))
    coarse = rng.uniform(-1.0, 1.0, size=(grid_h, grid_w)).astype(np.float32)
    # Bilinear upsample using numpy slicing.
    y_idx = np.linspace(0, grid_h - 1, h)
    x_idx = np.linspace(0, grid_w - 1, w)
    y0 = np.floor(y_idx).astype(np.intp)
    x0 = np.floor(x_idx).astype(np.intp)
    y1 = np.clip(y0 + 1, 0, grid_h - 1)
    x1 = np.clip(x0 + 1, 0, grid_w - 1)
    ty = (y_idx - y0).astype(np.float32)[:, None]
    tx = (x_idx - x0).astype(np.float32)[None, :]
    c00 = coarse[np.ix_(y0, x0)]
    c01 = coarse[np.ix_(y0, x1)]
    c10 = coarse[np.ix_(y1, x0)]
    c11 = coarse[np.ix_(y1, x1)]
    angle_field = (
        c00 * (1 - ty) * (1 - tx)
        + c01 * (1 - ty) * tx
        + c10 * ty * (1 - tx)
        + c11 * ty * tx
    ) * math.pi
    vx = np.cos(angle_field).astype(np.float32)
    vy = np.sin(angle_field).astype(np.float32)
    return vx, vy


def _integrate_streamline(
    vx: NDArray[np.float32],
    vy: NDArray[np.float32],
    mask: NDArray[np.bool_],
    occupancy: NDArray[np.bool_],
    seed_xy: tuple[float, float],
    *,
    step: float,
    max_steps: int,
    direction: int,
) -> list[tuple[float, float]]:
    h, w = mask.shape
    x, y = seed_xy
    path: list[tuple[float, float]] = []
    for _ in range(max_steps):
        ix, iy = int(round(x)), int(round(y))
        if not (0 <= ix < w and 0 <= iy < h):
            break
        if not mask[iy, ix]:
            break
        # Occupancy on a coarse grid so streamlines spread apart.
        if occupancy[iy, ix]:
            break
        occupancy[iy, ix] = True
        path.append((x, y))
        # RK2: average velocity at start and after a half-step.
        dx = float(vx[iy, ix]) * direction
        dy = float(vy[iy, ix]) * direction
        midx, midy = x + dx * step * 0.5, y + dy * step * 0.5
        mix, miy = int(round(midx)), int(round(midy))
        if 0 <= mix < w and 0 <= miy < h:
            dx2 = float(vx[miy, mix]) * direction
            dy2 = float(vy[miy, mix]) * direction
            dx = (dx + dx2) * 0.5
            dy = (dy + dy2) * 0.5
        x += dx * step
        y += dy * step
    return path


class FlowFieldAlgorithm(RasterAlgorithm):
    """Streamlines integrated on a gradient or Perlin vector field."""

    name: ClassVar[str] = "flowfield"
    description: ClassVar[str] = (
        "Long streamlines following the image gradient or smooth noise — "
        "few pen-lifts, organic feel."
    )

    def render_layer(
        self,
        mask: NDArray[Any],
        color_hex: str,
        label: str,
        *,
        options: dict[str, Any] | None = None,
    ) -> str:
        opts = options or {}
        mode = str(opts.get("mode", "gradient"))
        seed_spacing = max(2.0, float(opts.get("seed_spacing_px", 6.0)))
        step = max(0.1, float(opts.get("step_px", 0.8)))
        max_steps = max(10, int(opts.get("max_steps", 800)))
        bidirectional = bool(opts.get("bidirectional", True))
        noise_scale = max(4.0, float(opts.get("noise_scale", 32.0)))
        seed_rng = int(opts.get("seed", 0))
        bool_mask = mask.astype(bool)

        group_open = (
            f"<g inkscape:label={quoteattr(label)} stroke={quoteattr(color_hex)} "
            f'fill="none" stroke-width="0.6" stroke-linecap="round" '
            f'stroke-linejoin="round">'
        )
        if not bool_mask.any():
            return group_open + "</g>"

        if mode == "perlin":
            vx, vy = _perlin_field(bool_mask.shape, scale=noise_scale, seed=seed_rng)
        else:
            # Prefer caller-supplied intensity (greyscale tonal map) when
            # available — gives streamlines that follow the source image
            # rather than just the mask silhouette.
            intensity_opt = opts.get("intensity")
            if isinstance(intensity_opt, np.ndarray) and intensity_opt.shape == bool_mask.shape:
                intensity = intensity_opt.astype(np.float32)
            else:
                # Distance transform of the mask gives a smooth interior
                # gradient even without caller-supplied intensity.
                try:
                    from scipy.ndimage import distance_transform_edt  # type: ignore[import-untyped]
                    intensity = distance_transform_edt(bool_mask).astype(np.float32)
                except ImportError:
                    intensity = bool_mask.astype(np.float32)
            vx, vy = _gradient_field(intensity)

        # Seed points on a grid stepped by seed_spacing, restricted to mask.
        h, w = bool_mask.shape
        ys = np.arange(seed_spacing / 2.0, h, seed_spacing)
        xs = np.arange(seed_spacing / 2.0, w, seed_spacing)
        gy, gx = np.meshgrid(ys, xs, indexing="ij")
        seeds = np.column_stack([gx.ravel(), gy.ravel()])
        # Jitter so the grid pattern isn't visible in the result.
        rng = np.random.default_rng(seed_rng)
        seeds += rng.uniform(-seed_spacing / 4.0, seed_spacing / 4.0, size=seeds.shape)
        occupancy = np.zeros_like(bool_mask)

        parts: list[str] = []
        for sx, sy in seeds:
            ix, iy = int(round(sx)), int(round(sy))
            if not (0 <= ix < w and 0 <= iy < h):
                continue
            if not bool_mask[iy, ix] or occupancy[iy, ix]:
                continue
            fwd = _integrate_streamline(
                vx, vy, bool_mask, occupancy, (sx, sy),
                step=step, max_steps=max_steps, direction=1,
            )
            if bidirectional:
                bwd = _integrate_streamline(
                    vx, vy, bool_mask, occupancy, (sx, sy),
                    step=step, max_steps=max_steps, direction=-1,
                )
                # Reverse backward path and stitch in front of forward.
                if len(bwd) > 1:
                    full = list(reversed(bwd)) + fwd[1:]
                else:
                    full = fwd
            else:
                full = fwd
            if len(full) < 2:
                continue
            pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in full)
            parts.append(f'<polyline points="{pts}"/>')
        return group_open + "".join(parts) + "</g>"

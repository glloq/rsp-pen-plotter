# The CIE Lab + ΔE 2000 math below uses the upper-case variable names
# from the CIEDE2000 reference paper (L, L1, L_bar, …). Renaming them
# obscures the formula — keeping the standard notation lets the math be
# audited side-by-side with the paper. Silence ruff's N806 for this file.
# ruff: noqa: N806
"""Auto-attribution of cluster centroids to owned inks via CIE Lab ΔE.

Multicolour segmentation (kmeans, fixed_palette without a snap pool)
produces clusters whose centroid RGB is an arbitrary blend of the
source image's pixels — almost never the exact hex of an ink the
operator actually owns. The G-code prompt "Change to ``#a3b4c5``"
that surfaces during a tool change is therefore unactionable unless
the operator can read intent into the value.

This module closes that gap: for every layer, the centroid colour is
snapped to the nearest hex from the active palette pool (installed
pens, the available-colours inventory, or the union of both — driven
by the ``palette_source`` setting). The snap is computed in CIE Lab
with ΔE 2000 so perceptual closeness matches what the operator sees
on the swatch strip, not just RGB-euclidean.

The output is the layer's ``assigned_color_hex`` field. The operator
can pin a manual choice per layer via the editor; calling
``auto_assign_layer_colors`` again skips those rows (the
``color_assignment == "manual"`` guard) and only refreshes
``"auto"`` rows — so editing the inventory or swapping pens doesn't
stomp explicit assignments.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from pen_plotter.models import LayerInfo


def _hex_to_rgb(hex_value: str) -> tuple[int, int, int]:
    """Lower / strip / parse ``#rrggbb`` → ``(r, g, b)`` ints in 0..255."""
    body = hex_value.lstrip("#").lower()
    if len(body) == 3:
        body = "".join(ch * 2 for ch in body)
    return int(body[0:2], 16), int(body[2:4], 16), int(body[4:6], 16)


def _normalise_hex(hex_value: str) -> str:
    """Canonical ``#rrggbb`` form so dedup/comparison stay case-insensitive."""
    r, g, b = _hex_to_rgb(hex_value)
    return f"#{r:02x}{g:02x}{b:02x}"


def _rgb_to_xyz(rgb: NDArray[np.float64]) -> NDArray[np.float64]:
    """SRGB ``(N, 3)`` in 0..1 → CIE XYZ ``(N, 3)`` (D65 reference white).

    Uses the IEC 61966-2-1 piecewise-gamma curve. Same conversion the
    scikit-image / colour-science libraries apply; reimplemented here
    so this module avoids pulling in a third-party dependency for a
    handful of vector ops.
    """
    mask = rgb > 0.04045
    linear = np.where(mask, ((rgb + 0.055) / 1.055) ** 2.4, rgb / 12.92)
    # Standard sRGB → XYZ matrix (D65).
    matrix = np.array(
        [
            [0.4124564, 0.3575761, 0.1804375],
            [0.2126729, 0.7151522, 0.0721750],
            [0.0193339, 0.1191920, 0.9503041],
        ]
    )
    return linear @ matrix.T  # type: ignore[no-any-return]


def _xyz_to_lab(xyz: NDArray[np.float64]) -> NDArray[np.float64]:
    """CIE XYZ ``(N, 3)`` → CIE Lab ``(N, 3)`` (D65 reference white)."""
    # D65 reference white.
    ref = np.array([0.95047, 1.00000, 1.08883])
    normalized = xyz / ref
    delta = 6.0 / 29.0
    delta3 = delta**3
    mask = normalized > delta3
    f = np.where(
        mask,
        np.cbrt(normalized, where=mask, out=np.zeros_like(normalized)),
        (normalized / (3 * delta**2)) + (4.0 / 29.0),
    )
    L = 116.0 * f[..., 1] - 16.0
    a = 500.0 * (f[..., 0] - f[..., 1])
    b = 200.0 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)


def _hexes_to_lab(hexes: list[str]) -> NDArray[np.float64]:
    """Vector convert a list of hex strings to Lab coordinates."""
    if not hexes:
        return np.zeros((0, 3), dtype=np.float64)
    rgb = np.array([_hex_to_rgb(h) for h in hexes], dtype=np.float64) / 255.0
    return _xyz_to_lab(_rgb_to_xyz(rgb))


def _delta_e_2000(lab1: NDArray[np.float64], lab2: NDArray[np.float64]) -> NDArray[np.float64]:
    """Compute ΔE 2000 between two Lab arrays of matching shape.

    Inputs are ``(N, 3)`` arrays; output is the ``(N,)`` per-row distance.
    Faithful to the CIEDE2000 reference equations — the implementation
    is dense but pure-numpy, so it stays vectorised over hundreds of
    candidates without measurable overhead.
    """
    L1, a1, b1 = lab1[..., 0], lab1[..., 1], lab1[..., 2]
    L2, a2, b2 = lab2[..., 0], lab2[..., 1], lab2[..., 2]
    c1 = np.hypot(a1, b1)
    c2 = np.hypot(a2, b2)
    c_bar = (c1 + c2) / 2.0
    g = 0.5 * (1.0 - np.sqrt(c_bar**7 / (c_bar**7 + 25.0**7)))
    a1p = (1.0 + g) * a1
    a2p = (1.0 + g) * a2
    c1p = np.hypot(a1p, b1)
    c2p = np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360.0
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360.0
    dLp = L2 - L1
    dCp = c2p - c1p
    dhp = h2p - h1p
    dhp = np.where(dhp > 180.0, dhp - 360.0, dhp)
    dhp = np.where(dhp < -180.0, dhp + 360.0, dhp)
    dHp = 2.0 * np.sqrt(c1p * c2p) * np.sin(np.radians(dhp) / 2.0)
    L_bar = (L1 + L2) / 2.0
    c_bar_p = (c1p + c2p) / 2.0
    h_bar = (h1p + h2p) / 2.0
    h_bar = np.where(np.abs(h1p - h2p) > 180.0, h_bar + 180.0, h_bar)
    h_bar = h_bar % 360.0
    t = (
        1.0
        - 0.17 * np.cos(np.radians(h_bar - 30.0))
        + 0.24 * np.cos(np.radians(2.0 * h_bar))
        + 0.32 * np.cos(np.radians(3.0 * h_bar + 6.0))
        - 0.20 * np.cos(np.radians(4.0 * h_bar - 63.0))
    )
    sL = 1.0 + (0.015 * (L_bar - 50.0) ** 2) / np.sqrt(20.0 + (L_bar - 50.0) ** 2)
    sC = 1.0 + 0.045 * c_bar_p
    sH = 1.0 + 0.015 * c_bar_p * t
    rT = (
        -2.0
        * np.sqrt(c_bar_p**7 / (c_bar_p**7 + 25.0**7))
        * np.sin(np.radians(60.0 * np.exp(-(((h_bar - 275.0) / 25.0) ** 2))))
    )
    return np.sqrt(  # type: ignore[no-any-return]
        (dLp / sL) ** 2 + (dCp / sC) ** 2 + (dHp / sH) ** 2 + rT * (dCp / sC) * (dHp / sH)
    )


@dataclass(frozen=True)
class _NearestResult:
    """Internal: nearest pool hex + the ΔE distance that won."""

    hex: str
    delta_e: float


def nearest_pool_hex(source_hex: str, pool: list[str]) -> _NearestResult | None:
    """Return the pool entry closest to ``source_hex`` in ΔE 2000.

    Args:
        source_hex: The colour we want to snap (typically a cluster centroid).
        pool: Candidate hexes — installed pens / available inventory / union.

    Returns:
        A ``_NearestResult`` carrying the winning hex and its distance,
        or ``None`` when the pool is empty.
    """
    if not pool:
        return None
    source_lab = _hexes_to_lab([source_hex])
    pool_lab = _hexes_to_lab(pool)
    distances = _delta_e_2000(np.broadcast_to(source_lab, pool_lab.shape), pool_lab)
    idx = int(np.argmin(distances))
    return _NearestResult(hex=_normalise_hex(pool[idx]), delta_e=float(distances[idx]))


def auto_assign_layer_colors(
    layers: list[LayerInfo], pool: list[str], *, force: bool = False
) -> list[LayerInfo]:
    """Assign each layer an ink from ``pool``, keeping inks distinct.

    A plain per-layer nearest-match collapses distinct clusters onto the
    same ink as soon as the cluster count grows past the pool's spread
    (6 clusters / 4 pens → 2-3 visible colours): several centroids share
    one nearest pen and the preview repaints them identically. Instead,
    auto rows are matched greedily by ascending ΔE 2000 **without
    reusing a pool entry** while unused entries remain — so N clusters
    against N+ pens always come out as N distinct inks. Only once the
    pool is exhausted do the remaining layers fall back to plain
    nearest-match (reuse allowed). Duplicate pool entries count as that
    many uses, matching a rack with two identical pens.

    Args:
        layers: Layer records, possibly carrying manual overrides
            (``color_assignment == "manual"``) that this call must preserve.
            Preserved manual picks consume their matching pool entry so the
            auto rows spread over the remaining inks.
        pool: Candidate hexes for the snap. When empty the assignment is
            cleared (``assigned_color_hex = None``) so the G-code path
            falls back to the raw centroid.
        force: When ``True``, re-snap even ``"manual"`` rows. Used by the
            "reset all to auto" affordance; the default leaves overrides
            untouched.

    Returns:
        A new list (the inputs are not mutated) with ``assigned_color_hex``
        + ``color_assignment`` filled in per layer.
    """
    if not pool:
        # No pool to snap against → drop any stale auto value so the
        # downstream rendering uses ``source_color`` cleanly.
        return [
            layer
            if (not force and layer.color_assignment == "manual")
            else layer.model_copy(update={"assigned_color_hex": None, "color_assignment": "auto"})
            for layer in layers
        ]

    pool_hex = [_normalise_hex(h) for h in pool]
    pool_lab = _hexes_to_lab(pool_hex)
    available = [True] * len(pool_hex)

    auto_indices: list[int] = []
    for idx, layer in enumerate(layers):
        if not force and layer.color_assignment == "manual":
            # A pinned ink consumes one matching pool entry so the auto
            # rows spread over the rest of the rack.
            if layer.assigned_color_hex:
                pinned = _normalise_hex(layer.assigned_color_hex)
                for j, h in enumerate(pool_hex):
                    if available[j] and h == pinned:
                        available[j] = False
                        break
            continue
        auto_indices.append(idx)

    # Distance matrix auto-rows × pool, then globally-greedy unique
    # matching: repeatedly take the smallest remaining (layer, ink) ΔE
    # among unassigned layers and unused entries. Greedy (not Hungarian)
    # keeps the code obvious; with the handful of pens/clusters involved
    # the difference is imperceptible.
    assigned: dict[int, str] = {}
    if auto_indices:
        src_lab = _hexes_to_lab([layers[i].source_color for i in auto_indices])
        n, k = len(auto_indices), len(pool_hex)
        dist = np.empty((n, k), dtype=np.float64)
        for col in range(k):
            dist[:, col] = _delta_e_2000(src_lab, np.broadcast_to(pool_lab[col], src_lab.shape))
        order = np.dstack(np.unravel_index(np.argsort(dist, axis=None), dist.shape))[0]
        row_done = [False] * n
        remaining = n
        for row, col in order:
            if remaining == 0 or not any(available):
                break
            if row_done[row] or not available[col]:
                continue
            assigned[auto_indices[int(row)]] = pool_hex[int(col)]
            row_done[int(row)] = True
            available[int(col)] = False
            remaining -= 1

    out: list[LayerInfo] = []
    for idx, layer in enumerate(layers):
        if not force and layer.color_assignment == "manual":
            out.append(layer)
            continue
        hex_value = assigned.get(idx)
        if hex_value is None:
            # Pool exhausted (more clusters than inks) → plain nearest.
            nearest = nearest_pool_hex(layer.source_color, pool_hex)
            hex_value = nearest.hex if nearest else None
        out.append(
            layer.model_copy(
                update={"assigned_color_hex": hex_value, "color_assignment": "auto"}
            )
        )
    return out

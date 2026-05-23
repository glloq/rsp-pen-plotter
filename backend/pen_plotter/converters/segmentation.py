"""Image segmentation methods (the "decoupage" step).

Each method takes an RGB image and turns it into a ``(labels, palette)``
pair, where ``labels`` assigns every pixel to a cluster and ``palette``
lists the cluster centroids as RGB tuples. Downstream the converter
renders one SVG layer per cluster via a pluggable raster algorithm.

Methods
-------
* :func:`kmeans` — colour clustering in RGB space (the original behaviour).
* :func:`luminance_bands` — slice the greyscale image into N equal bands.
* :func:`thresholds` — slice on operator-provided luminance breakpoints.
* :func:`fixed_palette` — snap each pixel to its nearest operator-supplied
  colour. Lets the operator pin the output to the actual pens installed.

Post-processing
---------------
* :func:`drop_small_regions` removes clusters smaller than ``min_pixels``
  (anti-noise on shaky photos).
* :func:`merge_similar_colours` collapses clusters whose centroids are
  closer than ``threshold`` in CIE Lab ΔE — avoids near-duplicate layers.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import numpy as np
from numpy.typing import NDArray
from PIL import Image
from sklearn.cluster import KMeans

_REC709 = np.array([0.2126, 0.7152, 0.0722])


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    """Parse ``#rgb``, ``#rrggbb`` or ``rrggbb`` into a tuple."""
    h = value.lstrip("#").strip()
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        raise ValueError(f"Invalid hex colour: {value!r}")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _greyscale(image: Image.Image) -> NDArray[np.float64]:
    """Return a (H, W) float array in 0..1 from an RGB image."""
    arr = np.asarray(image, dtype=np.float64) / 255.0
    return arr @ _REC709


def kmeans(
    image: Image.Image, *, num_colors: int, n_init: int = 10
) -> tuple[NDArray[np.intp], NDArray[np.uint8]]:
    """Cluster pixels into ``num_colors`` clusters in RGB space."""
    arr = np.asarray(image, dtype=np.float64).reshape(-1, 3)
    k = min(num_colors, max(1, np.unique(arr, axis=0).shape[0]))
    model = KMeans(n_clusters=k, n_init=n_init, random_state=0)
    flat_labels = model.fit_predict(arr)
    palette = model.cluster_centers_.round().astype(np.uint8)
    labels = flat_labels.reshape(image.height, image.width).astype(np.intp)
    return labels, palette


def luminance_bands(
    image: Image.Image, *, num_bands: int
) -> tuple[NDArray[np.intp], NDArray[np.uint8]]:
    """Slice the image into ``num_bands`` equal-width luminance bands.

    The palette is a greyscale ramp from black (darkest band) to white
    (lightest), so the downstream renderer draws darker layers with darker
    pens when the operator assigns them by colour.
    """
    bands = max(1, num_bands)
    grey = _greyscale(image)
    # Linear breakpoints: [1/N, 2/N, ..., (N-1)/N]. ``np.digitize`` returns
    # 0..N for values below/above each breakpoint, which is exactly the
    # cluster index we want.
    breakpoints = np.linspace(0.0, 1.0, bands + 1)[1:-1]
    labels = np.digitize(grey, breakpoints).astype(np.intp)
    centres = (np.arange(bands) + 0.5) / bands
    palette = np.tile((centres * 255).round().astype(np.uint8)[:, None], (1, 3))
    return labels, palette


def thresholds(
    image: Image.Image, *, levels: Sequence[float]
) -> tuple[NDArray[np.intp], NDArray[np.uint8]]:
    """Slice the image on operator-provided luminance thresholds.

    ``levels`` is a list of cutoffs in 0..1. ``N`` cutoffs produce ``N+1``
    layers; the palette assigns the midpoint luminance of each band so
    layer order matches darkness.
    """
    breakpoints = sorted(float(x) for x in levels if 0.0 <= float(x) <= 1.0)
    if not breakpoints:
        # No thresholds → single layer with the average luminance colour.
        grey = _greyscale(image)
        mean = float(np.clip(grey.mean(), 0.0, 1.0))
        labels = np.zeros(grey.shape, dtype=np.intp)
        palette = np.array([[round(mean * 255)] * 3], dtype=np.uint8)
        return labels, palette
    grey = _greyscale(image)
    labels = np.digitize(grey, breakpoints).astype(np.intp)
    edges = [0.0, *breakpoints, 1.0]
    midpoints = [(edges[i] + edges[i + 1]) / 2 for i in range(len(edges) - 1)]
    palette = np.array(
        [[round(m * 255)] * 3 for m in midpoints], dtype=np.uint8
    )
    return labels, palette


def fixed_palette(
    image: Image.Image, *, palette_hex: Iterable[str]
) -> tuple[NDArray[np.intp], NDArray[np.uint8]]:
    """Snap every pixel to the nearest colour in a user-defined palette.

    Distance is Euclidean in RGB — good enough for the small palettes the
    operator will typically use (matching their pen rack). For wider
    palettes we'd switch to Lab, but the cost isn't justified here.
    """
    colours = [_hex_to_rgb(h) for h in palette_hex]
    if not colours:
        raise ValueError("Fixed palette must contain at least one colour")
    palette = np.array(colours, dtype=np.uint8)
    pixels = np.asarray(image, dtype=np.float64).reshape(-1, 3)
    # (P, K) distance matrix; we keep argmin per pixel.
    diffs = pixels[:, None, :] - palette[None, :, :].astype(np.float64)
    sq = np.einsum("pkc,pkc->pk", diffs, diffs)
    flat_labels = sq.argmin(axis=1).astype(np.intp)
    labels = flat_labels.reshape(image.height, image.width)
    return labels, palette


# ---------------------------------------------------------------- post-process


def drop_small_regions(
    labels: NDArray[np.intp], min_pixels: int
) -> NDArray[np.intp]:
    """Reassign connected components smaller than ``min_pixels`` to their
    most-frequent neighbouring label.

    No-op when ``min_pixels <= 0`` or the input is uniform. We use
    ``scipy.ndimage.label`` to identify components within each cluster, then
    repaint each small one to the modal label among its 4-connected
    neighbours.
    """
    if min_pixels <= 0:
        return labels
    try:
        from scipy.ndimage import label as nd_label
    except ImportError:
        # scipy is a transitive dep of scikit-learn; if it's gone we degrade
        # gracefully instead of failing the whole conversion.
        return labels
    h, w = labels.shape
    out = labels.copy()
    for cluster in np.unique(labels):
        mask = labels == cluster
        components, count = nd_label(mask)
        if count == 0:
            continue
        sizes = np.bincount(components.ravel())
        for comp_idx in range(1, count + 1):
            if sizes[comp_idx] >= min_pixels:
                continue
            ys, xs = np.where(components == comp_idx)
            # Sample 4-neighbours, vote for the most common other cluster.
            neighbours: list[int] = []
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                ny, nx = ys + dy, xs + dx
                inside = (ny >= 0) & (ny < h) & (nx >= 0) & (nx < w)
                if not inside.any():
                    continue
                cand = out[ny[inside], nx[inside]]
                neighbours.extend(int(v) for v in cand if int(v) != int(cluster))
            if not neighbours:
                continue
            replacement = max(set(neighbours), key=neighbours.count)
            out[ys, xs] = replacement
    return out


def merge_similar_colours(
    labels: NDArray[np.intp], palette: NDArray[np.uint8], threshold: float
) -> tuple[NDArray[np.intp], NDArray[np.uint8]]:
    """Collapse palette entries closer than ``threshold`` in CIE Lab ΔE.

    The clusters being merged inherit the lowest-indexed label of the group.
    The palette is rewritten so its indices line up with the new label
    space; downstream code keeps working without further changes.
    """
    if threshold <= 0 or len(palette) <= 1:
        return labels, palette
    lab = _rgb_to_lab(palette.astype(np.float64) / 255.0)
    n = len(palette)
    # Union-Find for transitive merging (A close to B, B close to C → all one).
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for i in range(n):
        for j in range(i + 1, n):
            if np.linalg.norm(lab[i] - lab[j]) < threshold:
                union(i, j)

    roots = sorted({find(i) for i in range(n)})
    remap = {old: new for new, old in enumerate(roots)}
    new_labels = np.vectorize(lambda v: remap[find(int(v))])(labels).astype(np.intp)
    new_palette = palette[roots]
    return new_labels, new_palette


def _rgb_to_lab(rgb: NDArray[np.float64]) -> NDArray[np.float64]:
    """Convert linear-ish sRGB in 0..1 to CIE Lab.

    Standard D65 illuminant; ``rgb`` is assumed approximately sRGB-encoded
    (the gamma step is folded into the cube-root in the XYZ→Lab leg, which
    is the textbook formula).
    """
    # sRGB → linear
    lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    m = np.array(
        [
            [0.4124564, 0.3575761, 0.1804375],
            [0.2126729, 0.7151522, 0.0721750],
            [0.0193339, 0.1191920, 0.9503041],
        ]
    )
    xyz = lin @ m.T
    # Normalise to D65 white point.
    white = np.array([0.95047, 1.00000, 1.08883])
    f = xyz / white
    eps = (6 / 29) ** 3
    f = np.where(f > eps, np.cbrt(f), f / (3 * (6 / 29) ** 2) + 4 / 29)
    L = 116.0 * f[..., 1] - 16.0
    a = 500.0 * (f[..., 0] - f[..., 1])
    b = 200.0 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)

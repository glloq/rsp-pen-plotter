"""Cacheable bitmap conversion artefacts.

``SegmentationResult`` stores the slow, deterministic parts of the
pipeline (the cluster ``labels`` array and the ``palette`` of centroid
RGBs) so the ``/rerender`` endpoint can swap a single layer's
rendering algorithm without paying for the k-means / threshold pass
again — segmentation is the expensive step on a Pi, rendering each
layer is comparatively cheap.

Kept in its own module so future cache plumbing (eviction policies,
on-disk serialisation, etc.) can land here without touching the
segmentation or render code paths.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass
class SegmentationResult:
    """The parts of a bitmap conversion that survive between requests.

    Stored in the ``/rerender`` cache so the operator can swap a single
    layer's rendering algorithm without paying for the k-means pass again
    (which is the slow step on a Pi).
    """

    labels: NDArray[np.intp]
    palette: NDArray[np.uint8]
    width: int
    height: int

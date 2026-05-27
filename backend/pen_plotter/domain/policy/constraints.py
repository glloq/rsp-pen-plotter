"""Hard constraints from audit #4 §4.

These run **after** the per-source-kind matrix has produced a base
recommendation; they may override the chosen algorithm to keep the
preview snappy, the mono-pen flow coherent, or a near-monochrome image
on a sensible algorithm.

Each constraint is applied once. When it overrides the algorithm it
records a :class:`ConstraintHit` so the modal can show the operator
"on a basculé sur scanlines parce que l'image fait 12 MP".
"""

from __future__ import annotations

from pen_plotter.domain.policy.types import ConstraintHit, Goal, PolicyInput

# Algorithms forbidden by the "heavy + non-quality input" rule (audit
# #4 §4 first bullet). The matrix entry for the BALANCED bucket may
# legitimately propose a heavy algorithm; we strip it down here.
HEAVY_ALGORITHMS: frozenset[str] = frozenset(
    {"tsp", "tsp_opt", "voronoi_stipple", "flowfield"}
)

# When the heavy rule fires the recommendation is forced into this
# allowlist (ordered from most ink-economical to most line-economical).
HEAVY_FALLBACKS: tuple[str, ...] = ("scanlines", "halftone", "direct")

# When ``available_colors_count`` is ≤ 2 the resolver prefers algorithms
# whose output reads cleanly on tiny palettes. Same shape as above.
SPARSE_PALETTE_PREFERRED: tuple[str, ...] = ("scanlines", "crosshatch", "direct")

MEGAPIXEL_HEAVY_THRESHOLD = 8.0


def apply(
    inp: PolicyInput,
    algorithm: str,
    fallback_chain: list[str],
) -> tuple[str, list[str], list[ConstraintHit]]:
    """Apply hard constraints to a candidate ``(algorithm, fallback_chain)``.

    Returns the (possibly overridden) algorithm, the updated fallback
    chain (heavy candidates stripped), and the list of constraints
    that fired.
    """
    hits: list[ConstraintHit] = []

    if inp.is_mono_pen_machine:
        hits.append(
            ConstraintHit(
                constraint="mono_pen_machine",
                description=(
                    "Machine mono-pen : la séparation couleur est désactivée, "
                    "les variantes de densité/passes sont utilisées à la place."
                ),
            )
        )

    too_big = (
        inp.image_megapixels is not None
        and inp.image_megapixels > MEGAPIXEL_HEAVY_THRESHOLD
        and inp.goal is not Goal.QUALITY
    )
    if too_big:
        if algorithm in HEAVY_ALGORITHMS:
            previous = algorithm
            algorithm = HEAVY_FALLBACKS[0]
            hits.append(
                ConstraintHit(
                    constraint="heavy_algo_on_large_input",
                    description=(
                        f"Image {inp.image_megapixels:.1f} MP en mode "
                        f"{inp.goal.value} — algo lourd '{previous}' "
                        f"remplacé par '{algorithm}'."
                    ),
                    forbidden_algorithms=sorted(HEAVY_ALGORITHMS),
                )
            )
        fallback_chain = [a for a in fallback_chain if a not in HEAVY_ALGORITHMS]

    if 0 < inp.available_colors_count <= 2:
        if algorithm not in SPARSE_PALETTE_PREFERRED:
            previous = algorithm
            algorithm = SPARSE_PALETTE_PREFERRED[0]
            hits.append(
                ConstraintHit(
                    constraint="sparse_palette",
                    description=(
                        f"Palette ≤ 2 couleurs disponibles — algo '{previous}' "
                        f"remplacé par '{algorithm}'."
                    ),
                )
            )

    return algorithm, fallback_chain, hits

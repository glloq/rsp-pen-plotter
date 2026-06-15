"""Main entry point — :func:`resolve` glues matrix + constraints together.

Audit #4 pipeline:

    PolicyInput
      -> rule lookup (per source_kind, goal)
      -> derive segmentation method (palette_mode dependent)
      -> assemble reasoning trail
      -> apply hard constraints (mega-pixels / sparse palette)
      -> PolicyDecision
"""

from __future__ import annotations

from copy import deepcopy

from pen_plotter.domain.policy import constraints, rules
from pen_plotter.domain.policy.types import (
    PolicyDecision,
    PolicyInput,
    RuleHit,
)


def _palette_cap_options(
    options: dict[str, object],
    *,
    source_kind: str,
    available_colors_count: int,
) -> tuple[dict[str, object], RuleHit | None]:
    """Cap ``num_colors`` to the palette and record a reasoning entry.

    Several matrix entries propose ``num_colors=min(available, N)`` —
    rather than special-casing each, we honour it once here.
    """
    if available_colors_count <= 0:
        return options, None

    capped: dict[str, object] = dict(options)
    target_caps: dict[str, int] = {
        # Photo/fast scanlines → cap at 4.
        "bitmap_photo": 4,
        # Illustration/fast direct → cap at 6.
        "bitmap_illustration": 6,
    }
    target = target_caps.get(source_kind)
    if target is None:
        return capped, None

    num = min(target, max(1, available_colors_count))
    capped["num_colors"] = num
    hit = RuleHit(
        rule="palette.num_colors_capped",
        description=(
            f"num_colors = min({target}, available_colors_count="
            f"{available_colors_count}) = {num}."
        ),
    )
    return capped, hit


def resolve(inp: PolicyInput) -> PolicyDecision:
    """Compute the recommended algorithm + parameters for ``inp``."""
    base = rules.lookup(inp.source_kind, inp.goal)
    reasoning: list[RuleHit] = [
        RuleHit(
            rule=f"{inp.source_kind.value}.{inp.goal.value}",
            description=base.rationale,
        )
    ]

    segmentation, seg_hit = rules.derive_segmentation(base, inp.source_kind, inp.palette_mode)
    if seg_hit is not None:
        reasoning.append(seg_hit)

    options = deepcopy(dict(base.options))
    options, palette_hit = _palette_cap_options(
        options,
        source_kind=inp.source_kind.value,
        available_colors_count=inp.available_colors_count,
    )
    if palette_hit is not None:
        reasoning.append(palette_hit)

    algorithm = base.algorithm
    fallback_chain = list(base.fallback_chain)
    algorithm, fallback_chain, constraint_hits = constraints.apply(inp, algorithm, fallback_chain)

    passes: list[dict[str, object]] = [deepcopy(dict(p)) for p in base.passes]

    # If a hard constraint forced the algorithm, the matrix-supplied
    # options are no longer relevant — fall back to whatever the
    # constraint-imposed algorithm uses out of the box. The multi-pass
    # stack is dropped too: it was tuned for the original algorithm.
    forced = any(
        c.constraint in {"heavy_algo_on_large_input", "sparse_palette"} for c in constraint_hits
    )
    if forced and algorithm != base.algorithm:
        options = {}
        passes = []

    # NOTE: mono-pen machines are no longer collapsed to a single colour.
    # A single-holder machine can still draw a multi-colour file — the
    # operator swaps the pen at each colour change (prompted by the
    # print-launch load modal / the mid-print pauses). The resolver
    # therefore picks colours purely from ``palette_mode`` /
    # ``available_colors_count``, exactly like a magazine machine.

    return PolicyDecision(
        segmentation_method=segmentation,
        default_algorithm=algorithm,
        default_options=options,
        default_passes=passes,
        quality_tier=base.quality,
        fallback_chain=fallback_chain,
        reasoning=reasoning,
        hard_constraints_applied=constraint_hits,
    )

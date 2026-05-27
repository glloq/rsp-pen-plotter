"""HTTP surface for the AlgorithmPolicyResolver (roadmap C.2).

Wraps :func:`pen_plotter.domain.policy.resolve` so the frontend modal
V2 can ask the backend for a recommendation given an intent + source
classification + available palette. The resolver is pure, so this
endpoint is a thin adapter — no caching, no side effects.
"""

from __future__ import annotations

from fastapi import APIRouter

from pen_plotter.domain.policy import PolicyDecision, PolicyInput, resolve

router = APIRouter()


@router.post("/policy/resolve")
async def resolve_policy(payload: PolicyInput) -> PolicyDecision:
    """Return the recommended algorithm + parameters for ``payload``.

    Mirrors the matrix from audit #4 (see ``backend/pen_plotter/domain/policy``).
    The reasoning trail in the response is what the modal V2 surfaces
    next to the recommendation as "Pourquoi ce choix ?".
    """
    return resolve(payload)

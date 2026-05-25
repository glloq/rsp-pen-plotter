"""Resolve a :class:`PrintPlan` against a machine profile.

This is the single funnel through which both ``preflight`` and ``generate``
flow. It applies profile defaults to ``None`` fields, validates business
invariants, marks missing pen slots, and computes a stable SHA-256 hash
over a canonical JSON representation of the resolved plan.

If you ever wonder "did preflight and generate see the same settings?",
compare the ``plan_hash`` of both responses — they must match.
"""

from __future__ import annotations

import hashlib
import json

from pen_plotter.domain.print_plan import (
    _DEFAULT_SIMPLIFY_TOLERANCE_MM,
    LayerPlan,
    PrintPlan,
    ResolvedLayer,
    ResolvedPlan,
)
from pen_plotter.domain.validators import PlanValidationError, validate_plan
from pen_plotter.models import MachineProfile


class PlanResolutionError(ValueError):
    """Raised when a plan cannot be resolved against a profile.

    Wraps :class:`PlanValidationError` so callers only need to catch one
    type at the application boundary.
    """


def _resolve_layer(
    layer: LayerPlan,
    profile_speed: float,
    installed_slots: set[int],
) -> ResolvedLayer:
    return ResolvedLayer(
        layer_id=layer.layer_id,
        target_pen_slot=layer.target_pen_slot,
        drawing_speed_mm_s=layer.drawing_speed_mm_s or profile_speed,
        source_color=layer.source_color,
        color_label=layer.color_label,
        pause_before=layer.pause_before,
        pen_slot_installed=(
            layer.target_pen_slot is None
            or layer.target_pen_slot in installed_slots
        ),
        optimize=layer.optimize,
        simplify_tolerance_mm=(
            layer.simplify_tolerance_mm
            if layer.simplify_tolerance_mm is not None
            else _DEFAULT_SIMPLIFY_TOLERANCE_MM
        ),
    )


def _hash_resolved(payload: dict[str, object]) -> str:
    """Compute a stable hash over the resolved payload.

    ``sort_keys`` plus ``separators`` give a single canonical encoding so
    the same logical plan always yields the same hex digest, regardless
    of dict ordering or Python version.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def resolve_plan(plan: PrintPlan, profile: MachineProfile) -> ResolvedPlan:
    """Apply defaults + validate + hash a print plan against a profile.

    Args:
        plan: The raw plan received from the client.
        profile: The active machine profile (already looked up by name).

    Returns:
        A :class:`ResolvedPlan` whose ``layers`` contain no ``None``
        speeds and whose ``plan_hash`` identifies this exact resolution.

    Raises:
        PlanResolutionError: If any layer/plan invariant fails.
    """
    try:
        validate_plan(plan)
    except PlanValidationError as exc:
        raise PlanResolutionError(str(exc)) from exc

    installed_slots = {
        pen.index for pen in profile.effective_pens() if pen.installed
    }
    profile_speed = profile.drawing_speed_mm_s

    resolved_layers = [
        _resolve_layer(layer, profile_speed, installed_slots) for layer in plan.layers
    ]

    # Hash the resolved layers + the immutable plan inputs. We exclude
    # ``metadata.created_at`` from the digest so re-resolving the same
    # plan a second later still yields the same hash — otherwise the
    # snapshot table would grow with duplicates on every preflight.
    hash_payload: dict[str, object] = {
        "profile_name": profile.name,
        "svg": plan.svg,
        "scale_mode": plan.scale_mode,
        "margin_mm": plan.margin_mm,
        "placement": plan.placement.model_dump() if plan.placement else None,
        "layers": [layer.model_dump() for layer in resolved_layers],
    }

    return ResolvedPlan(
        plan=plan,
        layers=resolved_layers,
        plan_hash=_hash_resolved(hash_payload),
        profile_name=profile.name,
        profile_drawing_speed_mm_s=profile_speed,
        mono_pen=profile.pen_slot_count <= 1,
    )

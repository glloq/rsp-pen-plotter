"""Business invariants for a :class:`PrintPlan`.

These checks run once per plan inside the application layer, before the
engines see anything. Centralising them here means ``preflight`` and
``generate`` cannot disagree on what counts as valid input.
"""

from __future__ import annotations

from pen_plotter.domain.print_plan import LayerPlan, PrintPlan


class PlanValidationError(ValueError):
    """Raised when a :class:`PrintPlan` violates an invariant."""


def validate_layer(layer: LayerPlan) -> None:
    """Validate a single layer's settings.

    Raises:
        PlanValidationError: If a per-layer setting is impossible.
    """
    if layer.drawing_speed_mm_s is not None and layer.drawing_speed_mm_s <= 0:
        raise PlanValidationError(
            f"Layer {layer.layer_id!r}: drawing_speed_mm_s must be > 0 "
            f"(got {layer.drawing_speed_mm_s})."
        )
    if layer.target_pen_slot is not None and layer.target_pen_slot < 0:
        raise PlanValidationError(
            f"Layer {layer.layer_id!r}: target_pen_slot must be >= 0 "
            f"(got {layer.target_pen_slot})."
        )
    if layer.simplify_tolerance_mm is not None and layer.simplify_tolerance_mm < 0:
        raise PlanValidationError(
            f"Layer {layer.layer_id!r}: simplify_tolerance_mm must be >= 0 "
            f"(got {layer.simplify_tolerance_mm})."
        )


def validate_plan(plan: PrintPlan) -> None:
    """Validate a full :class:`PrintPlan`.

    Currently delegates to :func:`validate_layer` for each layer and
    checks ``margin_mm`` is non-negative. The function is the single
    business-validation entry point so adding a new rule means editing
    this module alone.

    Raises:
        PlanValidationError: If any invariant fails.
    """
    if plan.margin_mm < 0:
        raise PlanValidationError(
            f"margin_mm must be >= 0 (got {plan.margin_mm})."
        )
    seen: set[str] = set()
    for layer in plan.layers:
        if layer.layer_id in seen:
            raise PlanValidationError(
                f"Duplicate layer_id {layer.layer_id!r} in plan."
            )
        seen.add(layer.layer_id)
        validate_layer(layer)

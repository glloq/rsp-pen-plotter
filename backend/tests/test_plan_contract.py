"""Contract tests for the shared ``PrintPlan`` pivot.

These tests guarantee the property the refactor was built around: a
single :class:`PrintPlan` submitted to both ``run_preflight`` and
``run_generate`` resolves to the **same** ``plan_hash``. If this
breaks, the refactor's central promise is broken — preflight and
generate would no longer be operating on identical inputs.
"""

from __future__ import annotations

import pytest

from pen_plotter.application.generate_service import run_generate
from pen_plotter.application.plan_resolver import (
    PlanResolutionError,
    resolve_plan,
)
from pen_plotter.application.preflight_service import run_preflight
from pen_plotter.domain.print_plan import LayerPlan, PrintPlan
from pen_plotter.profiles import get_profile

NS = (
    'xmlns="http://www.w3.org/2000/svg" '
    'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"'
)
TWO_LAYERS_SVG = (
    f'<svg {NS} viewBox="0 0 100 100">'
    '<g inkscape:label="red" stroke="#ff0000"><path d="M10 10 L90 10 L90 90"/></g>'
    '<g inkscape:label="blue" stroke="#0000ff"><path d="M10 50 L90 50"/></g>'
    "</svg>"
)


def _profile():
    profile = get_profile("Custom CoreXY A3")
    assert profile is not None
    return profile


def _plan() -> PrintPlan:
    return PrintPlan(
        svg=TWO_LAYERS_SVG,
        profile_name="Custom CoreXY A3",
        layers=[
            LayerPlan(
                layer_id="red",
                target_pen_slot=0,
                drawing_speed_mm_s=50.0,
                source_color="#ff0000",
                color_label="Red",
                pause_before="auto",
            ),
            LayerPlan(
                layer_id="blue",
                target_pen_slot=1,
                drawing_speed_mm_s=60.0,
                source_color="#0000ff",
                color_label="Blue",
                pause_before="auto",
            ),
        ],
        scale_mode="fit",
        margin_mm=10.0,
    )


def test_preflight_and_generate_share_plan_hash() -> None:
    """The single most important contract: same plan ⇒ same hash."""
    plan = _plan()
    profile = _profile()
    pre = run_preflight(plan, profile)
    gen = run_generate(plan, profile)
    assert pre.resolved.plan_hash == gen.resolved.plan_hash
    # And the resolved layer list matches field-for-field.
    assert pre.resolved.layers == gen.resolved.layers


def test_plan_hash_changes_when_any_layer_setting_changes() -> None:
    """Regression guard: a tweak in any setting MUST shift the hash."""
    plan = _plan()
    profile = _profile()
    baseline = resolve_plan(plan, profile).plan_hash

    # Toggle pen slot
    p2 = plan.model_copy(
        update={
            "layers": [
                plan.layers[0].model_copy(update={"target_pen_slot": 2}),
                plan.layers[1],
            ]
        }
    )
    assert resolve_plan(p2, profile).plan_hash != baseline

    # Toggle speed
    p3 = plan.model_copy(
        update={
            "layers": [
                plan.layers[0].model_copy(update={"drawing_speed_mm_s": 123.0}),
                plan.layers[1],
            ]
        }
    )
    assert resolve_plan(p3, profile).plan_hash != baseline

    # Toggle pause policy
    p4 = plan.model_copy(
        update={
            "layers": [
                plan.layers[0].model_copy(update={"pause_before": "always"}),
                plan.layers[1],
            ]
        }
    )
    assert resolve_plan(p4, profile).plan_hash != baseline


def test_plan_hash_is_stable_across_metadata_timestamp() -> None:
    """Re-submitting the same plan a second later yields the same hash.

    Otherwise the snapshot table would balloon with one row per
    preflight click on an unchanged plan.
    """
    plan_a = _plan()
    plan_b = _plan()  # built fresh — metadata.created_at differs
    profile = _profile()
    assert (
        resolve_plan(plan_a, profile).plan_hash
        == resolve_plan(plan_b, profile).plan_hash
    )


def test_resolver_applies_profile_default_speed() -> None:
    profile = _profile()
    plan = _plan().model_copy(
        update={
            "layers": [
                LayerPlan(layer_id="red", target_pen_slot=0),
                LayerPlan(layer_id="blue", target_pen_slot=1),
            ]
        }
    )
    resolved = resolve_plan(plan, profile)
    assert all(layer.drawing_speed_mm_s == profile.drawing_speed_mm_s for layer in resolved.layers)


def test_resolver_rejects_zero_speed() -> None:
    plan = _plan().model_copy(
        update={
            "layers": [
                LayerPlan(layer_id="red", drawing_speed_mm_s=0.0),
            ]
        }
    )
    with pytest.raises(PlanResolutionError, match="drawing_speed_mm_s"):
        resolve_plan(plan, _profile())


def test_resolver_rejects_duplicate_layer_ids() -> None:
    plan = _plan().model_copy(
        update={
            "layers": [
                LayerPlan(layer_id="red"),
                LayerPlan(layer_id="red"),
            ]
        }
    )
    with pytest.raises(PlanResolutionError, match="Duplicate layer_id"):
        resolve_plan(plan, _profile())


def test_resolver_marks_missing_pen_slot() -> None:
    plan = _plan().model_copy(
        update={"layers": [LayerPlan(layer_id="red", target_pen_slot=99)]}
    )
    resolved = resolve_plan(plan, _profile())
    assert resolved.layers[0].pen_slot_installed is False

"""Contract tests for the shared ``PrintPlan`` pivot.

These tests guarantee the property the refactor was built around: a
single :class:`PrintPlan` submitted to both ``run_preflight`` and
``run_generate`` resolves to the **same** ``plan_hash``. If this
breaks, the refactor's central promise is broken — preflight and
generate would no longer be operating on identical inputs.
"""

from __future__ import annotations

import pytest

from pen_plotter.application.generate_service import MissingPenSlotsError, run_generate
from pen_plotter.application.plan_resolver import (
    PlanResolutionError,
    resolve_plan,
)
from pen_plotter.application.preflight_service import run_preflight
from pen_plotter.domain.print_plan import LayerPlan, PrintPlan, TypographyPlan
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


def test_resolver_propagates_optimize_and_simplify_defaults() -> None:
    """Defaults (optimize=True, simplify=0.05) survive the resolver."""
    plan = _plan().model_copy(
        update={"layers": [LayerPlan(layer_id="red")]}
    )
    resolved = resolve_plan(plan, _profile())
    assert resolved.layers[0].optimize is True
    assert resolved.layers[0].simplify_tolerance_mm == pytest.approx(0.05)


def test_resolver_propagates_explicit_optimize_and_simplify() -> None:
    """Explicit operator settings are carried over verbatim."""
    plan = _plan().model_copy(
        update={
            "layers": [
                LayerPlan(layer_id="red", optimize=False, simplify_tolerance_mm=0.2),
            ]
        }
    )
    resolved = resolve_plan(plan, _profile())
    assert resolved.layers[0].optimize is False
    assert resolved.layers[0].simplify_tolerance_mm == pytest.approx(0.2)


def test_plan_hash_changes_when_optimize_toggled() -> None:
    """Two plans differing only in ``optimize`` must NOT share a hash."""
    plan = _plan()
    baseline = resolve_plan(plan, _profile()).plan_hash
    flipped = plan.model_copy(
        update={
            "layers": [
                plan.layers[0].model_copy(update={"optimize": False}),
                plan.layers[1],
            ]
        }
    )
    assert resolve_plan(flipped, _profile()).plan_hash != baseline


def test_plan_hash_changes_when_simplify_tolerance_changed() -> None:
    """Same SVG with different simplify tolerance must yield a fresh hash."""
    plan = _plan()
    baseline = resolve_plan(plan, _profile()).plan_hash
    tweaked = plan.model_copy(
        update={
            "layers": [
                plan.layers[0].model_copy(update={"simplify_tolerance_mm": 0.5}),
                plan.layers[1],
            ]
        }
    )
    assert resolve_plan(tweaked, _profile()).plan_hash != baseline


def test_resolver_rejects_negative_simplify_tolerance() -> None:
    plan = _plan().model_copy(
        update={"layers": [LayerPlan(layer_id="red", simplify_tolerance_mm=-0.1)]}
    )
    with pytest.raises(PlanResolutionError, match="simplify_tolerance_mm"):
        resolve_plan(plan, _profile())


def test_generate_refuses_missing_pen_slot_by_default() -> None:
    """The application service must refuse to render G-code asking for
    pens the magazine does not have. Preflight already detected this;
    generate now blocks instead of silently emitting M0 for a phantom
    slot.
    """
    plan = _plan().model_copy(
        update={"layers": [LayerPlan(layer_id="red", target_pen_slot=99)]}
    )
    with pytest.raises(MissingPenSlotsError) as info:
        run_generate(plan, _profile())
    assert info.value.slots == [99]


def test_generate_allows_missing_pen_slot_when_overridden() -> None:
    """The override is the deliberate path for operators who plan to
    swap pens manually at the firmware M0 pause.
    """
    plan = _plan().model_copy(
        update={"layers": [LayerPlan(layer_id="red", target_pen_slot=99)]}
    )
    outcome = run_generate(plan, _profile(), allow_missing_slots=True)
    assert outcome.gcode  # non-empty
    assert outcome.resolved.layers[0].pen_slot_installed is False


def test_generate_aggregates_multiple_missing_slots() -> None:
    """A plan with several missing slots reports them all at once so
    the operator can install them in a single intervention.
    """
    plan = _plan().model_copy(
        update={
            "layers": [
                LayerPlan(layer_id="red", target_pen_slot=99),
                LayerPlan(layer_id="blue", target_pen_slot=42),
            ]
        }
    )
    with pytest.raises(MissingPenSlotsError) as info:
        run_generate(plan, _profile())
    assert info.value.slots == [42, 99]


def _count_pause_prompts(gcode: str) -> int:
    """Count the M0 prompts that the streamer would intercept."""
    # The G-code path emits "M0" on its own line for every pause point
    # (tool change AND mono-pen colour change templates both end with M0).
    return sum(1 for line in gcode.splitlines() if line.strip() == "M0")


def test_preflight_pen_changes_matches_generated_pauses() -> None:
    """End-to-end check that L3 was actually achieved: the count the
    operator sees in preflight is byte-identical to what the streamer
    will encounter at run-time.

    Before extracting ``core/pause_logic``, this was held together by
    two manually-synced predicates 200 LOC apart; any drift would have
    surprised the operator at the wrong moment.
    """
    plan = _plan()
    profile = _profile()
    report = run_preflight(plan, profile).report
    outcome = run_generate(plan, profile)
    assert report.pen_changes == _count_pause_prompts(outcome.gcode)


def test_typography_survives_into_resolved_plan() -> None:
    """``PrintPlan.typography`` rides through the resolver and the
    persisted ``ResolvedPlan.plan`` carries it intact. Today this is
    traceability data; tomorrow the rerender path can act on it.
    """
    plan = _plan().model_copy(
        update={
            "typography": TypographyPlan(
                font="rowmant",
                font_size_mm=20.0,
                bold=True,
                italic=True,
                letter_spacing_mm=1.5,
            )
        }
    )
    resolved = resolve_plan(plan, _profile())
    assert resolved.plan.typography is not None
    assert resolved.plan.typography.font == "rowmant"
    assert resolved.plan.typography.font_size_mm == 20.0
    assert resolved.plan.typography.bold is True


def test_plan_hash_changes_when_font_changes() -> None:
    """Same SVG with different font intent must NOT share a hash —
    otherwise a future in-pipeline rerender would silently return the
    stale snapshot.
    """
    plan = _plan().model_copy(
        update={"typography": TypographyPlan(font="futural", font_size_mm=10.0)}
    )
    baseline = resolve_plan(plan, _profile()).plan_hash
    flipped = plan.model_copy(
        update={"typography": TypographyPlan(font="rowmant", font_size_mm=10.0)}
    )
    assert resolve_plan(flipped, _profile()).plan_hash != baseline


def test_plan_hash_changes_when_font_size_changes() -> None:
    plan = _plan().model_copy(
        update={"typography": TypographyPlan(font="futural", font_size_mm=10.0)}
    )
    baseline = resolve_plan(plan, _profile()).plan_hash
    tweaked = plan.model_copy(
        update={"typography": TypographyPlan(font="futural", font_size_mm=18.0)}
    )
    assert resolve_plan(tweaked, _profile()).plan_hash != baseline


def test_plan_hash_changes_when_bold_italic_flip() -> None:
    plan = _plan().model_copy(update={"typography": TypographyPlan()})
    baseline = resolve_plan(plan, _profile()).plan_hash
    bold = plan.model_copy(update={"typography": TypographyPlan(bold=True)})
    italic = plan.model_copy(update={"typography": TypographyPlan(italic=True)})
    assert resolve_plan(bold, _profile()).plan_hash != baseline
    assert resolve_plan(italic, _profile()).plan_hash != baseline
    assert resolve_plan(bold, _profile()).plan_hash != resolve_plan(italic, _profile()).plan_hash


def test_plan_hash_unchanged_when_typography_absent() -> None:
    """Plans without a typography block (vector / bitmap sources) must
    keep their existing hash — backwards compat for every non-text
    upload already in the snapshot table.
    """
    plan = _plan()  # no typography
    assert plan.typography is None
    other = _plan()
    assert resolve_plan(plan, _profile()).plan_hash == resolve_plan(other, _profile()).plan_hash


def test_plan_hash_changes_when_library_file_id_or_source_mime_changes() -> None:
    """The pivot extensions for in-pipeline text rerender (post-L5)
    must participate in the hash so two plans differing only in which
    library file they re-render from get different snapshots.
    """
    plan = _plan()
    baseline = resolve_plan(plan, _profile()).plan_hash
    with_file = plan.model_copy(
        update={"library_file_id": "abc123", "source_mime": "text/plain"}
    )
    assert resolve_plan(with_file, _profile()).plan_hash != baseline
    flipped_mime = with_file.model_copy(update={"source_mime": "text/markdown"})
    assert (
        resolve_plan(flipped_mime, _profile()).plan_hash
        != resolve_plan(with_file, _profile()).plan_hash
    )

from pen_plotter.core.gcode import LayerGeneration
from pen_plotter.core.preflight import preflight_report
from pen_plotter.profiles import get_profile

NS = (
    'xmlns="http://www.w3.org/2000/svg" '
    'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"'
)
TWO_LAYERS = (
    f'<svg {NS} viewBox="0 0 100 100">'
    '<g inkscape:label="red" stroke="#ff0000"><path d="M10 10 L90 10 L90 90"/></g>'
    '<g inkscape:label="blue" stroke="#0000ff"><path d="M10 50 L90 50"/></g>'
    "</svg>"
)


def _profile():
    profile = get_profile("Custom CoreXY A3")
    assert profile is not None
    return profile


def test_reports_bounds_and_estimates() -> None:
    report = preflight_report(TWO_LAYERS, _profile(), scale_mode="fit", margin_mm=10)
    assert report.within_bounds is True
    assert report.ok is True
    assert report.layer_count == 2
    assert report.path_count == 2
    assert report.width_mm > 0 and report.height_mm > 0
    assert report.drawing_length_mm > 0
    assert report.estimated_seconds > 0


def test_counts_pen_changes() -> None:
    report = preflight_report(
        TWO_LAYERS,
        _profile(),
        layers=[
            LayerGeneration(layer_id="red", target_pen_slot=0),
            LayerGeneration(layer_id="blue", target_pen_slot=1),
        ],
    )
    assert report.pen_changes == 2


def test_flags_missing_pen_slot() -> None:
    # The A3 profile has fewer than 99 slots, so slot 99 is not installed.
    report = preflight_report(
        TWO_LAYERS,
        _profile(),
        layers=[LayerGeneration(layer_id="red", target_pen_slot=99)],
    )
    assert 99 in report.missing_pen_slots
    assert report.ok is False
    assert any("99" in w for w in report.warnings)


def test_actual_scale_is_one_to_one() -> None:
    report = preflight_report(TWO_LAYERS, _profile(), scale_mode="actual")
    assert abs(report.scale - 1.0) < 1e-6


def test_pen_lift_time_added_to_estimate() -> None:
    # Two strokes → 2 lifts + 2 drops = 4 transitions. With 0 ms the
    # estimate matches the motion-only baseline; setting 500 ms must
    # add exactly 4 * 0.5 = 2.0 s.
    base_profile = _profile().model_copy(update={"pen_lift_time_ms": 0.0})
    lifted_profile = _profile().model_copy(update={"pen_lift_time_ms": 500.0})

    base = preflight_report(TWO_LAYERS, base_profile)
    lifted = preflight_report(TWO_LAYERS, lifted_profile)

    assert base.path_count == 2
    assert abs((lifted.estimated_seconds - base.estimated_seconds) - 2.0) < 1e-6


def test_assigned_color_pen_changes_match_gcode_prompts() -> None:
    """L7 assigned colours must pause identically in preflight and G-code.

    Regression: ``preflight_report`` fed ``should_pause`` the raw
    ``target_pen_slot`` / ``source_color`` while ``generate_gcode``
    promoted ``assigned_color_hex`` to an installed pen slot first, so
    the reported ``pen_changes`` count drifted from the number of
    tool-change prompts the generated program actually contains.
    """
    from pen_plotter.core.gcode import generate_gcode
    from pen_plotter.models import PenSlot

    profile = _profile().model_copy(
        update={
            "pens": [
                PenSlot(index=0, name="Red", color="#FF0000"),
                PenSlot(index=1, name="Blue", color="#0000ff"),
            ],
        }
    )
    # No explicit slots — only assigned colours, in mixed case so the
    # promotion's case-insensitive hex match is exercised too.
    layers = [
        LayerGeneration(layer_id="red", assigned_color_hex="#ff0000"),
        LayerGeneration(layer_id="blue", assigned_color_hex="#0000FF"),
    ]

    report = preflight_report(TWO_LAYERS, profile, layers=layers)
    gcode = generate_gcode(TWO_LAYERS, profile, layers=layers)

    prompts = sum(1 for line in gcode.splitlines() if line.startswith("; Change"))
    assert prompts == 2
    assert report.pen_changes == prompts


def test_pen_changes_counts_slot_reink_pauses() -> None:
    """The preflight pen_changes count must include re-ink pauses
    (slot reused with a different assigned colour) so it matches the
    number of prompts the generated program actually contains."""
    from pen_plotter.models import PenSlot

    profile = _profile().model_copy(
        update={
            "pen_slot_count": 2,
            "pens": [
                PenSlot(index=0, name="Black", color="#000000", installed=True),
                PenSlot(index=1, name="Red", color="#ff0000", installed=True),
            ],
        }
    )
    layers = [
        LayerGeneration(layer_id="red", target_pen_slot=0, assigned_color_hex="#000000"),
        # Same slot, different ink → re-ink pause.
        LayerGeneration(layer_id="blue", target_pen_slot=0, assigned_color_hex="#00aaff"),
    ]
    report = preflight_report(TWO_LAYERS, profile, layers=layers)
    # Slot 0 first pose + the re-ink swap.
    assert report.pen_changes == 2

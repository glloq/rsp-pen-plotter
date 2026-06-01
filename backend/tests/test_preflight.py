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

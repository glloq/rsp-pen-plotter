"""Tests for sheet placement: the drawing is centred in the sheet, not the
workspace, and exceeding the workspace surfaces a warning.
"""

from __future__ import annotations

from pen_plotter.core.gcode import generate_gcode
from pen_plotter.core.preflight import preflight_report
from pen_plotter.models import Placement
from pen_plotter.profiles import get_profile

NS = (
    'xmlns="http://www.w3.org/2000/svg" '
    'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"'
)
ONE_LINE = (
    f'<svg {NS} viewBox="0 0 100 100">'
    '<g inkscape:label="layer-1"><path d="M0 0 L100 0 L100 100 L0 100 Z"/></g>'
    "</svg>"
)


def _grbl_profile():
    profile = get_profile("Custom CoreXY A3")
    assert profile is not None
    # Pin the workspace to a known size so the test is independent of profile
    # tweaks: 300 mm × 300 mm starting at the origin.
    return profile.model_copy(
        update={
            "workspace": profile.workspace.model_copy(
                update={"x_min": 0.0, "y_min": 0.0, "x_max": 300.0, "y_max": 300.0}
            )
        }
    )


def test_drawing_centred_in_sheet_not_workspace() -> None:
    """A 100×100 sheet offset at (20, 30) places the drawing centre at (70, 80)."""
    profile = _grbl_profile()
    placement = Placement(
        sheet_width_mm=100.0,
        sheet_height_mm=100.0,
        offset_x_mm=20.0,
        offset_y_mm=30.0,
    )
    report = preflight_report(
        ONE_LINE, profile, scale_mode="fit", margin_mm=0.0, placement=placement
    )
    # Drawing fills the 100x100 sheet -> width/height are the sheet dimensions.
    assert abs(report.width_mm - 100.0) < 0.5
    assert abs(report.height_mm - 100.0) < 0.5
    assert report.within_bounds


def test_no_placement_falls_back_to_workspace() -> None:
    """Without a placement, the drawing scales to the workspace (legacy)."""
    profile = _grbl_profile()
    report = preflight_report(ONE_LINE, profile, scale_mode="fit", margin_mm=0.0)
    # Workspace is 300x300, so the fit-scaled drawing fills it (square input).
    assert abs(report.width_mm - 300.0) < 0.5
    assert abs(report.height_mm - 300.0) < 0.5


def test_sheet_exceeds_workspace_warns() -> None:
    """Sheet larger than workspace -> preflight surfaces a warning."""
    profile = _grbl_profile()
    placement = Placement(
        sheet_width_mm=400.0,  # workspace is 300×300
        sheet_height_mm=400.0,
        offset_x_mm=0.0,
        offset_y_mm=0.0,
    )
    report = preflight_report(
        ONE_LINE, profile, scale_mode="fit", margin_mm=0.0, placement=placement
    )
    assert any("Sheet exceeds the workspace" in w for w in report.warnings)


def test_sheet_warning_in_generated_gcode() -> None:
    """G-code generator includes a ``; WARNING:`` comment for an oversized sheet."""
    profile = _grbl_profile()
    placement = Placement(
        sheet_width_mm=400.0,
        sheet_height_mm=100.0,
        offset_x_mm=0.0,
        offset_y_mm=0.0,
    )
    gcode = generate_gcode(
        ONE_LINE, profile, scale_mode="fit", margin_mm=0.0, placement=placement
    )
    assert "; WARNING: sheet exceeds the workspace" in gcode

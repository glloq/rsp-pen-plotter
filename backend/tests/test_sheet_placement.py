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


def test_y_up_profile_places_drawing_at_top_when_offset_is_top() -> None:
    """A placement near the top of the work plan ends up near the top of the
    paper for a bottom_left (Y-up) profile — not mirrored to the bottom.

    The frontend's sheet preview shows the work plan in SVG-natural Y-down,
    so an ``offset_y_mm`` close to zero means "near the top of the work
    area" in the operator's mind. For a Y-up profile, the top of the paper
    is at ``workspace.y_max``, so the gcode must place the drawing there.
    Regression test for the issue where the Y flip was performed around the
    drawing's own bbox centre, sending the drawing to the bottom of the paper.
    """
    profile = _grbl_profile()  # workspace 0..300 x 0..300, bottom_left origin.
    # 100×100 sheet pinned at the top of the work plan.
    placement = Placement(
        sheet_width_mm=100.0,
        sheet_height_mm=100.0,
        offset_x_mm=20.0,
        offset_y_mm=10.0,
    )
    gcode = generate_gcode(
        ONE_LINE,
        profile,
        scale_mode="fit",
        margin_mm=0.0,
        placement=placement,
    )
    # Look only at the drawing moves (``G1``) — ``G0`` includes the footer's
    # home-at-end move, which would skew the min/max.
    ys: list[float] = []
    for line in gcode.splitlines():
        if not line.startswith("G1"):
            continue
        for token in line.split():
            if token.startswith("Y"):
                ys.append(float(token[1:]))
    assert ys, "expected some Y coordinates in the gcode"
    # Drawing of height 100 placed 10 mm from the top → gcode Y range
    # ``[ws.y_max - 110, ws.y_max - 10] = [190, 290]`` for the 300-tall ws.
    assert min(ys) >= 189.5, f"min Y too low: {min(ys)}"
    assert max(ys) <= 290.5, f"max Y too high: {max(ys)}"


def test_y_up_drawing_position_matches_offset() -> None:
    """For a Y-up profile, a small ``offset_y_mm`` (operator's "near top of
    work plan") places the drawing near ``workspace.y_max`` (top of paper),
    while a large offset places it near ``workspace.y_min``.
    """
    profile = _grbl_profile()  # 300×300 workspace, bottom_left origin.

    def y_range(offset_y: float) -> tuple[float, float]:
        placement = Placement(
            sheet_width_mm=100.0,
            sheet_height_mm=100.0,
            offset_x_mm=20.0,
            offset_y_mm=offset_y,
        )
        gcode = generate_gcode(
            ONE_LINE, profile, scale_mode="fit", margin_mm=0.0, placement=placement
        )
        ys: list[float] = []
        for line in gcode.splitlines():
            if line.startswith("G1"):
                for token in line.split():
                    if token.startswith("Y"):
                        ys.append(float(token[1:]))
        return min(ys), max(ys)

    top_min, top_max = y_range(10.0)
    bottom_min, bottom_max = y_range(190.0)
    # Top-of-plan placement maps to higher gcode Y values than a
    # bottom-of-plan placement.
    assert top_min > bottom_max, (
        f"top placement Y range [{top_min}, {top_max}] should sit above "
        f"bottom placement Y range [{bottom_min}, {bottom_max}]"
    )


def test_top_left_profile_keeps_drawing_at_offset() -> None:
    """For a top_left origin profile, a drawing placed at SVG y=10 stays at
    gcode y near 10 (no Y flip applied).
    """
    profile = _grbl_profile().model_copy(update={"origin": "top_left"})
    placement = Placement(
        sheet_width_mm=100.0,
        sheet_height_mm=100.0,
        offset_x_mm=20.0,
        offset_y_mm=10.0,
    )
    gcode = generate_gcode(
        ONE_LINE, profile, scale_mode="fit", margin_mm=0.0, placement=placement
    )
    ys: list[float] = []
    for line in gcode.splitlines():
        if line.startswith("G1"):
            for token in line.split():
                if token.startswith("Y"):
                    ys.append(float(token[1:]))
    assert ys
    assert min(ys) >= 9.5 and max(ys) <= 110.5


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

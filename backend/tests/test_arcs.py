import math

from pen_plotter.core.arcs import ArcTo, LineTo, fit_arcs
from pen_plotter.core.gcode import generate_gcode
from pen_plotter.profiles import get_profile

NS = (
    'xmlns="http://www.w3.org/2000/svg" '
    'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"'
)


def _circle_points(cx: float, cy: float, r: float, n: int, clockwise: bool) -> list[tuple]:
    pts = []
    for k in range(n + 1):
        t = 2 * math.pi * k / n
        angle = -t if clockwise else t
        pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return pts


def test_straight_line_stays_lines() -> None:
    pts = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0), (30.0, 0.0)]
    segs = fit_arcs(pts, tolerance=0.1)
    assert all(isinstance(s, LineTo) for s in segs)


def test_circle_collapses_to_arcs_with_correct_center() -> None:
    pts = _circle_points(50.0, 50.0, 20.0, 64, clockwise=False)
    segs = fit_arcs(pts, tolerance=0.05)
    arcs = [s for s in segs if isinstance(s, ArcTo)]
    assert arcs, "expected at least one arc"
    # Far fewer segments than the 64 input edges.
    assert len(segs) < 10
    for arc in arcs:
        assert abs(arc.cx - 50.0) < 0.5
        assert abs(arc.cy - 50.0) < 0.5


def test_direction_detected() -> None:
    ccw = [s for s in fit_arcs(_circle_points(0, 0, 10, 48, False), 0.05) if isinstance(s, ArcTo)]
    cw = [s for s in fit_arcs(_circle_points(0, 0, 10, 48, True), 0.05) if isinstance(s, ArcTo)]
    assert ccw and cw
    assert ccw[0].clockwise is False
    assert cw[0].clockwise is True


def test_gcode_emits_arcs_only_when_supported() -> None:
    # A circle drawn as many short segments via an SVG arc path.
    circle_svg = (
        f'<svg {NS} viewBox="0 0 100 100"><g inkscape:label="k" stroke="#000000">'
        '<circle cx="50" cy="50" r="30"/></g></svg>'
    )
    profile = get_profile("Custom CoreXY A3")
    assert profile is not None and profile.supports_arcs

    def arc_lines(gcode: str) -> list[str]:
        return [ln for ln in gcode.splitlines() if ln.startswith(("G2 ", "G3 "))]

    def line_moves(gcode: str) -> list[str]:
        return [ln for ln in gcode.splitlines() if ln.startswith("G1 ")]

    with_arcs = generate_gcode(circle_svg, profile, scale_mode="actual")
    assert arc_lines(with_arcs)

    profile_no_arcs = profile.model_copy(update={"supports_arcs": False})
    without = generate_gcode(circle_svg, profile_no_arcs, scale_mode="actual")
    assert not arc_lines(without)
    assert line_moves(without)

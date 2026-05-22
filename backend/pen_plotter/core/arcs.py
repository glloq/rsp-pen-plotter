"""Circular-arc fitting for G-code generation.

The pivot geometry reaches the generator as polylines (vpype flattens curves).
For controllers that support ``G2``/``G3`` arcs, runs of co-circular points are
collapsed back into arcs, producing smaller, smoother programs. Controllers
without arc support keep plain line segments.

Arc direction follows the standard XY-plane convention: ``G2`` is clockwise,
``G3`` counter-clockwise, as evaluated in the machine coordinate system.
"""

from __future__ import annotations

from dataclasses import dataclass

Point = tuple[float, float]


@dataclass
class LineTo:
    """A straight move to a point."""

    x: float
    y: float


@dataclass
class ArcTo:
    """An arc move to ``(x, y)`` about center ``(cx, cy)``."""

    x: float
    y: float
    cx: float
    cy: float
    clockwise: bool


Segment = LineTo | ArcTo

_MAX_RADIUS = 1e5
_MIN_ARC_POINTS = 5


def _circle_through(a: Point, b: Point, c: Point) -> tuple[float, float, float] | None:
    """Return the ``(cx, cy, radius)`` of the circle through three points, or None."""
    ax, ay = a
    bx, by = b
    cx, cy = c
    d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-9:
        return None
    a2 = ax * ax + ay * ay
    b2 = bx * bx + by * by
    c2 = cx * cx + cy * cy
    ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d
    uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d
    radius = ((ax - ux) ** 2 + (ay - uy) ** 2) ** 0.5
    return ux, uy, radius


def _cross(o: Point, a: Point, b: Point) -> float:
    """Z-component of the cross product of vectors ``o->a`` and ``a->b``."""
    return (a[0] - o[0]) * (b[1] - a[1]) - (a[1] - o[1]) * (b[0] - a[0])


def _fits_arc(points: list[Point], start: int, end: int, tolerance: float) -> bool:
    """Whether ``points[start..end]`` lie on one circle with a consistent turn."""
    circle = _circle_through(points[start], points[(start + end) // 2], points[end])
    if circle is None:
        return False
    cx, cy, radius = circle
    if radius > _MAX_RADIUS:
        return False
    for k in range(start, end + 1):
        px, py = points[k]
        if abs(((px - cx) ** 2 + (py - cy) ** 2) ** 0.5 - radius) > tolerance:
            return False
    sign = 0.0
    for k in range(start, end - 1):
        turn = _cross(points[k], points[k + 1], points[k + 2])
        if abs(turn) < 1e-12:
            continue
        if sign == 0.0:
            sign = turn
        elif (turn > 0) != (sign > 0):
            return False  # inflection: not a single arc
    return True


def _is_clockwise(points: list[Point], start: int, end: int) -> bool:
    """Determine the turn direction of an arc run (True = clockwise)."""
    total = 0.0
    for k in range(start, end - 1):
        total += _cross(points[k], points[k + 1], points[k + 2])
    return total < 0.0


def fit_arcs(points: list[Point], tolerance: float) -> list[Segment]:
    """Convert a polyline into a mix of line and arc segments.

    Args:
        points: The polyline vertices (>= 1), in machine coordinates.
        tolerance: Maximum distance a point may lie from a fitted arc.

    Returns:
        The moves following ``points[0]`` (one per subsequent vertex span).
    """
    n = len(points)
    out: list[Segment] = []
    i = 0
    while i < n - 1:
        end = i + 2
        best = i
        while end < n and _fits_arc(points, i, end, tolerance):
            best = end
            end += 1
        if best - i + 1 >= _MIN_ARC_POINTS:
            circle = _circle_through(points[i], points[(i + best) // 2], points[best])
            assert circle is not None  # _fits_arc succeeded
            cx, cy, _ = circle
            ex, ey = points[best]
            out.append(ArcTo(ex, ey, cx, cy, _is_clockwise(points, i, best)))
            i = best
        else:
            out.append(LineTo(points[i + 1][0], points[i + 1][1]))
            i += 1
    return out

"""Virtual fence crossing and perimeter line geometry helpers."""
from __future__ import annotations

from typing import Sequence


def ccw(a: Sequence[float], b: Sequence[float], c: Sequence[float]) -> bool:
    """Return True if points a, b, c are in counter-clockwise order."""
    return (float(c[1]) - float(a[1])) * (float(b[0]) - float(a[0])) > (float(b[1]) - float(a[1])) * (float(c[0]) - float(a[0]))


def lines_intersect(p1: Sequence[float], p2: Sequence[float], q1: Sequence[float], q2: Sequence[float]) -> bool:
    """Determine whether line segment p1-p2 intersects segment q1-q2."""
    return (ccw(p1, q1, q2) != ccw(p2, q1, q2)) and (ccw(p1, p2, q1) != ccw(p1, p2, q2))

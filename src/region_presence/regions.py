"""Region geometry: bounded rectangles, optionally rotated.

Regions are used by the *simulator* (to produce sensor readings and ground
truth).  The classifier never sees them: it only sees ``get_dist_a()`` /
``get_dist_b()``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

Point = tuple[float, float]

_KEYS = {"center", "width", "height", "rotation_deg"}


class Rectangle:
    """A bounded rectangle given by its center, size and rotation (degrees, counter-clockwise).

    Every query first moves the point into the rectangle's own frame (undo the
    translation and the rotation); there the rectangle is axis-aligned and
    centred at the origin, so the maths stays simple.
    """

    def __init__(self, name: str, center: Point, width: float, height: float,
                 rotation_deg: float = 0.0) -> None:
        if width <= 0 or height <= 0:
            raise ValueError(f"region {name}: width and height must be > 0")
        self.name = name
        self.center = (float(center[0]), float(center[1]))
        self.half_w = width / 2.0
        self.half_h = height / 2.0
        angle = math.radians(rotation_deg)
        self._cos, self._sin = math.cos(angle), math.sin(angle)

    def _to_local(self, p: Point) -> Point:
        dx, dy = p[0] - self.center[0], p[1] - self.center[1]
        return (self._cos * dx + self._sin * dy, -self._sin * dx + self._cos * dy)

    def _to_world(self, p: Point) -> Point:
        x, y = p
        return (self.center[0] + self._cos * x - self._sin * y,
                self.center[1] + self._sin * x + self._cos * y)

    def distance_to_boundary(self, p: Point) -> float:
        """Shortest (unsigned) distance from ``p`` to the rectangle's edges."""
        x, y = self._to_local(p)
        gap_x = abs(x) - self.half_w  # < 0 inside the vertical edges
        gap_y = abs(y) - self.half_h  # < 0 inside the horizontal edges
        if gap_x <= 0 and gap_y <= 0:  # inside: distance to the nearest edge
            return min(-gap_x, -gap_y)
        return math.hypot(max(gap_x, 0.0), max(gap_y, 0.0))  # outside: to the nearest edge/corner

    def contains(self, p: Point) -> bool:
        """True if ``p`` is strictly inside (points on the boundary are outside)."""
        x, y = self._to_local(p)
        return abs(x) < self.half_w and abs(y) < self.half_h

    @property
    def depth(self) -> float:
        """Largest distance-to-boundary reachable inside the rectangle."""
        return min(self.half_w, self.half_h)

    def corners(self) -> list[Point]:
        hw, hh = self.half_w, self.half_h
        return [self._to_world(c) for c in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))]

    def outline(self, n: int = 400) -> list[Point]:
        """About ``n`` points spread along the boundary (corners included)."""
        c = self.corners()
        per_edge = max(1, n // 4)
        return [
            (a[0] + (b[0] - a[0]) * i / per_edge, a[1] + (b[1] - a[1]) * i / per_edge)
            for a, b in zip(c, c[1:] + c[:1], strict=True)
            for i in range(per_edge)
        ]


def build_region(name: str, spec: Mapping[str, Any]) -> Rectangle:
    """Create a rectangle from a config mapping (see README for the keys)."""
    unknown = set(spec) - _KEYS
    if unknown:
        raise ValueError(f"region {name}: unknown keys {sorted(unknown)}; allowed: {sorted(_KEYS)}")
    try:
        return Rectangle(name, tuple(spec["center"]), spec["width"], spec["height"],
                         spec.get("rotation_deg", 0.0))
    except KeyError as exc:
        raise ValueError(f"region {name}: missing key {exc.args[0]!r}") from exc


def assert_disjoint(a: Rectangle, b: Rectangle, tol: float = 1e-6) -> None:
    """Raise if the rectangles share any interior area (partial or full overlap).

    Touching is allowed: a shared wall, part of a wall, or a single corner.

    Exact test (separating axis theorem): two convex shapes are apart when, along
    one of their edge directions, their shadows (projections) do not overlap.
    Rectangles have only two edge directions each, so four directions are checked.
    """
    axes = [(r._cos, r._sin) for r in (a, b)] + [(-r._sin, r._cos) for r in (a, b)]
    for ax, ay in axes:
        shadow_a = [x * ax + y * ay for x, y in a.corners()]
        shadow_b = [x * ax + y * ay for x, y in b.corners()]
        overlap = min(max(shadow_a), max(shadow_b)) - max(min(shadow_a), min(shadow_b))
        if overlap <= tol:
            return  # a gap (or a touching line) along this direction: interiors are apart
    raise ValueError(f"regions {a.name} and {b.name} overlap; they must be disjoint")

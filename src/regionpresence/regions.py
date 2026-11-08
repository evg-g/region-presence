"""Region geometry.

Regions are used by the *simulator* (to produce sensor readings and ground
truth).  The classifier never sees them: it only sees ``get_dist_a()`` /
``get_dist_b()``.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any

Point = tuple[float, float]


def _segment_distance(p: Point, a: Point, b: Point) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0.0:
        return math.hypot(p[0] - ax, p[1] - ay)
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / length_sq))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def _point_in_polygon(p: Point, vertices: Sequence[Point]) -> bool:
    """Even-odd ray casting."""
    x, y = p
    inside = False
    n = len(vertices)
    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _polygon_area(vertices: Sequence[Point]) -> float:
    n = len(vertices)
    s = 0.0
    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def _rotate(p: Point, angle_deg: float, origin: Point) -> Point:
    a = math.radians(angle_deg)
    c, s = math.cos(a), math.sin(a)
    x, y = p[0] - origin[0], p[1] - origin[1]
    return (origin[0] + c * x - s * y, origin[1] + s * x + c * y)


class Region(ABC):
    """A closed 2D region with a boundary."""

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def distance_to_boundary(self, p: Point) -> float:
        """Shortest (unsigned) distance from ``p`` to the region boundary."""

    @abstractmethod
    def contains(self, p: Point) -> bool:
        """True if ``p`` is inside the region."""

    @abstractmethod
    def outline(self, n: int = 360) -> list[Point]:
        """``n`` points spread along the boundary."""

    def bounds(self) -> tuple[float, float, float, float]:
        pts = self.outline()
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)

    def max_inner_distance(self, resolution: int = 80) -> float:
        """Largest distance-to-boundary reachable from inside the region.

        Grid estimate (slight under-estimate); exact for a circle.
        """
        x0, y0, x1, y1 = self.bounds()
        best = 0.0
        for i in range(resolution + 1):
            for j in range(resolution + 1):
                p = (x0 + (x1 - x0) * i / resolution, y0 + (y1 - y0) * j / resolution)
                if self.contains(p):
                    best = max(best, self.distance_to_boundary(p))
        return best


class CircleRegion(Region):
    def __init__(self, name: str, center: Point, radius: float) -> None:
        super().__init__(name)
        if radius <= 0:
            raise ValueError(f"region {name}: radius must be > 0")
        self.center = (float(center[0]), float(center[1]))
        self.radius = float(radius)

    def distance_to_boundary(self, p: Point) -> float:
        return abs(math.hypot(p[0] - self.center[0], p[1] - self.center[1]) - self.radius)

    def contains(self, p: Point) -> bool:
        return math.hypot(p[0] - self.center[0], p[1] - self.center[1]) < self.radius

    def outline(self, n: int = 360) -> list[Point]:
        cx, cy = self.center
        return [
            (cx + self.radius * math.cos(2 * math.pi * k / n),
             cy + self.radius * math.sin(2 * math.pi * k / n))
            for k in range(n)
        ]

    def max_inner_distance(self, resolution: int = 80) -> float:
        return self.radius


class PolygonRegion(Region):
    """Simple (non self-intersecting) polygon; concave shapes are fine."""

    def __init__(self, name: str, vertices: Sequence[Point]) -> None:
        super().__init__(name)
        verts = [(float(x), float(y)) for x, y in vertices]
        if len(verts) < 3:
            raise ValueError(f"region {name}: polygon needs at least 3 vertices")
        if abs(_polygon_area(verts)) == 0.0:
            raise ValueError(f"region {name}: polygon has zero area")
        self.vertices = verts

    def distance_to_boundary(self, p: Point) -> float:
        v = self.vertices
        return min(_segment_distance(p, v[i], v[(i + 1) % len(v)]) for i in range(len(v)))

    def contains(self, p: Point) -> bool:
        return _point_in_polygon(p, self.vertices)

    def outline(self, n: int = 360) -> list[Point]:
        v = self.vertices
        edges = [(v[i], v[(i + 1) % len(v)]) for i in range(len(v))]
        lengths = [math.dist(a, b) for a, b in edges]
        perimeter = sum(lengths)
        points: list[Point] = []
        for (a, b), length in zip(edges, lengths, strict=True):
            k = max(1, round(n * length / perimeter))
            for i in range(k):
                t = i / k
                points.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
        return points


def rectangle(name: str, center: Point, width: float, height: float,
              rotation_deg: float = 0.0) -> PolygonRegion:
    if width <= 0 or height <= 0:
        raise ValueError(f"region {name}: width and height must be > 0")
    cx, cy = center
    hw, hh = width / 2, height / 2
    corners = [(cx - hw, cy - hh), (cx + hw, cy - hh), (cx + hw, cy + hh), (cx - hw, cy + hh)]
    return PolygonRegion(name, [_rotate(c, rotation_deg, (cx, cy)) for c in corners])


def ellipse(name: str, center: Point, rx: float, ry: float, rotation_deg: float = 0.0,
            segments: int = 128) -> PolygonRegion:
    """Ellipse approximated by a polygon with ``segments`` vertices."""
    if rx <= 0 or ry <= 0:
        raise ValueError(f"region {name}: rx and ry must be > 0")
    cx, cy = center
    pts = [(cx + rx * math.cos(2 * math.pi * k / segments),
            cy + ry * math.sin(2 * math.pi * k / segments)) for k in range(segments)]
    return PolygonRegion(name, [_rotate(p, rotation_deg, (cx, cy)) for p in pts])


_SHAPE_KEYS: dict[str, set[str]] = {
    "circle": {"shape", "center", "radius"},
    "rectangle": {"shape", "center", "width", "height", "rotation_deg"},
    "ellipse": {"shape", "center", "rx", "ry", "rotation_deg", "segments"},
    "polygon": {"shape", "vertices"},
}


def build_region(name: str, spec: Mapping[str, Any]) -> Region:
    """Create a region from a config mapping (see README for the schema)."""
    shape = spec.get("shape")
    if shape not in _SHAPE_KEYS:
        raise ValueError(f"region {name}: unknown shape {shape!r}; choose from {sorted(_SHAPE_KEYS)}")
    unknown = set(spec) - _SHAPE_KEYS[shape]
    if unknown:
        raise ValueError(f"region {name}: unknown keys for {shape}: {sorted(unknown)}")
    try:
        if shape == "circle":
            return CircleRegion(name, tuple(spec["center"]), spec["radius"])
        if shape == "rectangle":
            return rectangle(name, tuple(spec["center"]), spec["width"], spec["height"],
                             spec.get("rotation_deg", 0.0))
        if shape == "ellipse":
            return ellipse(name, tuple(spec["center"]), spec["rx"], spec["ry"],
                           spec.get("rotation_deg", 0.0), spec.get("segments", 128))
        return PolygonRegion(name, [tuple(v) for v in spec["vertices"]])
    except KeyError as exc:
        raise ValueError(f"region {name}: missing key {exc.args[0]!r} for shape {shape}") from exc


def assert_disjoint(a: Region, b: Region) -> None:
    """Raise if the two regions overlap (checked on dense boundary samples)."""
    for first, second in ((a, b), (b, a)):
        if any(second.contains(p) for p in first.outline(720)):
            raise ValueError(f"regions {a.name} and {b.name} overlap; they must be disjoint")

"""Sensor motion: a parametric path plus a non-constant speed process."""

from __future__ import annotations

import bisect
import math
import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields
from typing import Any

from .regions import Point


class Path:
    """Arc-length parametrised 2D curve built from ``func(u) -> (x, y)``."""

    def __init__(self, func: Callable[[float], Point], u_max: float, closed: bool,
                 resolution: int = 5000) -> None:
        self.closed = closed
        us = [u_max * i / resolution for i in range(resolution + 1)]
        self._pts = [func(u) for u in us]
        self._cum = [0.0]
        for a, b in zip(self._pts, self._pts[1:], strict=False):
            self._cum.append(self._cum[-1] + math.dist(a, b))
        self.length = self._cum[-1]
        if self.length <= 0:
            raise ValueError("path has zero length")

    def position_at(self, s: float) -> Point:
        """Position after travelling arc length ``s`` (wraps if closed)."""
        s = s % self.length if self.closed else max(0.0, min(s, self.length))
        i = min(bisect.bisect_right(self._cum, s) - 1, len(self._pts) - 2)
        seg = self._cum[i + 1] - self._cum[i]
        t = 0.0 if seg == 0 else (s - self._cum[i]) / seg
        (x0, y0), (x1, y1) = self._pts[i], self._pts[i + 1]
        return (x0 + t * (x1 - x0), y0 + t * (y1 - y0))

    def finished(self, s: float) -> bool:
        return (not self.closed) and s >= self.length

    def polyline(self, n: int = 600) -> list[Point]:
        return [self.position_at(self.length * i / n) for i in range(n + 1)]


def waypoint_path(points: Sequence[Point], closed: bool = True) -> Path:
    """Catmull-Rom spline through ``points``."""
    pts = [(float(x), float(y)) for x, y in points]
    n = len(pts)
    if n < 2 or (closed and n < 3):
        raise ValueError("waypoint path needs >= 2 points (>= 3 if closed)")

    def at(i: int) -> Point:
        return pts[i % n] if closed else pts[max(0, min(n - 1, i))]

    def func(u: float) -> Point:
        i = min(int(math.floor(u)), (n if closed else n - 1) - 1)
        t = u - i
        p0, p1, p2, p3 = at(i - 1), at(i), at(i + 1), at(i + 2)
        t2, t3 = t * t, t * t * t
        return tuple(  # type: ignore[return-value]
            0.5 * ((2 * p1[k]) + (-p0[k] + p2[k]) * t
                   + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2
                   + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3)
            for k in (0, 1)
        )

    return Path(func, float(n if closed else n - 1), closed)


def build_path(spec: Mapping[str, Any]) -> Path:
    """Create the path from the ``[path]`` config section: ``points`` and ``closed``."""
    unknown = set(spec) - {"points", "closed"}
    if unknown:
        raise ValueError(f"[path]: unknown keys {sorted(unknown)}; allowed: ['closed', 'points']")
    if "points" not in spec:
        raise ValueError("[path]: missing key 'points'")
    closed = spec.get("closed", True)
    if not isinstance(closed, bool):  # bool("false") would be True
        raise ValueError(f"[path] closed = {closed!r}: expected true or false")
    return waypoint_path([tuple(p) for p in spec["points"]], closed)


@dataclass(frozen=True)
class MotionConfig:
    """Speed statistics (distance units per second)."""

    mean_speed: float = 1.4
    speed_std: float = 0.5
    correlation_time: float = 5.0
    min_speed: float = 0.0
    max_speed: float = 3.0

    def __post_init__(self) -> None:
        values = {f.name: getattr(self, f.name) for f in fields(self)}
        bad = [f"{name} = {v}" for name, v in values.items() if not math.isfinite(v)]
        if bad:
            raise ValueError(f"must be finite numbers: {', '.join(bad)}")
        if not (0 <= self.min_speed <= self.mean_speed <= self.max_speed):
            raise ValueError(
                "need 0 <= min_speed <= mean_speed <= max_speed, got "
                f"min_speed = {self.min_speed}, mean_speed = {self.mean_speed}, "
                f"max_speed = {self.max_speed}"
            )
        if self.max_speed <= 0:
            raise ValueError("max_speed must be > 0")
        if self.speed_std < 0:
            raise ValueError(f"speed_std = {self.speed_std}: must be >= 0")
        if self.correlation_time <= 0:
            raise ValueError(f"correlation_time = {self.correlation_time}: must be > 0")


class SpeedProcess:
    """Ornstein-Uhlenbeck speed: mean-reverting, correlated in time, clipped to limits.

    Gives a realistic "average speed with fluctuations" (accelerations, slow-downs,
    brief stops when the lower clip is hit).
    """

    def __init__(self, cfg: MotionConfig, dt: float, rng: random.Random) -> None:
        self._cfg = cfg
        self._rng = rng
        self._decay = math.exp(-dt / cfg.correlation_time)
        self._noise = cfg.speed_std * math.sqrt(1.0 - self._decay**2)
        self.speed = cfg.mean_speed

    def step(self) -> float:
        c = self._cfg
        v = c.mean_speed + self._decay * (self.speed - c.mean_speed) + self._noise * self._rng.gauss(0, 1)
        self.speed = max(c.min_speed, min(c.max_speed, v))
        return self.speed

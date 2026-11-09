"""Simulated GPS sensor exposing ``get_dist_a()`` / ``get_dist_b()``."""

from __future__ import annotations

import random

from .classifier import Presence
from .regions import Point, Rectangle
from .trajectory import Path, SpeedProcess


class SimulatedSensor:
    """Moves along ``path`` at a fluctuating speed; readings are noisy distances.

    ``step()`` advances time by ``dt``; ``get_dist_a()`` / ``get_dist_b()`` then
    return the (idempotent) readings for the current sample, with no arguments -
    exactly like a real sensor driver.  ``position`` and ``truth`` exist only for
    visualisation and evaluation; the classifier never uses them.
    """

    def __init__(self, region_a: Rectangle, region_b: Rectangle, path: Path, speed: SpeedProcess,
                 dt: float, noise_std: float, rng: random.Random) -> None:
        self._a, self._b = region_a, region_b
        self._path, self._speed = path, speed
        self.dt, self._noise_std, self._rng = dt, noise_std, rng
        self._s = 0.0
        self.time = 0.0
        self.speed = speed.speed
        self._sample()

    def step(self) -> bool:
        """Advance one sample. Returns False when an open path has ended."""
        self.speed = self._speed.step()
        self._s += self.speed * self.dt
        self.time += self.dt
        self._sample()
        return not self._path.finished(self._s)

    def _sample(self) -> None:
        self.position: Point = self._path.position_at(self._s)
        self._reading_a = self._noisy(self._a.distance_to_boundary(self.position))
        self._reading_b = self._noisy(self._b.distance_to_boundary(self.position))

    def _noisy(self, d: float) -> float:
        return max(0.0, d + self._rng.gauss(0.0, self._noise_std))

    def get_dist_a(self) -> float:
        return self._reading_a

    def get_dist_b(self) -> float:
        return self._reading_b

    @property
    def truth(self) -> Presence:
        if self._a.contains(self.position):
            return Presence.IN_A
        if self._b.contains(self.position):
            return Presence.IN_B
        return Presence.OUTSIDE

"""Run-time (causal) region-presence classifier.

The only inputs are two zero-argument callables, ``get_dist_a`` and
``get_dist_b``, returning the shortest *unsigned* distance to the boundary of
region A / B.  An unsigned distance cannot tell inside from outside from a
single sample, so the classifier tracks boundary crossings over time.

Crossing test
-------------
Between two consecutive samples the sensor moves at most ``L_step = v_max * dt``.
If it crossed the boundary of region R in that interval, it travelled at least
``d_prev`` (to reach the boundary) plus ``d_cur`` (to get away from it), so
``d_prev + d_cur <= L_step``.  Adding a margin for sensor noise gives the
threshold ``L``.  When the test fires, the state toggles (Outside <-> In R)
immediately - no look-ahead, no post-processing.

The pair test only marks a crossing as *possible*; it is declared as soon as the
distance turns upward (sensor moving away from the boundary) or when it leaves the
``L`` zone, which avoids firing ahead of the actual crossing.  A per-region latch
prevents one crossing from firing repeatedly: it is re-armed only once the
distance exceeds ``L`` again.

Adjacent regions (A and B sharing a boundary) are supported: both distances reach
zero together and the state moves A <-> B directly.

Self-healing: a distance larger than the deepest point of a region (plus ``L``)
proves the sensor is not inside it, which corrects a missed/spurious crossing.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple

log = logging.getLogger(__name__)


class Presence(str, Enum):
    OUTSIDE = "Outside"
    IN_A = "In A"
    IN_B = "In B"


@dataclass(frozen=True)
class ClassifierConfig:
    crossing_threshold: float
    """``L``: a boundary crossing is declared when ``d_prev + d_cur <= L``."""
    initial_state: Presence = Presence.OUTSIDE
    """Distances are unsigned, so the starting side must be known a priori."""
    max_depth_a: float | None = None
    """Optional: max distance-to-boundary attainable inside A (enables self-healing)."""
    max_depth_b: float | None = None

    def __post_init__(self) -> None:
        if self.crossing_threshold <= 0:
            raise ValueError("crossing_threshold must be > 0")

    @classmethod
    def from_motion(cls, max_speed: float, dt: float, noise_std: float,
                    sigma_multiplier: float = 3.0, **kwargs: object) -> ClassifierConfig:
        """Derive ``L = v_max*dt + 2*k*sigma`` from motion and sensor-noise limits."""
        threshold = max_speed * dt + 2.0 * sigma_multiplier * noise_std
        return cls(crossing_threshold=threshold, **kwargs)  # type: ignore[arg-type]


class Classification(NamedTuple):
    state: Presence
    changed: bool
    dist_a: float
    dist_b: float


class PresenceClassifier:
    """Call :meth:`update` once per sensor sample."""

    def __init__(self, get_dist_a: Callable[[], float], get_dist_b: Callable[[], float],
                 config: ClassifierConfig) -> None:
        self._get = {"A": get_dist_a, "B": get_dist_b}
        self._cfg = config
        self._state = config.initial_state
        self._prev: dict[str, float] = {}
        self._armed: dict[str, bool] = {}
        self._pending: dict[str, bool] = {}
        self._depth = {"A": config.max_depth_a, "B": config.max_depth_b}
        self._target = {"A": Presence.IN_A, "B": Presence.IN_B}

    @property
    def state(self) -> Presence:
        return self._state

    def update(self) -> Classification:
        limit = self._cfg.crossing_threshold
        dist = {key: float(get()) for key, get in self._get.items()}
        before = self._state
        self._self_heal(dist)

        crossings: list[str] = []
        for key in sorted(dist, key=dist.__getitem__):  # nearest boundary first
            if self._detect_crossing(key, dist[key], limit):
                crossings.append(key)
            self._prev[key] = dist[key]

        remaining = list(crossings)
        while remaining:
            consumed = self._apply_crossing(remaining.pop(0), dist)
            if consumed in remaining:
                remaining.remove(consumed)
        return Classification(self._state, self._state != before, dist["A"], dist["B"])

    def _detect_crossing(self, key: str, cur: float, limit: float) -> bool:
        """Pair test ``d_prev + d_cur <= L`` marks a crossing as *possible*; it is
        declared as soon as the distance turns upward (the sensor is moving away
        from the boundary) or, failing that, when it leaves the ``L`` zone."""
        prev = self._prev.get(key)
        if prev is None:  # first sample: starting next to a boundary must not fire
            self._armed[key] = cur > limit
            self._pending[key] = False
            return False
        if cur > limit:
            fire = self._pending[key]
            self._armed[key] = True
            self._pending[key] = False
            return fire
        if self._armed[key]:
            if prev + cur <= limit:
                self._pending[key] = True
            if self._pending[key] and cur > prev:
                self._armed[key] = self._pending[key] = False
                return True
        return False

    def _apply_crossing(self, key: str, dist: dict[str, float]) -> str | None:
        """Toggle state for a crossing of ``key``'s boundary.

        Adjacent regions share a boundary, so crossing it is one event seen by both
        distances: it moves A <-> B directly instead of passing through Outside.
        Returns the other region's key if its (simultaneous) crossing was consumed.
        """
        other = "B" if key == "A" else "A"
        target, other_target = self._target[key], self._target[other]
        near_other = dist[other] <= self._cfg.crossing_threshold
        if self._state == target:
            if near_other:
                self._state = other_target
                return self._disarm(other)
            self._state = Presence.OUTSIDE
        elif self._state == other_target and near_other:
            self._state = target
            return self._disarm(other)
        else:
            if self._state != Presence.OUTSIDE:
                log.warning("crossed boundary %s while in state %s; assuming a missed exit",
                            key, self._state.value)
            self._state = target
        return None

    def _disarm(self, key: str) -> str:
        self._armed[key] = self._pending[key] = False
        return key

    def _self_heal(self, dist: dict[str, float]) -> None:
        for key, depth in self._depth.items():
            if depth is not None and self._state == self._target[key] \
                    and dist[key] > depth + self._cfg.crossing_threshold:
                log.warning("distance %.2f exceeds depth of %s; correcting to Outside",
                            dist[key], key)
                self._state = Presence.OUTSIDE

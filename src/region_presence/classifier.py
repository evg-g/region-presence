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
``L`` zone.  At walking speed this indicates the crossing about one sample late; a
slow sensor can be indicated up to about ``L / 2`` before it reaches the edge.  A per-region latch
prevents one crossing from firing repeatedly: it is re-armed only once the
distance exceeds ``L`` again.

Adjacent regions (A and B sharing a boundary) are supported: both distances reach
zero together and the state moves A <-> B directly.

Depth check (optional)
----------------------
A rectangle has a largest possible distance to its own edge, reached at its
centre: half of its shorter side.  If the state says "In A" but ``get_dist_a()``
is clearly larger than that (by more than the noise margin), the sensor cannot
be inside A, so the state is wrong.  The classifier then goes back to Outside and
logs a warning.  This is the only way a wrong state can heal itself, because
distances carry no sign.  It needs the region depths (``max_depth_a`` and
``max_depth_b`` in :class:`ClassifierConfig`) and is skipped when they are not given.
"""

from __future__ import annotations

import logging
import math
import numbers
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import NamedTuple

log = logging.getLogger(__name__)


class InvalidReadingError(ValueError):
    """A distance function returned a value that is not a valid distance."""


class Presence(StrEnum):
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
    max_depth_b: float | None = None
    """Largest distance to the edge from inside A / B (half of the shorter side).
    Optional; when given, a state that contradicts it is corrected (see the module docstring)."""

    def __post_init__(self) -> None:
        # written as "not (x > 0)" so that NaN, for which every comparison is False, fails too
        if not (math.isfinite(self.crossing_threshold) and self.crossing_threshold > 0):
            raise ValueError(f"crossing_threshold = {self.crossing_threshold}: must be a finite number > 0")
        for name, depth in (("max_depth_a", self.max_depth_a), ("max_depth_b", self.max_depth_b)):
            if depth is None:
                continue
            if not (math.isfinite(depth) and depth > 0):
                raise ValueError(f"{name} = {depth}: must be a finite number > 0")
            if depth <= self.crossing_threshold:
                # Inside, the distance never gets above L, so the classifier could never
                # tell that the sensor has left again: the region is too small for this L.
                raise ValueError(
                    f"{name} = {depth} is not larger than the crossing threshold "
                    f"L = {self.crossing_threshold:.3g}. A region this small cannot be tracked: "
                    "make it larger, or lower max_speed, dt or the noise."
                )

    @classmethod
    def from_motion(cls, max_speed: float, dt: float, noise_std: float,
                    sigma_multiplier: float = 3.0,
                    initial_state: Presence = Presence.OUTSIDE,
                    max_depth_a: float | None = None,
                    max_depth_b: float | None = None) -> ClassifierConfig:
        """Derive ``L = v_max*dt + 2*k*sigma`` from motion and sensor-noise limits."""
        for name, value in (("max_speed", max_speed), ("dt", dt), ("sigma_multiplier", sigma_multiplier)):
            if not (math.isfinite(value) and value > 0):
                raise ValueError(f"{name} = {value}: must be a finite number > 0")
        if not (math.isfinite(noise_std) and noise_std >= 0):
            raise ValueError(f"noise_std = {noise_std}: must be a finite number >= 0")
        threshold = max_speed * dt + 2.0 * sigma_multiplier * noise_std
        return cls(crossing_threshold=threshold, initial_state=initial_state,
                   max_depth_a=max_depth_a, max_depth_b=max_depth_b)


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
        self._target = {"A": Presence.IN_A, "B": Presence.IN_B}
        self._max_depth = {"A": config.max_depth_a, "B": config.max_depth_b}

    @property
    def state(self) -> Presence:
        return self._state

    @property
    def crossing_threshold(self) -> float:
        """The threshold ``L`` currently in use."""
        return self._cfg.crossing_threshold

    def update(self) -> Classification:
        limit = self._cfg.crossing_threshold
        dist = {key: self._read(key) for key in self._get}  # validate both before changing anything
        before = self._state
        self._check_depth(dist, limit)

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

    def _check_depth(self, dist: dict[str, float], limit: float) -> None:
        """Go back to Outside if the state says "inside R" but the distance is too large for that."""
        for key, target in self._target.items():
            depth = self._max_depth[key]
            if depth is not None and self._state == target and dist[key] > depth + limit:
                log.warning("state was %s but get_dist_%s() = %.2f is larger than the region's "
                            "depth (%.2f) plus the threshold; resetting to Outside",
                            target.value, key.lower(), dist[key], depth)
                self._state = Presence.OUTSIDE

    def _read(self, key: str) -> float:
        """Call ``get_dist_<key>()`` and check that the result is a real, non-negative number."""
        name = f"get_dist_{key.lower()}()"
        value = self._get[key]()
        # bool is a subclass of int, and float("3.5") would quietly accept text: reject both
        if isinstance(value, bool) or not isinstance(value, numbers.Real):
            raise InvalidReadingError(f"{name} returned {value!r}; expected a number")
        distance = float(value)
        if not math.isfinite(distance) or distance < 0:
            raise InvalidReadingError(
                f"{name} returned {distance}; a distance must be a finite number >= 0"
            )
        return distance

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

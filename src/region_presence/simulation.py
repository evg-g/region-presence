"""Wires config -> world -> sensor -> classifier and streams frames."""

from __future__ import annotations

import random
from collections.abc import Iterator
from dataclasses import dataclass

from .classifier import ClassifierConfig, Presence, PresenceClassifier
from .config import SimConfig
from .regions import Point, Region, assert_disjoint, build_region
from .sensor import SimulatedSensor
from .trajectory import Path, SpeedProcess, build_path


@dataclass(frozen=True)
class Frame:
    t: float
    position: Point        # ground truth, for display only
    speed: float
    dist_a: float
    dist_b: float
    predicted: Presence    # classifier output for this sample
    truth: Presence        # ground truth, for evaluation only
    changed: bool          # predicted state changed at this sample


@dataclass
class Metrics:
    frames: int = 0
    correct: int = 0
    transitions: int = 0
    _delays: list[float] | None = None
    _pending: float | None = None
    _last_truth: Presence | None = None

    def add(self, f: Frame) -> None:
        if self._delays is None:
            self._delays = []
        self.frames += 1
        self.correct += f.predicted == f.truth
        self.transitions += f.changed
        if self._last_truth is not None and f.truth != self._last_truth:
            self._pending = f.t
        if self._pending is not None and f.predicted == f.truth:
            self._delays.append(f.t - self._pending)
            self._pending = None
        self._last_truth = f.truth

    @property
    def accuracy(self) -> float:
        return self.correct / self.frames if self.frames else 0.0

    @property
    def mean_delay_s(self) -> float:
        """Mean time from a true region change until the indication agrees (0 if early)."""
        d = self._delays or []
        return sum(d) / len(d) if d else 0.0


class Simulation:
    def __init__(self, cfg: SimConfig) -> None:
        self.cfg = cfg
        self.region_a: Region = build_region("A", cfg.regions["A"])
        self.region_b: Region = build_region("B", cfg.regions["B"])
        assert_disjoint(self.region_a, self.region_b)
        self.path: Path = build_path(cfg.path)

        rng = random.Random(cfg.seed)
        self.sensor = SimulatedSensor(
            self.region_a, self.region_b, self.path,
            SpeedProcess(cfg.motion, cfg.dt, rng), cfg.dt, cfg.noise_std, rng,
        )
        # A priori region knowledge used only for the optional self-healing bound.
        margin = 1.02
        self.classifier = PresenceClassifier(
            self.sensor.get_dist_a, self.sensor.get_dist_b,
            ClassifierConfig.from_motion(
                cfg.motion.max_speed, cfg.dt, cfg.noise_std, cfg.sigma_multiplier,
                initial_state=self.sensor.truth,
                max_depth_a=self.region_a.max_inner_distance() * margin,
                max_depth_b=self.region_b.max_inner_distance() * margin,
            ),
        )
        self.metrics = Metrics()

    def frames(self) -> Iterator[Frame]:
        """Yield one frame per sample; the classifier is fed strictly in time order."""
        steps = int(round(self.cfg.duration_s / self.cfg.dt))
        for _ in range(steps):
            result = self.classifier.update()
            frame = Frame(
                t=self.sensor.time, position=self.sensor.position, speed=self.sensor.speed,
                dist_a=result.dist_a, dist_b=result.dist_b, predicted=result.state,
                truth=self.sensor.truth, changed=result.changed,
            )
            self.metrics.add(frame)
            yield frame
            if not self.sensor.step():
                return

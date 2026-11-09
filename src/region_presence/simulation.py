"""Wires config -> world -> sensor -> classifier and streams frames."""

from __future__ import annotations

import random
from collections.abc import Iterator
from dataclasses import dataclass

from .classifier import ClassifierConfig, Presence, PresenceClassifier
from .config import INITIAL_STATES, SimConfig
from .regions import Point, Rectangle, assert_disjoint, build_region
from .sensor import SimulatedSensor
from .trajectory import Path, SpeedProcess, build_path


@dataclass(frozen=True)
class Frame:
    """Everything known about one sample; only ``predicted`` comes from the classifier."""

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
    """Running comparison of the indication with ground truth (evaluation only)."""

    frames: int = 0
    correct: int = 0
    transitions: int = 0

    def add(self, f: Frame) -> None:
        self.frames += 1
        self.correct += f.predicted == f.truth
        self.transitions += f.changed

    @property
    def accuracy(self) -> float:
        return self.correct / self.frames if self.frames else 0.0


class Simulation:
    def __init__(self, cfg: SimConfig) -> None:
        self.cfg = cfg
        self.region_a: Rectangle = build_region("A", cfg.regions["A"])
        self.region_b: Rectangle = build_region("B", cfg.regions["B"])
        assert_disjoint(self.region_a, self.region_b)
        self.path: Path = build_path(cfg.path)

        rng = random.Random(cfg.seed)
        self.sensor = SimulatedSensor(
            self.region_a, self.region_b, self.path,
            SpeedProcess(cfg.motion, cfg.dt, rng), cfg.dt, cfg.noise_std, rng,
        )
        initial = INITIAL_STATES[cfg.initial_state]
        if self.sensor.truth != initial:  # scenario sanity check; not given to the classifier
            raise ValueError(
                f"initial_state is '{cfg.initial_state}' but the path starts '{self.sensor.truth.value}'"
            )
        self.classifier = PresenceClassifier(
            self.sensor.get_dist_a, self.sensor.get_dist_b,
            ClassifierConfig.from_motion(
                cfg.motion.max_speed, cfg.dt, cfg.noise_std, cfg.sigma_multiplier,
                initial_state=initial,
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

"""TOML configuration loading and validation."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from pathlib import Path as FsPath
from typing import Any

from .trajectory import MotionConfig

DEFAULT_CONFIG = FsPath(__file__).with_name("default_config.toml")


class ConfigError(ValueError):
    """Invalid configuration."""


@dataclass(frozen=True)
class SimConfig:
    duration_s: float = 300.0
    dt: float = 0.1
    seed: int | None = 7
    noise_std: float = 0.05
    sigma_multiplier: float = 3.0
    motion: MotionConfig = field(default_factory=MotionConfig)
    path: Mapping[str, Any] = field(default_factory=dict)
    regions: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.duration_s <= 0 or self.dt <= 0:
            raise ConfigError("duration_s and dt must be > 0")
        if self.noise_std < 0 or self.sigma_multiplier <= 0:
            raise ConfigError("noise_std must be >= 0 and sigma_multiplier > 0")
        if set(self.regions) != {"A", "B"}:
            raise ConfigError("config must define exactly the regions [regions.A] and [regions.B]")
        if not self.path:
            raise ConfigError("config must define a [path] section")


def _check_keys(section: str, data: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = set(data) - allowed
    if unknown:
        raise ConfigError(f"unknown key(s) in [{section}]: {sorted(unknown)}")


def from_dict(data: Mapping[str, Any]) -> SimConfig:
    _check_keys("<root>", data, {"simulation", "sensor", "motion", "path", "regions"})
    sim = data.get("simulation", {})
    sensor = data.get("sensor", {})
    _check_keys("simulation", sim, {"duration_s", "dt", "seed"})
    _check_keys("sensor", sensor, {"noise_std", "sigma_multiplier"})
    motion_keys = {f.name for f in fields(MotionConfig)}
    _check_keys("motion", data.get("motion", {}), motion_keys)
    try:
        return SimConfig(
            **{k: v for k, v in sim.items()},
            **{k: v for k, v in sensor.items()},
            motion=MotionConfig(**data.get("motion", {})),
            path=data.get("path", {}),
            regions=data.get("regions", {}),
        )
    except (TypeError, ValueError) as exc:
        raise ConfigError(str(exc)) from exc


def load_config(path: str | FsPath | None = None) -> SimConfig:
    """Load a TOML file (the bundled default scenario when ``path`` is None)."""
    target = FsPath(path) if path else DEFAULT_CONFIG
    try:
        with target.open("rb") as fh:
            return from_dict(tomllib.load(fh))
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {target}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {target}: {exc}") from exc

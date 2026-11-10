"""TOML configuration loading and validation.

Every check on what the user wrote happens here, before anything is built, so a
mistake in a config file is reported as one ``ConfigError`` that names the
section, the key and the value (and the file, when loaded from one).
"""

from __future__ import annotations

import math
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from pathlib import Path as FsPath
from typing import Any

from .classifier import Presence
from .trajectory import MotionConfig

DEFAULT_CONFIG = FsPath(__file__).with_name("default_config.toml")


class ConfigError(ValueError):
    """Invalid configuration."""


INITIAL_STATES = {"outside": Presence.OUTSIDE, "in_a": Presence.IN_A, "in_b": Presence.IN_B}

_SECTIONS = {"simulation", "sensor", "motion", "path", "regions"}
_SIMULATION_KEYS = {"duration_s", "dt", "seed", "initial_state"}
_SENSOR_KEYS = {"noise_std", "sigma_multiplier"}
_MOTION_KEYS = {f.name for f in fields(MotionConfig)}
_PATH_KEYS = {"points", "closed"}
_REGION_KEYS = {"center", "width", "height", "rotation_deg"}


@dataclass(frozen=True)
class SimConfig:
    duration_s: float = 300.0
    dt: float = 0.1
    seed: int | None = 7
    initial_state: str = "outside"
    """Where the sensor starts: ``outside``, ``in_a`` or ``in_b`` (the classifier is told this)."""
    noise_std: float = 0.05
    sigma_multiplier: float = 3.0
    motion: MotionConfig = field(default_factory=MotionConfig)
    path: Mapping[str, Any] = field(default_factory=dict)
    regions: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_positive("[simulation] duration_s", self.duration_s)
        _require_positive("[simulation] dt", self.dt)
        if self.duration_s < self.dt:
            raise ConfigError(
                f"[simulation] duration_s = {self.duration_s} is shorter than one sample (dt = {self.dt})"
            )
        if self.initial_state not in INITIAL_STATES:
            raise ConfigError(f"[simulation] initial_state = {self.initial_state!r}: "
                              f"must be one of {sorted(INITIAL_STATES)}")
        if not (math.isfinite(self.noise_std) and self.noise_std >= 0):
            raise ConfigError(f"[sensor] noise_std = {self.noise_std}: must be a finite number >= 0")
        _require_positive("[sensor] sigma_multiplier", self.sigma_multiplier)
        if set(self.regions) != {"A", "B"}:
            raise ConfigError("config must define exactly the regions [regions.A] and [regions.B]")
        if not self.path:
            raise ConfigError("config must define a [path] section")


def _require_positive(name: str, value: float) -> None:
    if not (math.isfinite(value) and value > 0):
        raise ConfigError(f"{name} = {value}: must be a finite number > 0")


def _check_keys(section: str, data: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = set(data) - allowed
    if unknown:
        raise ConfigError(f"unknown key(s) in [{section}]: {sorted(unknown)}; allowed: {sorted(allowed)}")


def _table(section: str, value: object, allowed: set[str]) -> Mapping[str, Any]:
    """A config section: must be a TOML table with known keys only."""
    if not isinstance(value, Mapping):
        raise ConfigError(f"[{section}] must be a table, got {value!r}")
    _check_keys(section, value, allowed)
    return value


def _number(section: str, key: str, value: object) -> float:
    """A finite real number. ``true``/``false`` and quoted numbers like ``"20"`` are rejected."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError(f"[{section}] {key} = {value!r}: expected a number")
    if not math.isfinite(value):
        raise ConfigError(f"[{section}] {key} = {value!r}: must be a finite number")
    return float(value)


def _point(section: str, key: str, value: object) -> tuple[float, float]:
    """An ``[x, y]`` pair of numbers."""
    if not isinstance(value, list) or len(value) != 2:
        raise ConfigError(f"[{section}] {key} = {value!r}: expected [x, y]")
    return (_number(section, key, value[0]), _number(section, key, value[1]))


def _numbers(section: str, data: Mapping[str, Any]) -> dict[str, float]:
    return {key: _number(section, key, value) for key, value in data.items()}


def _parse_simulation(data: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = _numbers("simulation", {k: v for k, v in data.items()
                                                  if k in ("duration_s", "dt")})
    if "seed" in data:
        seed = data["seed"]
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ConfigError(f"[simulation] seed = {seed!r}: expected a whole number")
        out["seed"] = seed
    if "initial_state" in data:
        out["initial_state"] = data["initial_state"]  # SimConfig checks the value
    return out


def _parse_path(data: Mapping[str, Any]) -> dict[str, Any]:
    if "points" not in data:
        raise ConfigError("[path] missing key 'points'")
    points = data["points"]
    if not isinstance(points, list):
        raise ConfigError(f"[path] points = {points!r}: expected a list of [x, y] pairs")
    closed = data.get("closed", True)
    if not isinstance(closed, bool):
        raise ConfigError(f"[path] closed = {closed!r}: expected true or false")
    return {
        "points": [_point("path", f"points[{i}]", p) for i, p in enumerate(points)],
        "closed": closed,
    }


def _parse_region(name: str, data: object) -> dict[str, Any]:
    section = f"regions.{name}"
    spec = _table(section, data, _REGION_KEYS)
    for key in ("center", "width", "height"):
        if key not in spec:
            raise ConfigError(f"[{section}] missing key '{key}'")
    region: dict[str, Any] = {
        "center": _point(section, "center", spec["center"]),
        "rotation_deg": _number(section, "rotation_deg", spec.get("rotation_deg", 0.0)),
    }
    for key in ("width", "height"):
        region[key] = _number(section, key, spec[key])
        if region[key] <= 0:
            raise ConfigError(f"[{section}] {key} = {spec[key]!r}: must be > 0")
    return region


def from_dict(data: Mapping[str, Any]) -> SimConfig:
    """Check a parsed TOML document and turn it into a :class:`SimConfig`."""
    _check_keys("top level", data, _SECTIONS)
    sim = _table("simulation", data.get("simulation", {}), _SIMULATION_KEYS)
    sensor = _table("sensor", data.get("sensor", {}), _SENSOR_KEYS)
    motion = _table("motion", data.get("motion", {}), _MOTION_KEYS)
    regions = _table("regions", data.get("regions", {}), {"A", "B"})
    path = _table("path", data["path"], _PATH_KEYS) if "path" in data else {}

    try:
        motion_cfg = MotionConfig(**_numbers("motion", motion))
    except ValueError as exc:
        raise ConfigError(f"[motion] {exc}") from exc
    scalars: dict[str, Any] = {**_parse_simulation(sim), **_numbers("sensor", sensor)}
    return SimConfig(
        **scalars,
        motion=motion_cfg,
        path=_parse_path(path) if path else {},
        regions={name: _parse_region(name, spec) for name, spec in regions.items()},
    )


def load_config(path: str | FsPath | None = None) -> SimConfig:
    """Load a TOML file (the bundled default scenario when ``path`` is None)."""
    target = FsPath(path) if path else DEFAULT_CONFIG
    try:
        with target.open("rb") as fh:
            data = tomllib.load(fh)
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {target}") from exc
    except OSError as exc:  # a directory, no permission, ...
        raise ConfigError(f"cannot read config file {target}: {exc.strerror or exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {target}: {exc}") from exc
    try:
        return from_dict(data)
    except ConfigError as exc:
        raise ConfigError(f"{target}: {exc}") from exc

import dataclasses
import statistics
from pathlib import Path

import pytest

from regionpresence import ConfigError, Presence, Simulation, load_config
from regionpresence.config import from_dict

EXAMPLES = Path(__file__).parent.parent / "examples"


def test_default_scenario_is_tracked_accurately_across_seeds():
    base = load_config()
    for seed in range(8):
        sim = Simulation(dataclasses.replace(base, seed=seed))
        frames = list(sim.frames())
        assert len(frames) == 3000
        assert sim.metrics.accuracy > 0.99, seed
        assert {f.predicted for f in frames} == set(Presence)  # visits A, B and outside
        truth_changes = sum(a.truth != b.truth for a, b in zip(frames, frames[1:], strict=False))
        assert sim.metrics.transitions == truth_changes  # no flicker, no missed crossing


def test_alternative_scenario_with_noise_and_concave_region():
    sim = Simulation(load_config(EXAMPLES / "blobs.toml"))
    list(sim.frames())
    assert sim.metrics.accuracy > 0.95


def test_speed_varies_but_matches_configured_mean():
    sim = Simulation(load_config())
    speeds = [f.speed for f in sim.frames()]
    assert statistics.pstdev(speeds) > 0.2
    assert statistics.mean(speeds) == pytest.approx(1.4, abs=0.3)


def test_run_is_reproducible_with_seed():
    cfg = dataclasses.replace(load_config(), duration_s=30)
    a = [f.dist_a for f in Simulation(cfg).frames()]
    b = [f.dist_a for f in Simulation(cfg).frames()]
    assert a == b


def test_changing_region_size_changes_behaviour():
    cfg = load_config()
    regions = {k: dict(v) for k, v in cfg.regions.items()}
    regions["A"]["radius"] = 3
    small = Simulation(dataclasses.replace(cfg, regions=regions))
    frames = list(small.frames())
    t_in_a = sum(f.truth == Presence.IN_A for f in frames)
    t_in_a_default = sum(f.truth == Presence.IN_A for f in Simulation(cfg).frames())
    assert t_in_a < t_in_a_default and small.metrics.accuracy > 0.95


def test_overlapping_regions_rejected():
    cfg = load_config()
    regions = {k: dict(v) for k, v in cfg.regions.items()}
    regions["A"]["radius"] = 60
    with pytest.raises(ValueError, match="overlap"):
        Simulation(dataclasses.replace(cfg, regions=regions))


@pytest.mark.parametrize("data", [
    {"bogus": {}},
    {"simulation": {"dt": 0}, "path": {"kind": "waypoints"}, "regions": {"A": {}, "B": {}}},
    {"path": {"kind": "waypoints"}, "regions": {"A": {}}},
    {"regions": {"A": {}, "B": {}}},
    {"simulation": {"typo": 1}},
])
def test_config_errors(data):
    with pytest.raises(ConfigError):
        from_dict(data)


def test_missing_config_file():
    with pytest.raises(ConfigError, match="not found"):
        load_config("/nonexistent.toml")


def test_adjacent_strips_from_sketch_left_to_right():
    for seed in range(5):
        cfg = dataclasses.replace(load_config(EXAMPLES / "adjacent_strips.toml"), seed=seed)
        sim = Simulation(cfg)
        frames = list(sim.frames())
        order = [f.predicted for i, f in enumerate(frames) if i == 0 or f.changed]
        assert order == [Presence.OUTSIDE, Presence.IN_A, Presence.IN_B, Presence.OUTSIDE], seed
        assert sim.metrics.accuracy > 0.99

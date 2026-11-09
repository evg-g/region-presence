import dataclasses
import statistics
from pathlib import Path

import pytest

from region_presence import ConfigError, Presence, Simulation, load_config
from region_presence.config import from_dict

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


def test_rotated_rectangles_with_more_noise():
    sim = Simulation(load_config(EXAMPLES / "noisy_rotated.toml"))
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
    regions["A"]["width"] = 6
    regions["A"]["height"] = 6
    small = Simulation(dataclasses.replace(cfg, regions=regions))
    frames = list(small.frames())
    t_in_a = sum(f.truth == Presence.IN_A for f in frames)
    t_in_a_default = sum(f.truth == Presence.IN_A for f in Simulation(cfg).frames())
    assert t_in_a < t_in_a_default and small.metrics.accuracy > 0.95


def test_overlapping_regions_rejected():
    cfg = load_config()
    regions = {k: dict(v) for k, v in cfg.regions.items()}
    regions["A"]["width"] = 200
    with pytest.raises(ValueError, match="overlap"):
        Simulation(dataclasses.replace(cfg, regions=regions))


@pytest.mark.parametrize("data", [
    {"bogus": {}},
    {"simulation": {"dt": 0}, "path": {"points": []}, "regions": {"A": {}, "B": {}}},
    {"path": {"points": []}, "regions": {"A": {}}},
    {"regions": {"A": {}, "B": {}}},
    {"simulation": {"typo": 1}},
])
def test_config_errors(data):
    with pytest.raises(ConfigError):
        from_dict(data)


def test_missing_config_file():
    with pytest.raises(ConfigError, match="not found"):
        load_config("/nonexistent.toml")


@pytest.mark.parametrize("scenario", ["shared_wall.toml", "partial_wall.toml"])
def test_shared_wall_left_to_right_goes_directly_from_a_to_b(scenario):
    for seed in range(5):
        cfg = dataclasses.replace(load_config(EXAMPLES / scenario), seed=seed)
        sim = Simulation(cfg)
        frames = list(sim.frames())
        order = [f.predicted for i, f in enumerate(frames) if i == 0 or f.changed]
        assert order == [Presence.OUTSIDE, Presence.IN_A, Presence.IN_B, Presence.OUTSIDE], seed
        assert sim.metrics.accuracy > 0.99


def _scenario(points, a_center, a_size, b_center, b_size, seed):
    cfg = load_config(EXAMPLES / "shared_wall.toml")
    return dataclasses.replace(
        cfg, seed=seed, path={"closed": False, "points": points},
        regions={
            "A": {"center": a_center, "width": a_size[0], "height": a_size[1]},
            "B": {"center": b_center, "width": b_size[0], "height": b_size[1]},
        },
    )


def _sequence(cfg):
    sim = Simulation(cfg)
    frames = list(sim.frames())
    return [f.predicted for i, f in enumerate(frames) if i == 0 or f.changed], sim.metrics.accuracy


def test_passing_above_the_shared_wall_goes_through_outside():
    # A: x 10-30, y 12-28; B: x 30-50, y 14-34. The walk leaves A through its top (y=28),
    # then enters B through the part of B's left wall that A does not touch (y > 28).
    for seed in range(5):
        cfg = _scenario([[-5, 20], [20, 20], [20, 31], [26, 31], [40, 31], [70, 31]],
                        [20, 20], (20, 16), [40, 24], (20, 20), seed)
        order, acc = _sequence(cfg)
        assert order == [Presence.OUTSIDE, Presence.IN_A, Presence.OUTSIDE, Presence.IN_B,
                         Presence.OUTSIDE], seed
        assert acc > 0.98


def test_corner_touching_rectangles_are_not_treated_as_shared_wall():
    # A: x 10-30, y 12-28; B: x 30-50, y 28-44 -> they touch only at the corner (30, 28).
    for seed in range(5):  # the walk passes within ~1.7 of the shared corner
        cfg = _scenario([[-5, 20], [20, 20], [27, 26], [29, 29.5], [33, 31], [40, 34], [70, 36]],
                        [20, 20], (20, 16), [40, 36], (20, 16), seed)
        order, acc = _sequence(cfg)
        assert order == [Presence.OUTSIDE, Presence.IN_A, Presence.OUTSIDE, Presence.IN_B,
                         Presence.OUTSIDE], seed
        assert acc > 0.98


def test_initial_state_must_match_where_the_path_starts():
    cfg = dataclasses.replace(load_config(), initial_state="in_a")
    with pytest.raises(ValueError, match="initial_state"):
        Simulation(cfg)


def test_invalid_initial_state_rejected():
    with pytest.raises(ConfigError, match="initial_state"):
        dataclasses.replace(load_config(), initial_state="middle")


def test_starting_inside_a_region_is_supported():
    cfg = load_config()
    regions = {k: dict(v) for k, v in cfg.regions.items()}
    regions["A"]["center"] = [0, 20]  # the default path starts at (0, 20): inside A
    cfg = dataclasses.replace(cfg, regions=regions, initial_state="in_a")
    sim = Simulation(cfg)
    list(sim.frames())
    assert sim.metrics.accuracy > 0.98


def _sequences(points, region_a, region_b, seeds=range(5)):
    """For each seed: (classifier's sequence of states, true sequence of states)."""
    base = load_config(EXAMPLES / "shared_wall.toml")
    for seed in seeds:
        cfg = dataclasses.replace(base, seed=seed, path={"closed": False, "points": points},
                                  regions={"A": region_a, "B": region_b})
        frames = list(Simulation(cfg).frames())
        predicted = [f.predicted for i, f in enumerate(frames) if i == 0 or f.changed]
        truth = [f.truth for i, f in enumerate(frames) if i == 0 or f.truth != frames[i - 1].truth]
        yield predicted, truth


RECT_A = {"center": [20, 20], "width": 20, "height": 16}
RECT_B_SHARED = {"center": [40, 20], "width": 20, "height": 16}
RECT_B_GAP = {"center": [45, 20], "width": 20, "height": 16}


@pytest.mark.parametrize("points,region_b", [
    ([[70, 20], [40, 21], [20, 19], [-5, 20]], RECT_B_SHARED),                     # shared wall, right to left
    ([[-5, 20], [25, 20], [36, 21], [24, 19], [37, 20], [70, 20]], RECT_B_SHARED),  # back and forth across it
    ([[-5, 20], [25, 20], [42, 21], [28, 19], [50, 20], [70, 20]], RECT_B_GAP),     # back and forth with a gap
])
def test_indication_follows_the_true_sequence(points, region_b):
    for predicted, truth in _sequences(points, RECT_A, region_b):
        assert predicted == truth

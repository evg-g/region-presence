import random
import statistics

import pytest

from region_presence.trajectory import (
    MotionConfig,
    SpeedProcess,
    build_path,
    waypoint_path,
)


def test_waypoint_path_passes_through_points_and_wraps():
    pts = [(0, 0), (10, 0), (10, 10), (0, 10)]
    path = waypoint_path(pts, closed=True)
    for p in pts:
        assert min(abs(q[0] - p[0]) + abs(q[1] - p[1]) for q in path.polyline(2000)) < 0.05
    a, b = path.position_at(1.0), path.position_at(1.0 + path.length)
    assert a == pytest.approx(b)


def test_open_path_finishes():
    path = waypoint_path([(0, 0), (10, 0)], closed=False)
    assert not path.finished(5) and path.finished(path.length)
    assert path.position_at(1e6) == pytest.approx((10, 0))


def test_path_config_validation():
    assert build_path({"points": [[0, 0], [10, 0], [10, 10]]}).closed
    with pytest.raises(ValueError, match="unknown keys"):
        build_path({"points": [[0, 0], [1, 1]], "kind": "spiral"})
    with pytest.raises(ValueError, match="missing key"):
        build_path({"closed": True})


def test_speed_is_variable_bounded_and_has_requested_mean():
    cfg = MotionConfig(mean_speed=1.4, speed_std=0.5, correlation_time=5.0, max_speed=3.0)
    proc = SpeedProcess(cfg, 0.1, random.Random(1))
    v = [proc.step() for _ in range(20000)]
    assert all(cfg.min_speed <= x <= cfg.max_speed for x in v)
    assert statistics.mean(v) == pytest.approx(1.4, abs=0.1)
    assert statistics.pstdev(v) > 0.3  # not constant


def test_motion_config_validation():
    with pytest.raises(ValueError):
        MotionConfig(mean_speed=5, max_speed=3)

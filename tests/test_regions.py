import math

import pytest

from region_presence.regions import (
    CircleRegion,
    PolygonRegion,
    assert_disjoint,
    build_region,
    ellipse,
    rectangle,
)


def test_circle_distance_and_contains():
    c = CircleRegion("A", (0, 0), 5)
    assert c.distance_to_boundary((0, 0)) == pytest.approx(5)
    assert c.distance_to_boundary((8, 0)) == pytest.approx(3)
    assert c.contains((1, 1)) and not c.contains((6, 0))


def test_rotated_rectangle():
    r = rectangle("B", (0, 0), 4, 2, rotation_deg=90)  # becomes 2 wide, 4 tall
    assert r.contains((0.9, 1.9)) and not r.contains((1.1, 0))
    assert r.distance_to_boundary((0, 0)) == pytest.approx(1.0)


def test_concave_polygon():
    l_shape = PolygonRegion("A", [(0, 0), (4, 0), (4, 1), (1, 1), (1, 4), (0, 4)])
    assert l_shape.contains((0.5, 3)) and not l_shape.contains((2, 2))
    assert l_shape.distance_to_boundary((2, 2)) == pytest.approx(1.0)


def test_ellipse_close_to_analytic_extent():
    e = ellipse("B", (0, 0), 10, 5)
    assert e.contains((9.9, 0)) and not e.contains((0, 5.2))
    assert e.distance_to_boundary((0, 0)) == pytest.approx(5, rel=0.01)


def test_max_inner_distance():
    assert CircleRegion("A", (0, 0), 3).max_inner_distance() == 3
    assert rectangle("B", (0, 0), 10, 4).max_inner_distance() == pytest.approx(2, rel=0.05)


def test_disjoint_check():
    a, b = CircleRegion("A", (0, 0), 5), CircleRegion("B", (20, 0), 5)
    assert_disjoint(a, b)
    with pytest.raises(ValueError, match="overlap"):
        assert_disjoint(a, CircleRegion("B", (6, 0), 5))
    with pytest.raises(ValueError, match="overlap"):  # nested
        assert_disjoint(a, CircleRegion("B", (0, 0), 1))


@pytest.mark.parametrize("spec,msg", [
    ({"shape": "star"}, "unknown shape"),
    ({"shape": "circle", "center": [0, 0]}, "missing key"),
    ({"shape": "circle", "center": [0, 0], "radius": -1}, "radius"),
    ({"shape": "circle", "center": [0, 0], "radius": 1, "colour": 1}, "unknown keys"),
    ({"shape": "polygon", "vertices": [[0, 0], [1, 1]]}, "at least 3"),
    ({"shape": "polygon", "vertices": [[0, 0], [1, 1], [2, 2]]}, "zero area"),
])
def test_build_region_validation(spec, msg):
    with pytest.raises(ValueError, match=msg):
        build_region("A", spec)


def test_polygon_outline_lies_on_boundary():
    r = rectangle("B", (3, 3), 6, 2, 30)
    assert all(r.distance_to_boundary(p) < 1e-9 for p in r.outline(100))
    assert not math.isnan(r.bounds()[0])

import math

import pytest

from region_presence.regions import Rectangle, assert_disjoint, build_region


def rect(cx, cy, w, h, rot=0.0, name="A"):
    return Rectangle(name, (cx, cy), w, h, rot)


def test_distance_inside_is_to_nearest_edge():
    r = rect(0, 0, 20, 10)  # x in [-10, 10], y in [-5, 5]
    assert r.distance_to_boundary((0, 0)) == pytest.approx(5)
    assert r.distance_to_boundary((8, 0)) == pytest.approx(2)
    assert r.contains((0, 0))


def test_distance_outside_to_edge_and_to_corner():
    r = rect(0, 0, 20, 10)
    assert r.distance_to_boundary((13, 0)) == pytest.approx(3)        # facing an edge
    assert r.distance_to_boundary((13, 9)) == pytest.approx(5)        # past a corner: 3-4-5
    assert not r.contains((13, 0))


def test_point_on_boundary_has_zero_distance_and_is_not_inside():
    r = rect(0, 0, 20, 10)
    assert r.distance_to_boundary((10, 0)) == pytest.approx(0)
    assert not r.contains((10, 0))


def test_rotation_by_90_degrees_swaps_width_and_height():
    r = rect(0, 0, 20, 10, rot=90)  # now 10 wide, 20 tall
    assert r.contains((0, 9)) and not r.contains((9, 0))
    assert r.distance_to_boundary((0, 0)) == pytest.approx(5)


def test_rotated_rectangle_corners():
    r = rect(0, 0, 2, 2, rot=45)  # a diamond with corners on the axes
    assert any(math.isclose(x, math.sqrt(2)) and abs(y) < 1e-9 for x, y in r.corners())
    assert r.distance_to_boundary((math.sqrt(2) + 1, 0)) == pytest.approx(1)


def test_outline_lies_on_the_boundary():
    r = rect(3, 3, 6, 2, rot=30)
    assert all(r.distance_to_boundary(p) < 1e-9 for p in r.outline(100))


@pytest.mark.parametrize("b", [
    rect(40, 0, 20, 10, name="B"),        # case 1: gap
    rect(20, 0, 20, 10, name="B"),        # case 2: shared wall
    rect(20, 3, 20, 4, name="B"),         # case 3: part of a wall
    rect(20, 10, 20, 10, name="B"),       # touching at a corner only
])
def test_touching_or_separated_rectangles_are_allowed(b):
    assert_disjoint(rect(0, 0, 20, 10), b)


@pytest.mark.parametrize("b", [
    rect(15, 3, 20, 10, name="B"),        # partial overlap (case 4)
    rect(0, 0, 20, 10, name="B"),         # exactly on top of each other
    rect(0, 0, 4, 4, name="B"),           # B fully inside A
    rect(0, 0, 2, 40, name="B"),          # a cross: no corner inside the other
    rect(18, 0, 20, 10, rot=45, name="B"),  # rotated, poking in
])
def test_overlapping_rectangles_are_rejected(b):
    with pytest.raises(ValueError, match="overlap"):
        assert_disjoint(rect(0, 0, 20, 10), b)


@pytest.mark.parametrize("spec,msg", [
    ({"center": [0, 0], "width": 5}, "missing key"),
    ({"center": [0, 0], "width": 5, "height": -1}, "must be > 0"),
    ({"center": [0, 0], "width": 5, "height": 5, "radius": 1}, "unknown keys"),
])
def test_build_region_validation(spec, msg):
    with pytest.raises(ValueError, match=msg):
        build_region("A", spec)


def test_depth_is_half_of_the_shorter_side():
    assert Rectangle("A", (0, 0), 20, 16).depth == 8
    assert Rectangle("A", (5, 5), 6, 30, rotation_deg=37).depth == 3

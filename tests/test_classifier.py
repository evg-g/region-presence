"""Classifier tests on scripted distance sequences (no simulator involved)."""
import pytest

from region_presence import ClassifierConfig, InvalidReadingError, Presence, PresenceClassifier

A, B, OUT = Presence.IN_A, Presence.IN_B, Presence.OUTSIDE


def run(seq_a, seq_b, **kw):
    """Feed paired readings; returns the state after every sample."""
    it = iter(zip(seq_a, seq_b, strict=True))
    cur = [0.0, 0.0]

    def advance():
        cur[0], cur[1] = next(it)

    cfg = ClassifierConfig(crossing_threshold=kw.pop("L", 0.6), **kw)
    clf = PresenceClassifier(lambda: cur[0], lambda: cur[1], cfg)
    out = []
    for _ in seq_a:
        advance()
        out.append(clf.update().state)
    return out


FAR = 50.0


def test_enter_and_leave_region_a():
    # approach A, cross, go deep, come back, cross out
    da = [5, 3, 1.5, 0.3, 0.1, 1.0, 3, 6, 3, 1.0, 0.2, 0.1, 1.2, 4, 8]
    states = run(da, [FAR] * len(da))
    assert states[:4] == [OUT] * 4
    assert states[5] == A and states[9] == A
    assert states[-1] == OUT
    assert sum(1 for a, b in zip(states, states[1:], strict=False) if a != b) == 2


def test_enter_b_directly_after_a():
    da = [FAR, FAR, FAR, FAR, FAR, FAR]
    db = [3, 1, 0.1, 1.0, 3, 5]
    assert run(da, db, L=2.0)[-1] == B


def test_crossing_between_samples_is_caught():
    # never samples closer than 0.25 to the boundary, but d_prev + d_cur <= L
    states = run([2, 0.28, 0.27, 2], [FAR] * 4)
    assert states[-1] == A


def test_fast_jump_outside_of_threshold_is_not_a_crossing():
    # d drops 3 -> 2: far from the boundary, nothing happens
    assert run([3, 2, 3, 2], [FAR] * 4) == [OUT] * 4


def test_single_crossing_does_not_fire_repeatedly():
    # a real crossing (the sensor approaches from far away), then it wobbles near the edge
    # inside the L zone: the state must flip once and stay
    da = [5, 3, 1.5, 0.3, 0.1, 0.35, 0.3, 0.4, 0.3, 0.2, 0.3, 0.25, 0.3, 0.2]
    states = run(da, [FAR] * len(da))
    assert states[0] == OUT and states[-1] == A
    assert sum(1 for x, y in zip(states, states[1:], strict=False) if x != y) == 1


def test_starting_inside_the_zone_does_not_fire():
    # the first sample is already near the edge: nothing is known about a crossing yet
    states = run([0.5, 0.4, 0.3, 0.2, 0.25, 0.2, 0.3, 0.4, 1.5, 4], [FAR] * 10)
    assert states == [OUT] * 10


def test_slow_crossing_fires_when_leaving_zone():
    # distance never visibly "turns up" before leaving the zone
    da = [3, 1.0, 0.5, 0.25, 0.2, 0.2, 0.2, 0.3, 0.45, 1.0, 3.0]
    states = run(da, [FAR] * len(da))
    assert states[-1] == A


def test_initial_state_respected():
    da = [8, 6, 4, 2, 0.5, 0.2, 1.0, 3]
    assert run(da, [FAR] * 8, L=2.0, initial_state=A)[-1] == OUT


def test_a_then_b_sequence():
    da = [4, 1, 0.1, 1, 4, 1, 0.1, 1, 4, 20, 40] + [60] * 8
    db = [60] * 11 + [20, 4, 1, 0.1, 1, 4, 8]  + [8]
    states = run(da, db, L=2.0)
    assert states[3] == A and states[8] == OUT and states[10] == OUT
    assert states[-1] == B


def test_config_validation_and_derivation():
    with pytest.raises(ValueError):
        ClassifierConfig(crossing_threshold=0)
    cfg = ClassifierConfig.from_motion(max_speed=3.0, dt=0.1, noise_std=0.05, sigma_multiplier=3)
    assert cfg.crossing_threshold == pytest.approx(0.3 + 0.3)


def test_classifier_uses_only_the_two_callables():
    clf = PresenceClassifier(lambda: 10.0, lambda: 10.0, ClassifierConfig(0.5))
    assert clf.update().state == OUT and clf.state == OUT


def test_adjacent_regions_move_directly_from_a_to_b():
    # start inside A, walk to the shared A|B boundary (both distances reach ~0), continue into B
    da = [10, 6, 2, 0.1, 2, 6, 10, 10]
    db = [30, 26, 22, 0.1, 2, 6, 10, 10]
    states = run(da, db, L=3.0, initial_state=A)
    assert states[0] == A and states[-1] == B
    assert OUT not in states  # never flickers through Outside


@pytest.mark.parametrize("bad", [-0.3, float("nan"), float("inf"), "far", None, "3.5", True, b"4"])
def test_invalid_reading_is_rejected_with_a_clear_message(bad):
    clf = PresenceClassifier(lambda: bad, lambda: 10.0, ClassifierConfig(0.6))
    with pytest.raises(InvalidReadingError, match=r"get_dist_a\(\) returned"):
        clf.update()


def test_bad_reading_does_not_change_the_state():
    readings = iter([5.0, 3.0, -1.0, 2.0])
    current = [0.0]

    def get_a():
        return current[0]

    clf = PresenceClassifier(get_a, lambda: 50.0, ClassifierConfig(0.6))
    for _ in range(2):
        current[0] = next(readings)
        clf.update()
    current[0] = next(readings)  # -1.0
    with pytest.raises(InvalidReadingError):
        clf.update()
    assert clf.state == OUT
    current[0] = next(readings)  # a valid reading afterwards still works
    assert clf.update().state == OUT


def test_zero_distance_is_valid():
    clf = PresenceClassifier(lambda: 0.0, lambda: 0.0, ClassifierConfig(0.6))
    assert clf.update().state == OUT


@pytest.mark.parametrize("threshold", [0.0, -1.0, float("nan"), float("inf")])
def test_threshold_must_be_a_positive_finite_number(threshold):
    with pytest.raises(ValueError, match="crossing_threshold"):
        ClassifierConfig(threshold)


def test_from_motion_names_the_bad_input():
    with pytest.raises(ValueError, match="dt"):
        ClassifierConfig.from_motion(max_speed=3.0, dt=0.0, noise_std=0.05)
    with pytest.raises(ValueError, match="noise_std"):
        ClassifierConfig.from_motion(max_speed=3.0, dt=0.1, noise_std=float("nan"))


# ----- depth check -----------------------------------------------------------------------

DEPTH = 8.0  # like a 20 x 16 rectangle


def test_wrong_state_heals_when_the_distance_is_too_large_for_the_state(caplog):
    # a false crossing (the sensor idles next to the edge), then it walks 20 m away
    da = [5, 3, 1.5, 0.15, 0.17, 0.14, 0.16, 0.15, 2, 5, 10, 15, 20, 25]
    without = run(da, [FAR] * len(da))
    assert without[-1] == A  # no depth check: the mistake stays forever
    with caplog.at_level("WARNING"):
        states = run(da, [FAR] * len(da), max_depth_a=DEPTH)
    assert A in states and states[-1] == OUT
    assert "resetting to Outside" in caplog.text


def test_depth_check_leaves_a_correct_state_alone():
    # walk into A, to its centre (8 m from every edge, a little noise on top), and back out
    da = [5, 3, 1.5, 0.3, 0.1, 1, 4, 7, 8.0, 8.3, 8.4, 7, 4, 1, 0.1, 0.3, 1.5, 3]
    states = run(da, [FAR] * len(da), max_depth_a=DEPTH)
    assert states[5:15] == [A] * 10
    assert states[-1] == OUT


def test_depth_check_covers_region_b_too():
    db = [5, 3, 1.5, 0.15, 0.17, 0.14, 0.16, 0.15, 2, 5, 10, 15, 20, 25]
    assert run([FAR] * len(db), db, max_depth_b=DEPTH)[-1] == OUT


def test_region_that_is_too_small_for_the_threshold_is_rejected():
    with pytest.raises(ValueError, match="max_depth_a"):
        ClassifierConfig(crossing_threshold=0.6, max_depth_a=0.5)
    with pytest.raises(ValueError, match="max_depth_b"):
        ClassifierConfig(crossing_threshold=0.6, max_depth_b=float("nan"))


# ----- known limitations (documented in the README) --------------------------------------
# Each test says what a perfect classifier would do. They are marked as expected failures:
# strict=True makes the suite fail if one of them ever starts passing, so the README
# has to be updated when that happens.

@pytest.mark.xfail(strict=True, reason="idling next to an edge looks like a crossing")
def test_standing_still_next_to_an_edge_keeps_the_state():
    da = [5, 3, 1.5] + [0.15, 0.17, 0.14, 0.16, 0.15, 0.18, 0.14] * 3
    assert run(da, [FAR] * len(da))[-1] == OUT


@pytest.mark.xfail(strict=True, reason="a pass shallower than L never leaves the threshold zone")
def test_shallow_pass_through_a_corner_ends_outside():
    # in 0.2 m and straight out again
    da = [3, 1.5, 0.5, 0.1, 0.2, 0.2, 0.1, 0.5, 1.5, 3]
    assert run(da, [FAR] * len(da))[-1] == OUT


@pytest.mark.xfail(strict=True, reason="touching the edge and turning back looks like a crossing")
def test_touching_an_edge_and_turning_back_keeps_the_state():
    da = [5, 3, 1.5, 0.3, 0.15, 0.3, 1.5, 3, 5]
    assert run(da, [FAR] * len(da))[-1] == OUT


# ----- architecture ----------------------------------------------------------------------

def test_classifier_module_imports_only_the_standard_library():
    """The classifier must not depend on the simulator, the sensor or matplotlib."""
    import ast
    import sys
    from pathlib import Path

    import region_presence.classifier as module

    tree = ast.parse(Path(module.__file__).read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "relative import: the classifier would depend on its own package"
            imported.add((node.module or "").split(".")[0])
    assert imported <= set(sys.stdlib_module_names), imported - set(sys.stdlib_module_names)

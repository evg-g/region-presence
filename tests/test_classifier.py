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
    states = run([0.5, 0.4, 0.3, 0.2, 0.25, 0.2, 0.3, 0.4, 1.5, 4], [FAR] * 10, initial_state=OUT)
    # starts inside the zone: armed only after leaving it once -> no spurious toggles
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

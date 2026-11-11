# Limitations, accuracy and possible improvements

The short version is in the [README](../README.md). This page has the full lists.

## Limitations

These come from the problem itself (an unsigned distance) and from using only the
current and the previous reading. The numbers below come from
[`scripts/run_experiments.py`](../scripts/run_experiments.py), which anyone can rerun.
The first two are covered by tests in
[`tests/test_classifier.py`](../tests/test_classifier.py), marked as expected failures.

* **Standing still, sliding along an edge, or touching it and turning back** within
  about 0.3 m of the edge looks like a crossing, and the state flips wrongly. The
  depth check corrects it only after the sensor has moved far from the region. I
  measured 100 of 100 runs wrong after idling 0.15 m from an edge, and 0 of 100
  still wrong after walking 40 m away.
* **A pass shallower than `L`** (into a corner and straight out again) ends in the
  wrong state, for the same reason, and is corrected the same way.
* **A false "Outside" while really inside** cannot be detected: a distance below the
  region's depth fits both states.
* **A slow sensor is indicated early.** The flip comes before the edge by about
  0.3 m at 0.05 m/s and 0.2 m at 0.4 m/s. At about 0.8 m/s it is on time, and
  above that it is late (about 0.13 m at 1.4 m/s).
* **A gap between A and B smaller than about `L`** (0.6 m by default) is read as a
  shared wall, so no Outside appears between them.
* **Real GPS noise is much larger than 5 cm.** `L` grows with the noise, and so does
  the delay. With the default scenario and noise of 0.2 m the state sequence is
  right in 30 of 30 runs (98.6% of readings correct); at 0.5 m in 27 of 30
  (95.4%); at 1 m in 15 of 30 (89.4%). With noise of 2 m, `L` is larger than the
  regions and the config is rejected.
* **The sample interval is fixed.** `update()` has no timestamp, so dropped or late
  samples break the calculation of `L`.
* **A speed above `max_speed`** can make the sensor skip over a crossing.
* **After an invalid reading** the next valid one is compared with the last valid one as
  if only one sample had passed, although the gap may be longer.

## Accuracy

Over 100 seeds per scenario, the indication matches the true state on these shares
of readings. The misses are the short delays right after each crossing. The last
column counts the runs where the list of state changes was exactly the true one.

| Scenario | Mean | Worst run | Correct sequence |
|---|---|---|---|
| default | 99.75% | 99.33% | 100 of 100 |
| `shared_wall` | 99.65% | 98.69% | 100 of 100 |
| `partial_wall` | 99.67% | 98.91% | 100 of 100 |
| `noisy_rotated` | 99.19% | 97.92% | 99 of 100 |

The simulator uses the same top speed and noise as the classifier assumes, so these
are best-case numbers inside the limits above.

## Possible improvements

Left out on purpose: they change the core of the algorithm, the task has only two
regions, and I preferred not to risk the part that works and is well tested.

* One small state object per region instead of three dictionaries keyed by `"A"`
  and `"B"`. Adding a third region would then not need a rewrite of the crossing logic.
* The shared-wall rule as a separate policy, not part of the main state machine.
* A `Region` protocol (`distance_to_boundary`, `contains`), so other shapes need no
  change in the classifier or the sensor.
* Dependency injection in `Simulation`, so another sensor or classifier can be tested.
* Splitting `run_gui` into smaller functions.
* A `Trajectory` protocol, so a recorded GPS track can replace the generated path.
* Clearer diagnostics: a sample index or time in `InvalidReadingError` and in the
  "missed exit" warning, which should also be rate limited.
* `Simulation.frames()` is not safe to iterate twice (metrics are counted again), and one
  random generator feeds both speed and noise, so seeded runs change when either is changed.
* More automatic checks: a CI job that builds the wheel and runs it in a clean environment,
  a coverage threshold, `pre-commit`, a lock file, a property-based test (Hypothesis), and
  journey scenarios as TOML files driven by `pytest.mark.parametrize`.
* Timestamps in `update()`, so `L` is calculated from the real time between samples.
* `asyncio`, if the sensor becomes a network device or there are several sensors.
* Vectorising with NumPy, for batch work such as replaying long recordings.

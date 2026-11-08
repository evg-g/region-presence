# region-presence

Real-time classification of a moving sensor as **In A / In B / Outside**, using only
two zero-argument functions: `get_dist_a()` and `get_dist_b()` (shortest distance to
the boundary of region A / B). Includes a simulator (non-constant speed, noisy
readings, configurable region shapes) and a live view.

![demo](docs/demo.gif)

## Quick start

```bash
pip install -e ".[gui]"          # core has no dependencies; matplotlib only for the live plot
region-presence                  # live plot, bundled scenario, 5x real time
region-presence --headless -v    # console only (stdlib only), every sample
region-presence -c examples/blobs.toml --speedup 10
region-presence -c examples/adjacent_strips.toml   # layout of the assignment sketch: Out | A | B | Out
region-presence --save docs/demo.gif --duration 70
```

`python -m regionpresence ...` works too. Options: `--config`, `--headless`, `--speedup`
(0 = as fast as possible), `--duration`, `--seed`, `--save`, `--verbose`.

## The problem, and the algorithm

The readings are **unsigned** distances, so one sample cannot tell inside from
outside. The classifier therefore detects *boundary crossings* and toggles state.

Between consecutive samples the sensor moves at most `v_max * dt`. If it crossed the
boundary of region R in that interval it travelled at least `d_prev` (to reach the
boundary) plus `d_cur` (to leave it), so

    d_prev + d_cur  <=  L,    L = v_max * dt + 2 * k * sigma

(`sigma` = sensor noise, `k` = 3 by default). When this holds the crossing is
*possible*; it is declared as soon as the distance turns upward (the sensor is moving
away from the boundary) or, if it never does, when it leaves the `L` zone. The state
then toggles `Outside <-> In R`. A per-region latch stops one crossing from firing
twice. Each decision uses only the current and previous sample: **no look-ahead, no
post-processing**; the indication lags a crossing by about one sample.

Self-healing: a distance larger than the deepest point of region R (plus `L`) proves
the sensor is not in R, which corrects a missed or spurious crossing.

### Assumptions and limitations (read these)

* The starting side must be known (`initial_state`, default Outside; the simulator
  passes the true start). Unsigned distances cannot reveal it.
* A pure *touch-and-return* (reaching the boundary within noise and turning back
  without crossing) is indistinguishable from a crossing in distance data alone and is
  treated as one. The self-healing bound limits how long such an error can persist.
* `v_max` and `sigma` must really bound the sensor (the defaults come from the config).
  If the real speed exceeds `v_max`, crossings can be missed.
* Region interiors must not overlap (checked at start-up). Regions may touch: with
  adjacent A|B the shared boundary moves the state A <-> B directly (`examples/adjacent_strips.toml`).

## Simulation

* **Motion**: a parametric path (closed Catmull-Rom spline through waypoints, or a
  Lissajous curve) traversed at a speed from an Ornstein-Uhlenbeck process: mean speed,
  std-dev and correlation time are configurable, clipped to `[min_speed, max_speed]`, so
  the sensor accelerates, slows and occasionally pauses.
* **Sensor**: `SimulatedSensor.get_dist_a()/get_dist_b()` take no arguments and return the
  current sample (true distance + Gaussian noise, floored at 0). Ground truth
  exists only for display and metrics; the classifier never sees it.
* **Display**: the map, a large colour-coded indication, the ground truth for comparison
  and the two distance signals with the threshold `L`.

## Configuration (TOML, no code edits)

See [`src/regionpresence/default_config.toml`](src/regionpresence/default_config.toml)
and [`examples/blobs.toml`](examples/blobs.toml).

| Section | Keys |
|---|---|
| `[simulation]` | `duration_s`, `dt`, `seed` |
| `[sensor]` | `noise_std`, `sigma_multiplier` |
| `[motion]` | `mean_speed`, `speed_std`, `correlation_time`, `min_speed`, `max_speed` |
| `[path]` | `kind = "waypoints"` (`points`, `closed`) or `"lissajous"` (`center`, `amplitude`, `freq`, `phase`) |
| `[regions.A]`, `[regions.B]` | `shape = "circle"` (`center`, `radius`), `"rectangle"` (`center`, `width`, `height`, `rotation_deg`), `"ellipse"` (`center`, `rx`, `ry`, `rotation_deg`, `segments`), `"polygon"` (`vertices`, concave allowed) |

Unknown keys, missing keys, overlapping regions and bad values fail fast with a clear message.

## Use the classifier on its own

```python
from regionpresence import ClassifierConfig, PresenceClassifier

cfg = ClassifierConfig.from_motion(max_speed=3.0, dt=0.1, noise_std=0.05)
clf = PresenceClassifier(sensor.get_dist_a, sensor.get_dist_b, cfg)
while True:
    sensor.read_next_sample()
    print(clf.update().state)      # Presence.IN_A / IN_B / OUTSIDE
```

## Project layout

```
src/regionpresence/
  classifier.py   the algorithm (pure, depends only on the two callables)
  regions.py      circle / rectangle / ellipse / polygon geometry
  trajectory.py   parametric paths + speed process
  sensor.py       simulated sensor with get_dist_a()/get_dist_b()
  simulation.py   wiring, frames, accuracy metrics
  config.py       TOML loading and validation
  viz.py, cli.py live plot and command line
tests/            47 tests: geometry, motion statistics, classifier logic, end-to-end, CLI
```

## Development

```bash
pip install -e ".[dev]"
pytest && ruff check src tests && mypy src
```

On the bundled scenario the indication agrees with ground truth on ~99.7% of samples
(the rest is the one-sample lag at each crossing), with no flicker and no missed crossing.

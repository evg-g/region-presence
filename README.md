# region-presence

A small Python project that tells, in real time, whether a moving GPS sensor is
**In A**, **In B** or **Outside**. The only input is two functions,
`get_dist_a()` and `get_dist_b()`, that return the shortest distance from the
sensor to the edge of region A and region B.

The project includes a simulator (the sensor moves along a path at a changing
speed and the distance readings are noisy) and a live view.

![demo](docs/demo.gif)

## Quick start

Requires Python 3.11 or newer.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[gui]"       # matplotlib is only needed for the live view

region-presence               # live view, default scenario, 5x real time
region-presence --headless    # text output only, no matplotlib needed
```

Other scenarios:

```bash
region-presence -c examples/shared_wall.toml     # A and B share a whole wall
region-presence -c examples/partial_wall.toml    # A and B share part of a wall
region-presence -c examples/noisy_rotated.toml   # rotated rectangles, more sensor noise
```

Useful options: `--speedup N` (0 runs as fast as possible), `--duration S`,
`--seed N`, `--verbose` (print every sample), `--save file.gif`.
`python -m region_presence` works the same way.

## How it works

A distance reading has no sign. The sensor can be 3 m from the edge of A while
inside A or while outside it, and one reading cannot tell which. So the
classifier does not look at a single reading. It watches for the moment the
sensor **crosses an edge**, and switches state when that happens.

**Detecting a crossing.** Between two readings the sensor moves at most
`v_max * dt` (top speed times the time between readings). If it crossed the edge
in that time, it first covered `d_prev` to reach the edge and then `d_cur` to
move away from it. So a crossing is only possible when

```
d_prev + d_cur <= L        where  L = v_max * dt + 2 * k * noise
```

The second part of `L` is a margin for sensor noise (`k = 3` by default).
With the default settings `L = 3 * 0.1 + 2 * 3 * 0.05 = 0.6 m`.
The full calculation, with a reading-by-reading example, is in
[`docs/algorithm.md`](docs/algorithm.md).

When the test passes, the crossing is marked as possible. It is confirmed when
the distance starts growing again (the sensor is moving away from the edge), or
when the distance goes back above `L`. Then the state flips:
Outside <-> In A, or Outside <-> In B. After a crossing, the same edge cannot
trigger again until the distance has gone back above `L`, so one crossing is
never counted twice.

Each decision uses only the current and the previous reading. Nothing is
corrected afterwards. The indication is about one reading (0.1 s) behind the
real crossing.

**Shared wall.** If A and B touch, both distances drop to about zero at the
same moment. The classifier treats this as one crossing and moves straight from
A to B (or back) without passing through Outside.

## Assumptions

The assignment leaves a few things open. These are the choices made here:

1. **Distances are never negative.** If the real sensor returned a signed distance
   (negative inside), the problem would reduce to checking the sign.
2. **The starting state is known.** It is set in the config
   (`simulation.initial_state`, default `outside`). The simulator checks that it
   matches where the path really starts. The classifier never sees the true position.
3. **A and B are rectangles that do not overlap** (confirmed with the interviewer).
   Each one can be rotated (`rotation_deg`, default 0).
4. **The sensor moves freely in the plane.** It can curve and turn back; left to right
   is just one possible path.
5. **Top speed and sensor noise are known** (`max_speed`, `noise_std` in the config).
   Speed, noise and sample rate have no values in the assignment. The defaults
   (walking speed 1.4 m/s, 5 cm noise, 10 readings per second) are my choices.

## Region layouts

| Case | Layout | What the sensor sees, moving left to right | Scenario |
|---|---|---|---|
| 1 | Gap between A and B | Outside, A, Outside, B, Outside | default config |
| 2 | A and B share a whole wall | Outside, A, B, Outside | `examples/shared_wall.toml` |
| 3 | A and B share part of a wall | like case 2 through the shared part, like case 1 around it | `examples/partial_wall.toml` |
| 4 | A and B overlap, partly or fully | rejected when the config is loaded | |

Rectangles that touch only at a corner behave like case 1. Overlap is not allowed
because a point inside both regions would be "in A" and "in B" at the same time,
and the output has no such option. The overlap check is exact, so it also rejects
a thin crossing or two identical rectangles.

## Limitations

* If the sensor reaches an edge and turns back without crossing it, the distances
  look the same as a real crossing, and the classifier will count it as one.
* If the real speed is higher than `max_speed`, a crossing can be missed.
* Near a shared wall the two distances are almost equal on both sides of it.
  Only the history shows which side the sensor is on, which is why the classifier
  keeps state.

## Simulation

* **Path:** a smooth curve through a list of points from the config, open or closed.
* **Speed:** has a configured average but keeps changing. It drifts up and down
  around the average (an Ornstein-Uhlenbeck process) and stays between
  `min_speed` and `max_speed`, so the sensor speeds up, slows down and sometimes stops.
* **Readings:** `get_dist_a()` and `get_dist_b()` take no arguments, like a real
  sensor driver. Each returns the true distance plus random noise, never below 0.
  The true position is used only for the display and for measuring accuracy.
* **Display:** a map with both regions, the current state in large colored text,
  the true state next to it for comparison, and a plot of the two distances with
  the line `L`.

## Configuration

Everything is set in a TOML file, with no code changes. See
[`src/region_presence/default_config.toml`](src/region_presence/default_config.toml)
and the files in [`examples/`](examples/).

| Section | Keys |
|---|---|
| `[simulation]` | `duration_s`, `dt`, `seed`, `initial_state` (`outside`, `in_a`, `in_b`) |
| `[sensor]` | `noise_std`, `sigma_multiplier` |
| `[motion]` | `mean_speed`, `speed_std`, `correlation_time`, `min_speed`, `max_speed` |
| `[path]` | `points` (list of `[x, y]`), `closed` |
| `[regions.A]`, `[regions.B]` | `center`, `width`, `height`, `rotation_deg` (optional, degrees counter-clockwise) |

A wrong or missing key, a bad value, or overlapping regions stop the program with
a message that says what to fix.

## Using the classifier on its own

The classifier only needs the two distance functions:

```python
from region_presence import ClassifierConfig, PresenceClassifier

cfg = ClassifierConfig.from_motion(max_speed=3.0, dt=0.1, noise_std=0.05)
clf = PresenceClassifier(sensor.get_dist_a, sensor.get_dist_b, cfg)

# call once per new reading:
print(clf.update().state)    # Presence.IN_A, Presence.IN_B or Presence.OUTSIDE
```

## Project layout

```
src/region_presence/
  classifier.py   the algorithm; uses only the two distance functions
  regions.py      rectangles (optionally rotated) and the overlap check
  trajectory.py   the path and the changing speed
  sensor.py       simulated sensor with get_dist_a() / get_dist_b()
  simulation.py   connects the parts and measures accuracy
  config.py       loads and checks the TOML file
  live_view.py    the live plot
  cli.py          command line
tests/            59 tests: geometry, speed, classifier, full runs, command line
examples/         extra scenarios
```

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check src tests
mypy src
```

The same checks run on GitHub for Python 3.11, 3.12 and 3.13 on every push.

On the default scenario the indication matches the true state on about 99.9% of
readings. The rest are the short delays right after each crossing.

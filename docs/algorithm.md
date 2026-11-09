# How the numbers are calculated

This page shows the formulas behind the code, with the default values filled in.
Units are metres and seconds.

## 1. The crossing threshold `L`

Between two readings the sensor can move at most:

```
step = max_speed * dt = 3.0 * 0.1 = 0.3 m
```

Each reading can be off by up to about `k * noise_std` (with `k = 3`, about 99.7% of
Gaussian noise falls inside this range). Two readings are involved, so the noise margin is:

```
margin = 2 * k * noise_std = 2 * 3 * 0.05 = 0.3 m
```

The threshold is the sum:

```
L = step + margin = 0.6 m
```

If the sensor crossed an edge between two readings, it covered `d_prev` to reach the
edge and `d_cur` to leave it, so `d_prev + d_cur <= L`. When the sum is larger than `L`,
a crossing in that interval is impossible.

`L` is calculated from the config (`ClassifierConfig.from_motion` in `classifier.py`):

| Scenario | `max_speed` | `dt` | `noise_std` | `k` | `L` |
|---|---|---|---|---|---|
| default, `shared_wall`, `partial_wall` | 3.0 | 0.1 | 0.05 | 3 | 0.60 |
| `noisy_rotated` | 3.5 | 0.1 | 0.10 | 3 | 0.95 |

## 2. A crossing, reading by reading

This is the test `test_enter_and_leave_region_a` with `L = 0.6`.
The sensor walks into A; `d` is the reading of `get_dist_a()`.

| Reading | `d_prev` | `d` | `d_prev + d` | What happens |
|---|---|---|---|---|
| 1 | | 5.0 | | first reading, far from the edge |
| 2 | 5.0 | 3.0 | 8.0 | far, nothing |
| 3 | 3.0 | 1.5 | 4.5 | nothing |
| 4 | 1.5 | 0.3 | 1.8 | larger than 0.6: no crossing yet |
| 5 | 0.3 | 0.1 | 0.4 | at most 0.6: crossing is **possible**, wait |
| 6 | 0.1 | 1.0 | 1.1 | `d` is back above `L`: crossing **confirmed**, state becomes In A |

The state changes one reading after the sensor actually crossed.
The code is `PresenceClassifier._detect_crossing` in `classifier.py`.

## 3. Speed

The speed changes every reading. It is pulled back towards the average and gets a
random push each time (an Ornstein-Uhlenbeck process, `SpeedProcess` in `trajectory.py`):

```
a      = exp(-dt / correlation_time) = exp(-0.1 / 5) = 0.980
v_next = mean + a * (v - mean) + speed_std * sqrt(1 - a^2) * random_normal
v_next is then kept between min_speed and max_speed
```

With the defaults, `speed_std * sqrt(1 - a^2) = 0.5 * 0.198 = 0.099 m/s` per reading.
`a = 0.98` means a change in speed fades out over roughly `correlation_time = 5 s`.
The average speed of 1.4 m/s is a normal walking pace.

## 4. Distance to a rectangle

A rectangle has a center, a width, a height and a rotation. To measure a point, the
code first moves the point into the rectangle's own frame: subtract the center, then
rotate by the opposite angle (`Rectangle._to_local` in `regions.py`). In that frame the
rectangle is not rotated and is centred at `(0, 0)`, with half-width `hw` and half-height `hh`:

```
gap_x = |x| - hw
gap_y = |y| - hh

inside  (both gaps <= 0):  distance = min(-gap_x, -gap_y)            nearest edge
outside:                   distance = sqrt(max(gap_x,0)^2 + max(gap_y,0)^2)   nearest edge or corner
```

Example: a 20 x 10 rectangle at the origin (`hw = 10`, `hh = 5`) and the point `(13, 9)`:
`gap_x = 3`, `gap_y = 4`, so the distance is `sqrt(3^2 + 4^2) = 5` (to the corner).

## 5. Overlap check

Two rectangles overlap if they share any area. To check this, project the corners of
both rectangles onto each of the four edge directions (two per rectangle). If on one
of these directions the two projections do not overlap, or only touch, the rectangles
are apart. If they overlap on all four, the rectangles share area and the config is
rejected (`assert_disjoint` in `regions.py`). This is the separating axis test; it is
exact for rectangles, so touching walls and corners are allowed and any overlap is caught.

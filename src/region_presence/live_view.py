"""Live matplotlib view (optional dependency: ``pip install region-presence[gui]``)."""

from __future__ import annotations

from collections import deque
from pathlib import Path as FsPath

from .classifier import Presence
from .simulation import Frame, Simulation

COLORS = {Presence.IN_A: "#1f77b4", Presence.IN_B: "#ff7f0e", Presence.OUTSIDE: "#7f7f7f"}


def run_gui(sim: Simulation, realtime_factor: float = 1.0, save: FsPath | None = None,
            show: bool = True, window_s: float = 30.0) -> None:
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation
    from matplotlib.patches import Polygon

    interval_ms = 40
    steps_per_tick = max(1, round(realtime_factor * interval_ms / 1000 / sim.cfg.dt))
    limit = sim.classifier._cfg.crossing_threshold  # noqa: SLF001 - display only

    fig = plt.figure(figsize=(10, 7), dpi=55 if save else 100)  # small dpi keeps saved GIFs light
    ax_map = fig.add_axes((0.06, 0.37, 0.9, 0.5))
    ax_d = fig.add_axes((0.06, 0.07, 0.9, 0.15))

    for region, color in ((sim.region_a, COLORS[Presence.IN_A]), (sim.region_b, COLORS[Presence.IN_B])):
        outline = region.outline(200)
        ax_map.add_patch(Polygon(outline, closed=True, fc=color, ec=color, alpha=0.25, lw=2))
        cx = sum(p[0] for p in outline) / len(outline)
        cy = sum(p[1] for p in outline) / len(outline)
        ax_map.text(cx, cy, region.name, ha="center", va="center", fontsize=16, color=color)
    px, py = zip(*sim.path.polyline(), strict=True)
    ax_map.plot(px, py, ls=":", lw=0.8, color="#bbbbbb")
    ax_map.set_aspect("equal")
    ax_map.autoscale()
    ax_map.margins(0.05)
    ax_map.set_xlabel("x [m]")
    ax_map.set_ylabel("y [m]")

    trail, = ax_map.plot([], [], lw=1, color="#444444", alpha=0.6)
    dot, = ax_map.plot([], [], "o", ms=12, mec="black")
    banner = fig.text(0.5, 0.95, "", ha="center", va="center", fontsize=24, weight="bold")
    info = fig.text(0.5, 0.895, "", ha="center", va="center", fontsize=10, color="#555555")

    line_a, = ax_d.plot([], [], color=COLORS[Presence.IN_A], label="get_dist_a()")
    line_b, = ax_d.plot([], [], color=COLORS[Presence.IN_B], label="get_dist_b()")
    ax_d.axhline(limit, color="red", ls="--", lw=0.8, label="crossing threshold L")
    ax_d.set_yscale("symlog", linthresh=1.0)
    ax_d.set_ylim(0, 100)
    ax_d.set_xlabel("time [s]")
    ax_d.set_ylabel("distance [m]")
    ax_d.legend(loc="upper left", fontsize=8, ncol=3)

    xs: deque[float] = deque()
    ys: deque[float] = deque()
    ts: deque[float] = deque()
    da: deque[float] = deque()
    db: deque[float] = deque()
    source = sim.frames()
    done = False

    def consume(frame: Frame) -> None:
        xs.append(frame.position[0])
        ys.append(frame.position[1])
        ts.append(frame.t)
        da.append(frame.dist_a)
        db.append(frame.dist_b)
        while ts and ts[0] < frame.t - window_s:
            for q in (ts, da, db):
                q.popleft()
        while len(xs) > int(window_s / sim.cfg.dt):
            xs.popleft()
            ys.popleft()

    def tick(_: int):
        nonlocal done
        last: Frame | None = None
        for _i in range(steps_per_tick):
            try:
                last = next(source)
            except StopIteration:
                done = True
                break
            consume(last)
        if last is None:
            return ()
        trail.set_data(xs, ys)
        dot.set_data([last.position[0]], [last.position[1]])
        dot.set_color(COLORS[last.predicted])
        banner.set_text(f"{last.predicted.value}")
        banner.set_color(COLORS[last.predicted])
        info.set_text(f"t = {last.t:6.1f}s   speed = {last.speed:4.2f} m/s   "
                      f"ground truth: {last.truth.value}   "
                      f"accuracy so far: {sim.metrics.accuracy:6.1%}")
        line_a.set_data(ts, da)
        line_b.set_data(ts, db)
        ax_d.set_xlim(max(0.0, last.t - window_s), max(window_s, last.t))
        return ()

    total_ticks = -(-int(round(sim.cfg.duration_s / sim.cfg.dt)) // steps_per_tick)
    anim = FuncAnimation(fig, tick, frames=total_ticks, interval=interval_ms,
                         blit=False, repeat=False, cache_frame_data=False)
    if save is not None:
        anim.save(str(save), writer="pillow", fps=round(1000 / interval_ms), dpi=55)
    if show:
        plt.show()
    plt.close(fig)

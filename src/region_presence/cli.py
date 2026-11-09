"""Command line interface: ``python -m region_presence`` / ``region-presence``."""

from __future__ import annotations

import argparse
import dataclasses
import logging
import os
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from .config import ConfigError, load_config
from .simulation import Simulation


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="region-presence",
                                description="Real-time In A / In B / Outside classification demo.")
    p.add_argument("-c", "--config", type=Path, help="TOML scenario (default: bundled scenario)")
    p.add_argument("--headless", action="store_true", help="console output instead of the live plot")
    p.add_argument("--speedup", type=float, default=5.0,
                   help="simulated seconds per wall-clock second (0 = as fast as possible; default 5)")
    p.add_argument("--duration", type=float, help="override simulation.duration_s")
    p.add_argument("--seed", type=int, help="override simulation.seed")
    p.add_argument("--save", type=Path, help="save the animation to a .gif (implies no window)")
    p.add_argument("-v", "--verbose", action="store_true", help="print every sample in headless mode")
    return p


def _run_headless(sim: Simulation, speedup: float, verbose: bool) -> None:
    dt = sim.cfg.dt
    start = time.perf_counter()
    for f in sim.frames():
        if speedup > 0:
            delay = start + f.t / speedup - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
        if verbose or f.changed:
            note = "" if f.predicted == f.truth else f"   (truth: {f.truth.value})"
            print(f"t={f.t:7.1f}s  da={f.dist_a:7.2f}  db={f.dist_b:7.2f}  ->  {f.predicted.value}{note}",
                  flush=True)
    m = sim.metrics
    print(f"\n{m.frames} samples @ {1 / dt:g} Hz | indication matches ground truth "
          f"{m.accuracy:.2%} | {m.transitions} transitions")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    try:
        cfg = load_config(args.config)
        overrides = {k: v for k, v in (("duration_s", args.duration), ("seed", args.seed)) if v is not None}
        cfg = dataclasses.replace(cfg, **overrides)
        sim = Simulation(cfg)
    except (ConfigError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.headless:
        try:
            _run_headless(sim, args.speedup, args.verbose)
        except KeyboardInterrupt:  # Ctrl+C: stop quietly
            return 130
        except BrokenPipeError:  # output piped into e.g. `head`, which stopped reading
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
            return 0
        return 0
    try:
        from .live_view import run_gui
    except ImportError:
        print("error: the live plot needs matplotlib (pip install 'region-presence[gui]'); "
              "or use --headless", file=sys.stderr)
        return 2
    try:
        run_gui(sim, realtime_factor=args.speedup if args.speedup > 0 else 50.0,
                save=args.save, show=args.save is None)
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())

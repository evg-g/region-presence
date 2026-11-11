"""Repeat the experiments behind the numbers in docs/limitations.md.

Run it from anywhere, with the package installed:

    pip install -e .
    python scripts/run_experiments.py            # all three experiments
    python scripts/run_experiments.py seeds      # only the seed sweep
    python scripts/run_experiments.py dwell      # only the stop-near-an-edge experiment
    python scripts/run_experiments.py noise      # only the noise sweep

It takes about 15 seconds.
"""

import dataclasses
import logging
import random
import statistics
import sys
from pathlib import Path

from region_presence import ClassifierConfig, Presence, PresenceClassifier, Simulation, load_config

logging.disable(logging.WARNING)  # the classifier logs a warning for every reset; keep the output readable
ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = {
    "default (gap)": None,
    "full shared wall": ROOT / "examples" / "shared_wall.toml",
    "partial shared wall": ROOT / "examples" / "partial_wall.toml",
    "rotated and noisy": ROOT / "examples" / "noisy_rotated.toml",
}


def squeeze(seq):
    """Remove consecutive repeats: [A, A, Out, Out, B] -> [A, Out, B]."""
    out = []
    for item in seq:
        if not out or out[-1] != item:
            out.append(item)
    return out


def run_once(cfg):
    sim = Simulation(cfg)
    frames = list(sim.frames())
    accuracy = sim.metrics.accuracy
    same_sequence = squeeze(f.predicted for f in frames) == squeeze(f.truth for f in frames)
    return accuracy, same_sequence


def seeds(n=100):
    print(f"\n1. Accuracy over {n} seeds (per reading, and whether the sequence of states is right)")
    for name, path in SCENARIOS.items():
        base = load_config(path) if path else load_config()
        accs, same = [], 0
        for seed in range(n):
            acc, ok = run_once(dataclasses.replace(base, seed=seed))
            accs.append(acc)
            same += ok
        print(f"   {name:22s} mean {100 * statistics.mean(accs):.2f}%   worst {100 * min(accs):.2f}%   "
              f"same sequence as the truth: {same}/{n}")


def dwell(n=100):
    print(f"\n2. A sensor stands 0.15 m outside region A for 20 samples, then walks 40 m away ({n} runs)")
    noise_std, dt = 0.05, 0.1
    limit = 3.0 * dt + 2 * 3.0 * noise_std
    readings = [5.0, 3.0, 1.5, 0.5, 0.3]
    readings += [0.15] * 20
    readings += [0.15 + 0.14 * i for i in range(1, 286)]
    for label, depth in (("without depth check", None), ("with depth check", 8.0)):
        wrong = 0
        for seed in range(n):
            rng = random.Random(seed)
            current = [0.0]
            clf = PresenceClassifier(
                lambda c=current: c[0], lambda: 50.0,
                ClassifierConfig(limit, Presence.OUTSIDE, max_depth_a=depth),
            )
            for d in readings:
                current[0] = max(0.0, d + rng.gauss(0.0, noise_std))
                clf.update()
            wrong += clf.state != Presence.OUTSIDE
        print(f"   {label:20s} wrong at the end: {wrong}/{n}")


def noise(n=30):
    print(f"\n3. Noise sweep, default scenario, {n} seeds each (runs with the right sequence of states)")
    base = load_config()
    for sigma in (0.2, 0.5, 1.0, 2.0):
        try:
            ok = sum(run_once(dataclasses.replace(base, noise_std=sigma, seed=s))[1] for s in range(n))
            print(f"   noise {sigma} m: {ok}/{n}")
        except ValueError as exc:
            print(f"   noise {sigma} m: configuration rejected ({exc})")


if __name__ == "__main__":
    experiments = {"seeds": seeds, "dwell": dwell, "noise": noise}
    for name in sys.argv[1:] or list(experiments):
        experiments[name]()

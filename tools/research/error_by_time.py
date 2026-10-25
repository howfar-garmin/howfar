#!/usr/bin/env python3
"""How does the field's error grow with the time left to the checkpoint?

    python tools/research/error_by_time.py --activities FOLDER

Replays the field with full race prep (past races, race-day corrections), with the course
profile ("P") and without it ("~"), on the four races of benchmark.py and on the activities of
at least --min-km with checkpoints where the runner stopped (see benchmark_quiet.py). For each
band of actual moving time left it prints the typical error (median) and the error 4 times out
of 5 stay within (80th percentile), in minutes and as a share of the time left: what a "±" on
the watch could honestly say.
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import benchmark as B  # noqa: E402
import benchmark_activities as BA  # noqa: E402
import benchmark_quiet as Q  # noqa: E402
import predictors as P  # noqa: E402
import scenario as S  # noqa: E402
from wpeta import model as M  # noqa: E402
from wpeta.model import Layer  # noqa: E402

BANDS = [(0, 10), (10, 20), (20, 40), (40, 60), (60, 90), (90, 120), (120, 180), (180, 600)]


def errors(race, past, first_wp=None):
    """(minutes left, error in minutes) for every prediction, with and without the profile."""
    out = {}
    for ahead in (True, False):
        rows = S.run(race, P.HowFar(past=past, raceday=True), trail_ahead=ahead, first_wp=first_wp)
        out["P" if ahead else "~"] = [(am / 60, (eta - am) / 60) for t, k, dn, eta, act, am in rows]
    return out


def race_job(key):
    return errors(B.race(key), B.past_layer(key))


def activity_job(args):
    path, past = args
    race = Q.stop_race(Path(path).name, BA.load(Path(path)))[0]
    layer = None
    if past:
        layer = Layer()
        layer.paces, layer.weights = list(past[0]), list(past[1])
    return errors(race, layer, first_wp=1)


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else float("nan")


def table(title, results):
    print(f"\n{title}")
    print(f"{'time left':<12} {'n':>6} {'P typical':>10} {'P 4 in 5':>9} {'P share':>8}   {'~ typical':>9} {'~ 4 in 5':>9} {'~ share':>8}")
    for lo, hi in BANDS:
        line = f"{lo:>4}-{hi:<4} min "
        for mark in ("P", "~"):
            e = [(left, err) for r in results for left, err in r[mark] if lo <= left < hi]
            ab = [abs(err) for _, err in e]
            share = [abs(err) / left for left, err in e if left > 1]
            if mark == "P":
                line += f"{len(e):>6} "
            line += f"{pct(ab, 0.5):9.1f}m {pct(ab, 0.8):8.1f}m {pct(share, 0.8) * 100:7.0f}%   "
        print(line)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--activities")
    ap.add_argument("--min-km", type=float, default=50)
    ap.add_argument("--jobs", type=int, default=8)
    args = ap.parse_args()
    with ProcessPoolExecutor(args.jobs) as ex:
        table("four races", list(ex.map(race_job, B.RACES)))
        if args.activities:
            acts = []
            for f in sorted(Path(args.activities).glob("*.gpx")):
                pts = BA.load(f)
                if len(pts) < 100 or pts[-1].dist < args.min_km * 1000:
                    continue
                acts.append((BA.start_time(f), f, P.layer_from_obs(P.past_observations(pts))))
            acts.sort(key=lambda a: a[0])
            todo, running = [], Layer()
            for _, f, layer in acts:
                todo.append((str(f), (list(running.paces), list(running.weights)) if running.total_weight() else None))
                running.merge_from(layer, M.STORED_DECAY, M.STORED_CAP)
            table(f"{len(todo)} activities of {args.min_km:.0f} km or more, checkpoints where the runner stopped",
                  list(ex.map(activity_job, todo, chunksize=2)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

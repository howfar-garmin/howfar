#!/usr/bin/env python3
"""Is the field's prediction too long (or too short) right after a checkpoint, and would
taking a fixed share off it help?

    python tools/research/bias_after_checkpoint.py --activities FOLDER

Full race prep (past races, trail ahead, race-day corrections) on the four races of
benchmark.py and on the activities of at least --min-km with checkpoints where the runner
stopped. Prints the signed error by minutes since the last checkpoint (positive: the watch
said longer than it took), then scores taking CUT% off the prediction during the first
WINDOW minutes after each checkpoint.
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

SINCE = [(0, 5), (5, 10), (10, 15), (15, 30), (30, 60), (60, 999)]
CUTS = [(0, 0), (5, 15), (10, 15), (15, 15), (10, 30), (5, 999), (10, 999)]  # (% off, for minutes after a checkpoint)


def rows_with_since(race, past, first_wp=None):
    rows = S.run(race, P.HowFar(past=past, raceday=True), trail_ahead=True, first_wp=first_wp)
    out = []
    for t, k, dn, eta, act, am in rows:
        if k >= 1 and (k - 1) in race.arrival and k - 1 >= 1:  # not the start: that's a different problem
            out.append(((t - race.arrival[k - 1][0]) / 60, eta, am))
    return out


def race_job(key):
    return rows_with_since(B.race(key), B.past_layer(key))


def activity_job(args):
    path, past = args
    race = Q.stop_race(Path(path).name, BA.load(Path(path)))[0]
    layer = None
    if past:
        layer = Layer()
        layer.paces, layer.weights = list(past[0]), list(past[1])
    return rows_with_since(race, layer, first_wp=1)


def report(title, per_run):
    allrows = [r for rows in per_run for r in rows]
    print(f"\n{title}: {len(per_run)} runs, {len(allrows)} predictions (after the first checkpoint)")
    print(f"{'min since cp':<13} {'n':>6} {'mean err':>9} {'median %':>9} {'too long':>9}")
    for lo, hi in SINCE:
        e = [(eta - am, (eta - am) / am) for since, eta, am in allrows if lo <= since < hi and am > 60]
        if not e:
            continue
        rel = sorted(x[1] for x in e)
        print(f"{lo:>4}-{hi:<7}  {len(e):>6} {sum(x[0] for x in e) / len(e) / 60:+8.1f}m {rel[len(rel) // 2] * 100:+8.0f}% {sum(x[1] > 0 for x in e) / len(e) * 100:8.0f}%")
    print(f"{'take off':<20} {'1h MAE':>8} {'first 15 min':>13}")
    for cut, window in CUTS:
        hour, early = [], []
        for since, eta, am in allrows:
            e = eta * (1 - cut / 100) if since < window else eta
            if am <= 3600:
                hour.append(abs(e - am) / 60)
            if since < 15:
                early.append(abs(e - am) / 60)
        name = "nothing" if cut == 0 else f"{cut}% for {'the whole leg' if window > 600 else f'{window} min'}"
        print(f"{name:<20} {sum(hour) / len(hour):7.2f}m {sum(early) / len(early):12.2f}m")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--activities")
    ap.add_argument("--min-km", type=float, default=50)
    ap.add_argument("--jobs", type=int, default=8)
    args = ap.parse_args()
    with ProcessPoolExecutor(args.jobs) as ex:
        report("four races", list(ex.map(race_job, B.RACES)))
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
            report(f"activities of {args.min_km:.0f} km or more, checkpoints where the runner stopped",
                   list(ex.map(activity_job, todo, chunksize=2)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

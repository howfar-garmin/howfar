#!/usr/bin/env python3
"""Does it help to ignore the stretch around each checkpoint when learning how today is going?

    python tools/research/benchmark_quiet.py [--activities FOLDER] --out quiet.json

Around a checkpoint you often walk slowly through an aid station without stopping, which the
field takes as "slow today": its form factor and recent-slowdown factor drop and stretch the
whole next leg. Here the field (full race prep: past races, trail ahead, race-day corrections)
is replayed with observations within R metres of a checkpoint (before or after it) left out of:

- "form":  the form and recent-slowdown factors only
- "all":   those and the pace learned during the race

Races: the four of benchmark.py with their real checkpoints. Activities: those of at least
--min-km with virtual checkpoints (every 10 or 20 km, no aid stations), as a check that it
does no harm where nothing happens at the checkpoints; with --stops, the checkpoints are where
the runner stopped for at least STOP_S seconds instead (aid stations, refuges, fountains), at
least STOP_SEP apart, with a filler point in gaps longer than GAP. "after cp" is the error
during the first 15 minutes after each checkpoint.
"""

from __future__ import annotations

import argparse
import bisect
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import benchmark as B  # noqa: E402
import benchmark_activities as BA  # noqa: E402
import predictors as P  # noqa: E402
import scenario as S  # noqa: E402
from wpeta import model as M  # noqa: E402
from wpeta.model import Layer  # noqa: E402

VARIANTS = [("base", 0, None), ("form 200 m", 200, "form"), ("form 300 m", 300, "form"), ("form 500 m", 500, "form"),
            ("all 300 m", 300, "all")]


class Quiet(P.HowFar):
    """HowFar that leaves out observations within `radius` metres of a checkpoint."""

    def __init__(self, cps: list[float], radius: float, what: str | None, **kw) -> None:
        super().__init__(**kw)
        self.cps, self.radius, self.what = cps, radius, what

    def _near(self, dist: float) -> bool:
        i = bisect.bisect_left(self.cps, dist)
        return any(0 <= j < len(self.cps) and abs(self.cps[j] - dist) < self.radius for j in (i - 1, i))

    def observe(self, t, dist, alt):
        if not self.what or not self._near(dist):
            return super().observe(t, dist, alt)
        if not self.tracker.update(t, dist, alt):
            return
        if self.what == "form":  # still learn the pace, just not how today is going
            g, v = self.tracker.last_grade, self.tracker.last_speed
            M.RUN_DECAY = self._decay if self.raceday else 1.0
            self.model.observe(g, v)
            M.RUN_DECAY = self._decay


def score(race, rows) -> dict:
    out = S.score(rows)
    after = [abs(eta - am) / 60 for t, k, dn, eta, act, am in rows
             if k >= 1 and (k - 1) in race.arrival and t - race.arrival[k - 1][0] <= 900]
    out["mae_after"] = sum(after) / len(after) if after else float("nan")
    return out


def run_race(race, past: Layer | None, first_wp=None) -> dict:
    cps = [w.act_dist for w in race.waypoints]
    res = {}
    for name, radius, what in VARIANTS:
        pr = Quiet(cps, radius, what, past=past, raceday=True)
        rows = S.run(race, pr, trail_ahead=True, first_wp=first_wp)
        res[name] = score(race, rows) if rows else None
    return res


def race_job(key):
    return key, run_race(B.race(key), B.past_layer(key))


def stop_race(name, pts):
    return S.race_from_stops(name, pts)


def activity_job(args):
    path, past, by_stops = args
    pts = BA.load(Path(path))
    race = stop_race(Path(path).name, pts)[0] if by_stops else BA.as_race(Path(path).name, pts)
    layer = None
    if past:
        layer = Layer()
        layer.paces, layer.weights = list(past[0]), list(past[1])
    return Path(path).name, run_race(race, layer, first_wp=1)


def summarize(title, results):
    rs = [r for r in results.values() if all(r.get(v[0]) for v in VARIANTS)]
    print(f"\n{title}: {len(rs)}")
    print(f"{'variant':<12} {'1h MAE':>8} {'within 5':>9} {'2 km out':>9} {'after cp':>9}")
    for name, _, _ in VARIANTS:
        m = lambda k: sum(r[name][k] for r in rs if r[name][k] == r[name][k]) / max(1, sum(1 for r in rs if r[name][k] == r[name][k]))
        print(f"{name:<12} {m('mae_hour'):7.2f}m {m('within5_hour') * 100:8.0f}% {m('mae_2000'):8.2f}m {m('mae_after'):8.2f}m")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--activities")
    ap.add_argument("--min-km", type=float, default=25)
    ap.add_argument("--stops", action="store_true", help="checkpoints where the runner stopped")
    ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", type=int, default=8)
    args = ap.parse_args()

    out = {}
    with ProcessPoolExecutor(args.jobs) as ex:
        races = {} if args.stops else dict(ex.map(race_job, B.RACES))
        for key, r in races.items():
            print(key, "  ".join(f"{n}: {r[n]['mae_hour']:.2f}/{r[n]['mae_after']:.1f}" for n, _, _ in VARIANTS))
        if races:
            summarize("races (1h MAE / after cp per race above)", races)
        out["races"] = races
        if args.activities:
            files = sorted(Path(args.activities).glob("*.gpx"))
            acts = []
            for f in files:
                pts = BA.load(f)
                if len(pts) < 100 or pts[-1].dist < args.min_km * 1000:
                    continue
                acts.append((BA.start_time(f), f, P.layer_from_obs(P.past_observations(pts))))
            acts.sort(key=lambda a: a[0])
            todo, running = [], Layer()
            for _, f, layer in acts:
                todo.append((str(f), (list(running.paces), list(running.weights)) if running.total_weight() else None, args.stops))
                running.merge_from(layer, M.STORED_DECAY, M.STORED_CAP)
            res = {}
            for n, (name, r) in enumerate(ex.map(activity_job, todo, chunksize=2), 1):
                res[name] = r
                if n % 20 == 0:
                    print(f"{n}/{len(todo)}", flush=True)
            summarize("activities", res)
            out["activities"] = res
    json.dump(out, open(args.out, "w"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Would carrying today's trend forward (getting slower, or faster) improve the field?

    python tools/research/benchmark_trend.py [--activities FOLDER] --out trend.json

Every observation (25 m) compares how long you took with what a fixed reference expected on
that slope (the pace from past races, or the default curve without them); its log is today's
performance. A straight line through the last WINDOW minutes of moving time gives the trend:
how much faster or slower per hour you're getting. The prediction for the next checkpoint
then assumes the trend goes on: over a leg of T hours your speed is, on average, the current
one times exp(slope * T / 2), capped at CAP either way. Nothing changes until the window holds
at least MIN_SPAN minutes.

Full race prep (past races, trail ahead, race-day corrections) on the four races of
benchmark.py, the activities of at least 50 km with checkpoints where the runner stopped
(benchmark_quiet.py) and all activities of at least 25 km with virtual checkpoints.
"""

from __future__ import annotations

import argparse
import json
import math
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

# name, window (min of moving time), cap on the leg's change, which way it may act, metres
# after each checkpoint left out of the trend (you're often fresher and faster leaving one)
VARIANTS = [
    ("base", 0, 0.0, None, 0),
    ("trend 60 min, ±10%", 60, 0.10, "both", 0),
    ("trend 90 min, ±10%", 90, 0.10, "both", 0),
    ("trend 120 min, ±10%", 120, 0.10, "both", 0),
    ("trend 90 min, ±20%", 90, 0.20, "both", 0),
    ("slowing only 90 min, ±10%", 90, 0.10, "slower", 0),
    ("90 min, ±10%, skip 1 km", 90, 0.10, "both", 1000),
    ("90 min, ±10%, skip 2 km", 90, 0.10, "both", 2000),
    ("120 min, ±10%, skip 2 km", 120, 0.10, "both", 2000),
]
MIN_SPAN = 30.0  # minutes the window must cover before a trend is used


class Trend(P.HowFar):
    def __init__(self, window: float, cap: float, way: str | None, skip: float, cps: list[float], **kw) -> None:
        super().__init__(**kw)
        self.window, self.cap, self.way = window * 60, cap, way
        self.skip, self.cps = skip, cps
        self.moving = 0.0
        self.obs: list[tuple[float, float]] = []  # (moving s, log(expected / actual time))
        self.slope = 0.0  # per second

    def observe(self, t, dist, alt):
        if not self.tracker.update(t, dist, alt):
            return
        g, v, w = self.tracker.last_grade, self.tracker.last_speed, self.tracker.last_dist
        if self.way:
            act = w / v
            self.moving += act
            if not any(0 <= dist - c < self.skip for c in self.cps):
                self.obs.append((self.moving, math.log((w / self.model.predict_prior(g)) / act)))
            while self.obs and self.obs[0][0] < self.moving - self.window:
                self.obs.pop(0)
            self.slope = self._fit()
        if self.raceday:
            self.est.observe(g, v, w)
        M.RUN_DECAY = self._decay if self.raceday else 1.0
        self.model.observe(g, v)
        M.RUN_DECAY = self._decay

    def _fit(self) -> float:
        if len(self.obs) < 20 or self.obs[-1][0] - self.obs[0][0] < MIN_SPAN * 60:
            return 0.0
        n = len(self.obs)
        mx = sum(x for x, _ in self.obs) / n
        my = sum(y for _, y in self.obs) / n
        sxx = sum((x - mx) ** 2 for x, _ in self.obs)
        return sum((x - mx) * (y - my) for x, y in self.obs) / sxx if sxx else 0.0

    def predict(self, ctx):
        if self.raceday:
            self.scale.update(ctx.dist, ctx.dist_dest)
        s = self.scale.ratio if self.raceday else 1.0
        fatigue = self.est.fatigue if self.raceday else 1.0
        raw = max(1.0, sum(length * s / (self.model.predict(g / s) * fatigue) for length, g in ctx.chunks))
        if self.way:
            slope = self.slope if self.way == "both" else min(0.0, self.slope)
            change = math.exp(slope * raw / 2)  # average speed over the leg vs now
            change = min(1 + self.cap, max(1 - self.cap, change))
            raw /= change
        if ctx.wp_index != self._wp or ctx.dist_next > self._last_dn + 50:
            self._smooth = None
        self._wp, self._last_dn = ctx.wp_index, ctx.dist_next
        v = ctx.dist_next / raw
        self._smooth = v if self._smooth is None else self._smooth + (v - self._smooth) * P.SMOOTHING
        return ctx.dist_next / self._smooth


def run(race, past, first_wp=None):
    out = {}
    cps = [w.act_dist for w in race.waypoints]
    for name, window, cap, way, skip in VARIANTS:
        rows = S.run(race, Trend(window, cap, way, skip, cps, past=past, raceday=True), trail_ahead=True, first_wp=first_wp)
        out[name] = S.score(rows) if rows else None
    return out


def layer_of(past):
    if not past:
        return None
    layer = Layer()
    layer.paces, layer.weights = list(past[0]), list(past[1])
    return layer


def race_job(key):
    return key, run(B.race(key), B.past_layer(key))


def activity_job(args):
    path, past, stops = args
    pts = BA.load(Path(path))
    race = Q.stop_race(Path(path).name, pts)[0] if stops else BA.as_race(Path(path).name, pts)
    return Path(path).name, run(race, layer_of(past), first_wp=1)


def history(folder, min_km):
    acts = []
    for f in sorted(Path(folder).glob("*.gpx")):
        pts = BA.load(f)
        if len(pts) < 100 or pts[-1].dist < min_km * 1000:
            continue
        acts.append((BA.start_time(f), f, P.layer_from_obs(P.past_observations(pts))))
    acts.sort(key=lambda a: a[0])
    todo, running = [], Layer()
    for _, f, layer in acts:
        todo.append((str(f), (list(running.paces), list(running.weights)) if running.total_weight() else None))
        running.merge_from(layer, M.STORED_DECAY, M.STORED_CAP)
    return todo


def summarize(title, results):
    rs = [r for r in results.values() if all(r.get(v[0]) for v in VARIANTS)]
    print(f"\n{title}: {len(rs)}")
    print(f"{'variant':<28} {'1h MAE':>8} {'within 5':>9} {'2 km out':>9} {'bias':>7}")
    for name, *_ in VARIANTS:
        m = lambda k: sum(r[name][k] for r in rs if r[name][k] == r[name][k]) / max(1, sum(1 for r in rs if r[name][k] == r[name][k]))
        print(f"{name:<28} {m('mae_hour'):7.2f}m {m('within5_hour') * 100:8.0f}% {m('mae_2000'):8.2f}m {m('bias_hour'):+6.2f}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--activities")
    ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", type=int, default=8)
    args = ap.parse_args()
    out = {}
    with ProcessPoolExecutor(args.jobs) as ex:
        out["races"] = dict(ex.map(race_job, B.RACES))
        summarize("four races", out["races"])
        if args.activities:
            long_runs = [(p, past, True) for p, past in history(args.activities, 50)]
            out["long"] = dict(ex.map(activity_job, long_runs, chunksize=2))
            summarize("activities of 50 km or more, checkpoints where the runner stopped", out["long"])
            acts = [(p, past, False) for p, past in history(args.activities, 25)]
            out["all"] = dict(ex.map(activity_job, acts, chunksize=2))
            summarize("activities of 25 km or more, virtual checkpoints", out["all"])
    json.dump(out, open(args.out, "w"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

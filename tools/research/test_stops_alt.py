#!/usr/bin/env python3
"""Stops that GPS drift hides: standing at an aid station, the watch's distance can creep on by
10-20 m every 30 s, too much for "less than 15 m in a minute". The altitude, though, stays put
(a slow steep climb keeps climbing). Does also calling it a stop when the distance moved less
than SLOW m in a minute and the altitude stayed within ALT m help?

    python tools/research/test_stops_alt.py [--out results.json]

The six races of benchmark.py, scored as on the site (times rounded as the watch shows them):
the usual estimate, HowFar without and with the course profile, and with past runs too.

Each field rule is scored against two yardsticks for the stops left out of "what it really took":
- old: less than 30 m between 60 s before and 60 s after
- alt: the same, or less than 90 m with the altitude within 1.5 m over those two minutes
The new yardstick changes the score of every line (the usual estimate too), so compare lines
within a yardstick.

Result (October 2026): the field rule changes the average error by a few seconds at most
(3.42 -> 3.39 min with the profile, 5.01 -> 5.03 without), so the watch keeps its rule; the alt
yardstick finds the stops GPS drift hides (TOR330 life bases: 23 -> 32 h) and became replay.py's.
"""

from __future__ import annotations

import argparse
import bisect
import copy
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import benchmark as B  # noqa: E402
import predictors as P  # noqa: E402
import replay as R  # noqa: E402
import scenario as S  # noqa: E402
from wpeta import model as M  # noqa: E402
from wpeta.field import shown_seconds  # noqa: E402

# field rule: (SLOW_DIST m in a minute, SLOW_ALT m); (0, 0) is today's field
VARIANTS = {
    "today": (0.0, 0.0),
    "30m 1m": (30.0, 1.0),
    "45m 1m": (45.0, 1.0),
    "45m 2m": (45.0, 2.0),
    "60m 1m": (60.0, 1.0),
    "60m 2m": (60.0, 2.0),
    "90m 1m": (90.0, 1.0),
}
CONFIGS = {
    "average pace": B.AVERAGE,
    "no profile": dict(past=False, ahead=False, raceday=True),
    "profile": dict(past=False, ahead=True, raceday=True),
    "profile+past": dict(past=True, ahead=True, raceday=True),
}


def stops_with(points, slow: bool) -> list[float]:
    """replay.stop_time_index, with or without its altitude rule."""
    keep = R.SLOW_DIST
    R.SLOW_DIST = keep if slow else 0.0
    try:
        return R.stop_time_index(points)
    finally:
        R.SLOW_DIST = keep


class SlowStops(M.GradeTracker):
    """The field's tracker, also stopped when it moved less than SLOW_DIST in STOP_WINDOW with the
    altitude within SLOW_ALT."""

    SLOW_DIST, SLOW_ALT = 0.0, 0.0

    def reset(self) -> None:
        super().reset()
        self._alts: list[tuple[float, float]] = []

    def update(self, time_s, dist, alt):
        self._alts.append((time_s, alt))
        while self._alts[0][0] < time_s - self.STOP_WINDOW:
            self._alts.pop(0)
        return super().update(time_s, dist, alt)

    def is_moving(self, time_s, dist):
        if not super().is_moving(time_s, dist):
            return False
        for k in range(1, self._scount):
            idx = (self._shead - 1 - k + self.STOP_SIZE) % self.STOP_SIZE
            if self._st[idx] <= time_s - self.STOP_WINDOW:
                if dist - self._sd[idx] >= self.SLOW_DIST:
                    return True
                alts = [a for _, a in self._alts]
                return max(alts) - min(alts) >= self.SLOW_ALT
        return True


def with_stops(race, stops):
    r = copy.copy(race)
    r.stops = stops
    times = [p.t for p in race.points]
    r.arrival = {k: (t, stops[bisect.bisect_left(times, t)]) for k, (t, _) in race.arrival.items()}
    return r


def job(args):
    key, variant, yard = args
    SlowStops.SLOW_DIST, SlowStops.SLOW_ALT = VARIANTS[variant]
    race = B.race(key)
    race = with_stops(race, stops_with(race.points, yard == "alt"))
    out = {}
    for cid, o in CONFIGS.items():
        pred = B.make(o, key)
        if isinstance(pred, P.HowFar):  # the usual estimate keeps its simple clock
            pred.tracker = SlowStops()
        rows = S.run(race, pred, trail_ahead=o["ahead"])
        rows = [(t, k, dn, shown_seconds(eta), act, am) for t, k, dn, eta, act, am in rows]
        out[cid] = S.score(rows)
    return key, variant, yard, out


def stop_minutes(key):
    race = B.race(key)
    return key, stops_with(race.points, False)[-1] / 60, stops_with(race.points, True)[-1] / 60


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out")
    args = ap.parse_args()

    todo = [(k, v, y) for y in ("old", "alt") for v in VARIANTS for k in B.RACES]
    res: dict = {}
    with ProcessPoolExecutor(8) as ex:
        for key, mins_old, mins_alt in ex.map(stop_minutes, B.RACES):
            print(f"{key:<4} stopped: {mins_old:5.1f} min (old yardstick), {mins_alt:5.1f} min (alt)")
        for key, v, y, sc in ex.map(job, todo):
            res.setdefault(y, {}).setdefault(v, {})[key] = sc
    if args.out:
        json.dump(res, open(args.out, "w"))

    races = list(B.RACES)
    for y in ("old", "alt"):
        print(f"\n=== yardstick: {y} (average over the six races; per race: average minutes off)")
        for cid in CONFIGS:
            print(f"\n{cid}")
            for v in VARIANTS:
                s = [res[y][v][k][cid] for k in races]
                avg = lambda m: sum(x[m] for x in s) / len(s)  # noqa: E731
                per = "  ".join(f"{k} {x['mae_hour']:.2f}" for k, x in zip(races, s))
                print(f"  {v:<7} {avg('mae_hour'):5.2f} min  <5 {avg('within5_hour') * 100:3.0f}%  "
                      f"<15 {avg('within15_hour') * 100:3.0f}%  2km {avg('mae_2000'):4.2f}  bias {avg('bias_hour'):+5.2f}   {per}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

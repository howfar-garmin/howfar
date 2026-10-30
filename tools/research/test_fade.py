#!/usr/bin/env python3
"""This run's observations fade (RUN_DECAY 0.995 per observation, every slope at once, ~3.5 km
half-life), so after 18 km of climbing the fast early descents of TORX 2026 section 1 are gone
and two slow, technical ones before Lac du Fond set the pace downhill: the more runnable descent
to Planaval came out 16 min too long. Does fading descents more slowly help?

    python tools/research/test_fade.py

Variants:
- all D: every slope fades by D per observation (today's field: 0.995)
- down D: descents (grade < DOWN_FROM) fade by D, the rest by 0.995
- own D: a slope fades only when it is observed again, by D each time

The six races of benchmark.py, scored as on the site (times rounded as the watch shows them),
plus the error at every moment whatever the time left ("all") and, on section 1, the first 2 km
after Lac du Fond.

Result (October 2026): no. With the profile, today's fading is best on average (the hour before
2.90 min, 2 km before 2.81); every variant is worse (2.97-3.41, 3.02-3.61), and the first 2 km
after Lac du Fond get only a little closer (10.3 -> 7.7 min at best, descents never fading),
while the rest of section 1 gets worse (1.79 -> 2.2-2.8): later descents are usually slower, and
the recent ones say so. The field keeps RUN_DECAY 0.995 on every slope.
"""

from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import benchmark as B  # noqa: E402
import scenario as S  # noqa: E402
from wpeta import model as M  # noqa: E402
from wpeta.field import shown_seconds  # noqa: E402

DOWN_FROM = -3.0
# (kind, decay); ("all", 0.995) is today's field
VARIANTS = {
    "today": ("all", 0.995),
    "all 0.997": ("all", 0.997),
    "all 0.998": ("all", 0.998),
    "all 0.999": ("all", 0.999),
    "down 0.997": ("down", 0.997),
    "down 0.998": ("down", 0.998),
    "down 0.999": ("down", 0.999),
    "down 1": ("down", 1.0),
    "own 0.95": ("own", 0.95),
    "own 0.98": ("own", 0.98),
    "own 0.99": ("own", 0.99),
}
CONFIGS = {
    "no profile": dict(past=False, ahead=False, raceday=True),
    "profile": dict(past=False, ahead=True, raceday=True),
    "profile+past": dict(past=True, ahead=True, raceday=True),
}


def faded_observe(kind: str, decay: float):
    down_last = M.bin_index(DOWN_FROM)  # bins up to here are descents

    def observe(self, grade_pct: float, speed: float) -> None:
        i_new = M.bin_index(grade_pct)
        for i in range(M.NUM_BINS):
            if kind == "all":
                self.run.weights[i] *= decay
            elif kind == "down":
                self.run.weights[i] *= decay if i < down_last else M.RUN_DECAY
            elif i == i_new:
                self.run.weights[i] *= decay
        self.run.add(i_new, speed, 1.0)
        self.run_total.add(i_new, speed, 1.0)
        self._curve = None

    return observe


def job(args):
    key, variant = args
    M.SpeedGradeModel.observe = faded_observe(*VARIANTS[variant])
    race = B.race(key)
    out = {}
    for cid, o in CONFIGS.items():
        rows = S.run(race, B.make(o, key), trail_ahead=o["ahead"])
        rows = [(t, k, dn, shown_seconds(eta), act, am) for t, k, dn, eta, act, am in rows]
        sc = S.score(rows)
        sc["mae_all"] = sum(abs(eta - am) for _, _, _, eta, _, am in rows) / len(rows) / 60
        if key == "S1":
            k = next(i for i, w in enumerate(race.waypoints) if w.name == "Planaval")
            leg = race.waypoints[k].course_dist - race.waypoints[k - 1].course_dist
            near = [(eta - am) / 60 for _, kk, dn, eta, _, am in rows if kk == k and dn > leg - 2000]
            sc["lac"] = sum(abs(e) for e in near) / len(near)
        out[cid] = sc
    return key, variant, out


def main() -> int:
    todo = [(k, v) for v in VARIANTS for k in B.RACES]
    res: dict = {}
    with ProcessPoolExecutor(8) as ex:
        for key, v, sc in ex.map(job, todo):
            res.setdefault(v, {})[key] = sc
    races = list(B.RACES)
    for cid in CONFIGS:
        print(f"\n{cid}  (average over the six races; per race: 1 h error)")
        for v in VARIANTS:
            s = [res[v][k][cid] for k in races]
            avg = lambda m: sum(x[m] for x in s) / len(s)  # noqa: E731
            per = "  ".join(f"{k} {x['mae_hour']:.2f}" for k, x in zip(races, s))
            print(f"  {v:<10} 1h {avg('mae_hour'):5.2f}  <5 {avg('within5_hour') * 100:3.0f}%  2km {avg('mae_2000'):4.2f}  "
                  f"all {avg('mae_all'):5.2f}  Lac du Fond {res[v]['S1'][cid]['lac']:5.1f}   {per}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

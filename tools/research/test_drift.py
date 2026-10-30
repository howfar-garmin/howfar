#!/usr/bin/env python3
"""Standing at an aid station, GPS drift can move the watch's distance on by 20-25 m a minute,
more than the field's "less than 15 m in a minute" stop. The field then learns those minutes as
very slow walking: at La Thuile (TORX 2026 section 1) its flat pace fell from 1.72 to 1.23 m/s
and the next checkpoint, 2.5 h away, came out 17 min too long. Does skipping observations slower
than DRIFT_SPEED with the altitude within DRIFT_ALT (over the observation's 60 m) help?

    python tools/research/test_drift.py

The six races of benchmark.py, scored as on the site (times rounded as the watch shows them),
plus the error at every moment whatever the time left ("all") and, on section 1, the first 2 km
after La Thuile.

Result (October 2026): 1.0 m/s and 1 m, with the profile: La Thuile 11.7 -> 6.3 min, all 6.80 ->
6.72, 2 km before 2.88 -> 2.81, the hour before 2.92 -> 2.90; without it unchanged. The field
uses it since 0.6.1 (GradeTracker.DRIFT_SPEED, DRIFT_ALT); "off" here turns it off.
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

# (DRIFT_SPEED m/s, DRIFT_ALT m); (0, 0) is the field without the rule
VARIANTS = {
    "off": (0.0, 0.0),
    "0.6 1.5": (0.6, 1.5),
    "0.8 1.5": (0.8, 1.5),
    "0.9 1.5": (0.9, 1.5),
    "1.0 1.5": (1.0, 1.5),
    "1.1 1.5": (1.1, 1.5),
    "1.2 1.5": (1.2, 1.5),
    "1.0 1": (1.0, 1.0),
    "1.0 2.5": (1.0, 2.5),
}
CONFIGS = {
    "no profile": dict(past=False, ahead=False, raceday=True),
    "profile": dict(past=False, ahead=True, raceday=True),
    "profile+past": dict(past=True, ahead=True, raceday=True),
}


def job(args):
    key, variant = args
    M.GradeTracker.DRIFT_SPEED, M.GradeTracker.DRIFT_ALT = VARIANTS[variant]
    race = B.race(key)
    out = {}
    for cid, o in CONFIGS.items():
        rows = S.run(race, B.make(o, key), trail_ahead=o["ahead"])
        rows = [(t, k, dn, shown_seconds(eta), act, am) for t, k, dn, eta, act, am in rows]
        sc = S.score(rows)
        sc["mae_all"] = sum(abs(eta - am) for _, _, _, eta, _, am in rows) / len(rows) / 60
        if key == "S1":
            k = next(i for i, w in enumerate(race.waypoints) if w.name == "Rif. Deffeyes")
            leg = race.waypoints[k].course_dist - race.waypoints[k - 1].course_dist
            near = [(eta - am) / 60 for _, kk, dn, eta, _, am in rows if kk == k and dn > leg - 2000]
            sc["thuile"] = sum(abs(e) for e in near) / len(near)
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
            print(f"  {v:<8} 1h {avg('mae_hour'):5.2f}  <5 {avg('within5_hour') * 100:3.0f}%  2km {avg('mae_2000'):4.2f}  "
                  f"all {avg('mae_all'):5.2f}  La Thuile {res[v]['S1'][cid]['thuile']:5.1f}   {per}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

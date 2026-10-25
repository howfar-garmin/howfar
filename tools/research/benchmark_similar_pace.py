#!/usr/bin/env python3
"""Full race prep with the pace made the way a runner would: from their own earlier activities
of a similar distance, rather than from the other test races.

    python tools/research/benchmark_similar_pace.py FOLDER

For each race of benchmark.py, the pasted pace is made from the activities in FOLDER recorded
before it (at least 12 hours earlier) whose distance is within ±TOL of the race's, the COUNT
most recent ones, merged as the race prep page merges the files you pick. Earlier editions of
the same race count. Three versions are compared: course profile only, full race prep with this
pace, and full race prep with the pace from the other test races (benchmark.py's way).
"""

from __future__ import annotations

import re
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import benchmark as B  # noqa: E402
import benchmark_activities as BA  # noqa: E402
import predictors as P  # noqa: E402
import scenario as S  # noqa: E402
from wpeta.field import shown_seconds  # noqa: E402
from wpeta.model import Layer  # noqa: E402

TOL = 0.3
COUNT = 5
BUCKETS = [(0, 0.5), (0.5, 1), (1, 2), (2, 4), (4, 8), (8, 999)]


def started(path: Path) -> datetime:
    head = path.read_text(errors="ignore")[:400000]
    m = re.search(r"<trkpt[^>]*>.*?<time>([^<]+)</time>", head, re.S)
    return datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))


def similar_pace(key, acts):
    race = B.race(key)
    km = race.points[-1].dist / 1000
    when = started(Path(B.RACES[key][1]))
    earlier = [a for a in acts if (when - a[0]).total_seconds() > 12 * 3600]
    picked = [a for a in earlier if abs(a[1] - km) <= TOL * km][-COUNT:]
    layer = Layer()
    for _, _, name, lay in picked:
        layer.merge_from(lay, 1.0, float("inf"))
    return layer, [(n, round(k)) for _, k, n, _ in picked]


def job(args):
    key, layer = args
    race = B.race(key)
    t0 = race.points[0].t
    out = {}
    for name, past in (("profile only", None), ("full, similar runs", layer), ("full, other test races", B.past_layer(key))):
        rows = S.run(race, P.HowFar(past=past, raceday=True), trail_ahead=True)
        out[name] = [((t - t0) / 3600, abs(shown_seconds(eta) - am) / 60) for t, k, dn, eta, act, am in rows if am <= 3600]
    return key, out


def main() -> int:
    folder = Path(sys.argv[1])
    acts = []
    for f in sorted(folder.glob("*.gpx")):
        pts = BA.load(f)
        if len(pts) < 100 or pts[-1].dist < 10000:
            continue
        acts.append((started(f), pts[-1].dist / 1000, f.name, P.layer_from_obs(P.past_observations(pts))))
    acts.sort(key=lambda a: a[0])
    todo = []
    for key in B.RACES:
        layer, picked = similar_pace(key, acts)
        print(f"{key}: pace from {len(picked)} earlier runs {picked}")
        todo.append((key, layer if picked else None))
    with ProcessPoolExecutor(8) as ex:
        res = dict(ex.map(job, todo))
    names = ["profile only", "full, similar runs", "full, other test races"]
    print(f"\n{'':<26}{'avg':>6} {'≤5 min':>7} {'≤15 min':>8}   per race (avg min)")
    for n in names:
        per = {k: sum(e for _, e in res[k][n]) / len(res[k][n]) for k in res}
        avg = sum(per.values()) / len(per)
        w5 = sum(sum(e <= 5 for _, e in res[k][n]) / len(res[k][n]) for k in res) / len(res)
        w15 = sum(sum(e <= 15 for _, e in res[k][n]) / len(res[k][n]) for k in res) / len(res)
        print(f"{n:<26}{avg:6.2f} {w5 * 100:6.0f}% {w15 * 100:7.0f}%   " + "  ".join(f"{k} {v:.1f}" for k, v in per.items()))
    print(f"\nby hours into the race (avg min, share within 5 min), all races together")
    print(f"{'':<26}" + "".join(f"{f'{a}-{b}h' if b < 999 else f'>{a}h':>14}" for a, b in BUCKETS))
    for n in names:
        line = f"{n:<26}"
        for a, b in BUCKETS:
            es = [e for k in res for h, e in res[k][n] if a <= h < b]
            line += f"{sum(es) / len(es):6.1f} ({sum(e <= 5 for e in es) / len(es) * 100:3.0f}%)" if es else f"{'-':>14}"
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())

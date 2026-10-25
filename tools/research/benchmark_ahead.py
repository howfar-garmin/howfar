#!/usr/bin/env python3
"""How good is the time to the checkpoint after the next, and the one after that?

    python tools/research/benchmark_ahead.py

Replays the races of benchmark.py with HowFar (course profile, race-day corrections, first race:
nothing remembered) and, every EVAL_EVERY seconds, scores the time to the next checkpoint (as the
field shows it, smoothed) and to the 2nd and 3rd ones ahead (the next one's time plus the later
legs at the current model, as the field's bottom lines add them). Stops are left out of the real
time, as for the next checkpoint. Scored as the watch shows it: rounded.
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
from wpeta.field import shown_seconds  # noqa: E402

AHEAD = 3


def job(key):
    race = B.race(key)
    pr = B.make(dict(past=False, ahead=True, raceday=True), key)
    wps = race.waypoints
    first = S.first_scored(wps)
    total = wps[-1].course_dist
    out = [[] for _ in range(AHEAD)]  # (error s, real moving s)
    k, next_eval = 0, 0.0
    for i, p in enumerate(race.points):
        pr.observe(p.t, p.dist, p.alt)
        while k < len(wps) and p.dist >= wps[k].act_dist:
            k += 1
        if k >= len(wps):
            break
        if p.t < next_eval or k < first:
            continue
        next_eval = p.t + S.EVAL_EVERY
        wp, prev = wps[k], wps[k - 1]
        frac = (p.dist - prev.act_dist) / max(1.0, wp.act_dist - prev.act_dist)
        cd = prev.course_dist + frac * (wp.course_dist - prev.course_dist)
        dn = wp.course_dist - cd
        if dn <= 0:
            continue
        ctx = S.Ctx(p.t, p.dist, p.alt, dn, total - cd, race.elev.at(wp.course_dist), S.chunks_ahead(race.elev, cd, wp.course_dist), k)
        eta = pr.predict(ctx)
        s = pr.scale.ratio
        for a in range(AHEAD):
            j = k + a
            if j >= len(wps) or j not in race.arrival or any(m in race.skip for m in range(k, j + 1)):
                break
            if a > 0:
                eta += sum(length * s / (pr.model.predict(g / s) * pr.est.fatigue)
                           for length, g in S.chunks_ahead(race.elev, wps[j - 1].course_dist, wps[j].course_dist))
            t_arr, s_arr = race.arrival[j]
            real = (t_arr - p.t) - (s_arr - race.stops[i])
            out[a].append((shown_seconds(eta) - real, real))
    return key, out


def main() -> int:
    with ProcessPoolExecutor(8) as ex:
        res = dict(ex.map(job, B.RACES))
    print(f"{'':>22} " + " ".join(f"{n:>34}" for n in ("next checkpoint", "the one after", "the one after that")))
    for key, out in list(res.items()) + [("all six", [sum((r[a] for r in res.values()), []) for a in range(AHEAD)])]:
        cells = []
        for rows in out:
            if not rows:
                cells.append(f"{'-':>34}")
                continue
            e = [abs(x) / 60 for x, _ in rows]
            rel = sorted(abs(x) / r for x, r in rows if r > 600)
            hours = sum(r for _, r in rows) / len(rows) / 3600
            cells.append(f"{sum(e) / len(e):5.1f} min {sum(x <= 15 for x in e) / len(e) * 100:3.0f}%≤15 "
                         f"{rel[len(rel) // 2] * 100 if rel else 0:3.0f}% med, {hours:3.1f} h out")
        print(f"{key:>22} " + " ".join(cells))
    return 0


if __name__ == "__main__":
    sys.exit(main())

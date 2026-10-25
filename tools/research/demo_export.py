#!/usr/bin/env python3
"""Writes docs/demo/torx-s1.js: section 1 replayed against the T1 course, with HowFar's prediction
with and without the course profile at every moment, and the usual watch estimate (the distance
left at the average pace so far) to compare, plus the benchmark scores for the site's table.

    python tools/research/benchmark.py --shown --out results.json
    python tools/research/demo_export.py --results results.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import benchmark as B  # noqa: E402
import scenario as S  # noqa: E402
from wpeta.profile import best_profile  # noqa: E402
from wpeta.readers import read_course  # noqa: E402

KEY = "S1"
# minor points in the demo (the rest are main): the big number counts down to the next main
# point, and the full-screen watch shows the next minor one on the way
MINOR = {"Col Passo Alto", "Col de la Crosatie", "Lac Du Fond"}

# id, short label (chart, table), label next to the choice, benchmark options (trail ahead
# decides P/~ on the watch). HowFar's first race: nothing remembered from earlier runs.
CONFIGS = [
    ("average", "Average pace so far", "", B.AVERAGE),
    ("none", "HowFar, no course profile", "Nothing", dict(past=False, ahead=False, raceday=True)),
    ("profile", "HowFar with the course profile", "The course profile", dict(past=False, ahead=True, raceday=True)),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True, help="benchmark.py output")
    ap.add_argument("--out", default=str(B.ROOT / "docs/demo/torx-s1.js"))
    args = ap.parse_args()

    race = B.race(KEY)
    preds = [(cid, o["ahead"], B.make(o, KEY)) for cid, _, _, o in CONFIGS]
    final = preds[-1][2]  # HowFar with the course profile: what the watch has learned

    wps = race.waypoints
    first = S.first_scored(wps)
    total = wps[-1].course_dist
    frames, k, next_eval = [], 0, 0.0
    for i, p in enumerate(race.points):
        for _, _, pr in preds:
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
        elev_next = race.elev.at(wp.course_dist)
        ahead = S.chunks_ahead(race.elev, cd, wp.course_dist)
        avg = [(dn, max(-40.0, min(40.0, (elev_next - p.alt) / dn * 100.0)))]
        etas = []
        for _, use_ahead, pr in preds:
            ctx = S.Ctx(p.t, p.dist, p.alt, dn, total - cd, elev_next, ahead if use_ahead else avg, k)
            etas.append(round(pr.predict(ctx)))
        t_arr, s_arr = race.arrival[k]
        recent_stop = race.stops[i] - (race.stops[i - 60] if i >= 60 else 0) > 30
        # HowFar with the profile, from the next checkpoint on to each later one (unsmoothed, as
        # the field adds them to its countdown)
        s = final.scale.ratio
        legs, t_leg = [], 0.0
        for j in range(k + 1, len(wps)):
            t_leg += sum(length * s / (final.model.predict(g / s) * final.est.fatigue)
                         for length, g in S.chunks_ahead(race.elev, wps[j - 1].course_dist, wps[j].course_dist))
            legs.append(round(t_leg))
        frames.append([round(p.t), round(cd), round(p.alt), k, round(dn), round(t_arr - p.t), round(s_arr - race.stops[i]),
                       int(recent_stop), round(final.scale.ratio, 3),
                       *(round(final.model.predict(g), 3) for g in (0.0, 20.0, -20.0)),
                       round(final.est.fatigue, 3), round(race.stops[i]), *etas, legs])

    act_text = open(B.RACES[KEY][1]).read(20000)
    start = re.search(r"<time>([^<]+)</time>", act_text[act_text.find("<trkpt"):]).group(1)
    cpts, cps = read_course(str(B.RACES[KEY][2]))
    step, profile_str = best_profile(cpts, cps, 4000)
    results = json.load(open(args.results))
    scores = {cid: {r: {m: round(v, 3) for m, v in results[B.label(o)][r]["score"].items()} for r in B.RACES}
              for cid, _, _, o in CONFIGS}

    data = dict(
        start=start,
        configs=[dict(id=c[0], label=c[1], long=c[2], ahead=c[3]["ahead"]) for c in CONFIGS],
        # km: the length of course replayed (the last checkpoint reached, for a DNF)
        races=[dict(key=k, name=B.RACES[k][0], km=round(B.race(k).waypoints[-1].course_dist / 1000, 1)) for k in B.RACES],
        frames=frames,
        profile=[[round(d), round(race.elev.at(d))] for d in range(0, int(race.elev.length) + 1, 100)],
        waypoints=[dict(name=w.name, d=round(w.course_dist), alt=round(race.elev.at(w.course_dist)),
                        arrive=round(race.arrival[j][0]) if j in race.arrival else None,
                        stops=round(race.arrival[j][1]) if j in race.arrival else None,
                        minor=w.name in MINOR) for j, w in enumerate(wps)],
        firstWaypoint=first,
        profileString=profile_str, profileStep=step,
        scores=scores,
    )
    Path(args.out).write_text(
        "// Section 1 of TORX 2026 (Courmayeur to Valgrisenche) replayed against the T1 course.\n"
        "// Generated by tools/research/demo_export.py. frames: [race s, course m, altitude m, next waypoint,\n"
        "// metres to it, actual s to it, of which stopped s, standing still now, distance ratio, learned speed (m/s)\n"
        "// on the flat, up 20% and down 20%, fatigue, stopped s so far,\n"
        "// then one predicted time (s) per entry of configs, then HowFar's (profile) time from the next\n"
        "// waypoint to each later one]\n"
        "window.HOWFAR_DEMO = " + json.dumps(data, separators=(",", ":"), ensure_ascii=False) + ";\n")
    print(len(frames), "frames,", Path(args.out).stat().st_size, "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())

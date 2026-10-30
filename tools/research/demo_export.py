#!/usr/bin/env python3
"""Writes docs/demo/torx-s1.js: section 1 replayed against the T1 course, with HowFar's prediction
with and without the course profile at every moment (and with the profile after five past races),
and the usual watch estimate (the distance left at the average pace so far) to compare, plus the
benchmark scores for the site's table.

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
MINOR = {"Col d'Arp", "Col Passo Alto", "Col de la Crosatie", "Lac Du Fond"}

# id, short label (chart, table), label next to the choice, benchmark options (trail ahead
# decides P/~ on the watch). HowFar's first race: nothing remembered from earlier runs, except
# "past", which remembers the benchmark's other five races (as benchmark.py's past layer).
CONFIGS = [
    ("average", "Average pace so far", "", B.AVERAGE),
    ("none", "HowFar, no course profile", "Nothing", dict(past=False, ahead=False, raceday=True)),
    ("profile", "HowFar with the course profile", "The course profile", dict(past=False, ahead=True, raceday=True)),
    ("past", "HowFar with the profile and past races", "The course profile and five past races", dict(past=True, ahead=True, raceday=True)),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True, help="benchmark.py output")
    ap.add_argument("--out", default=str(B.ROOT / "docs/demo/torx-s1.js"))
    args = ap.parse_args()

    race = B.race(KEY)
    preds = [(cid, o["ahead"], B.make(o, KEY)) for cid, _, _, o in CONFIGS]
    final = next(pr for cid, _, pr in preds if cid == "profile")  # the watch: first race, with the profile
    learned = next(pr for cid, _, pr in preds if cid == "past")  # the watch after five past races

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
            ctx = S.Ctx(p.t, p.dist, p.alt, dn, total - cd, elev_next, ahead if use_ahead else avg, k, use_ahead)
            etas.append(round(pr.predict(ctx)))
        t_arr, s_arr = race.arrival[k]
        recent_stop = race.stops[i] - (race.stops[i - 60] if i >= 60 else 0) > 30
        # HowFar with the profile, from the next checkpoint on to each later one (unsmoothed, as
        # the field adds them to its countdown)
        def legs_of(pr):
            s = pr.scale.ratio
            out, t_leg = [], 0.0
            for j in range(k + 1, len(wps)):
                t_leg += sum(length * s / (pr.model.predict(g / s) * pr.est.fatigue)
                             for length, g in S.chunks_ahead(race.elev, wps[j - 1].course_dist, wps[j].course_dist))
                out.append(round(t_leg))
            return out
        legs = legs_of(final)
        # each prediction's time from the next waypoint on to the next main checkpoint, so the
        # error chart measures what the big number counts down to: HowFar with the profile as its
        # legs above (with past races, the same over its own learned model), without it at each
        # leg's average grade, the average pace at that pace
        m = k
        while m < len(wps) - 1 and wps[m].name in MINOR:
            m += 1
        extra = []
        for cid, use_ahead, pr in preds:
            if cid == "profile":
                extra.append(legs[m - k - 1] if m > k else 0)
                continue
            t_more = 0.0
            for j in range(k + 1, m + 1):
                length = wps[j].course_dist - wps[j - 1].course_dist
                if cid == "average":
                    t_more += length / pr.speed()
                    continue
                if use_ahead:
                    s = pr.scale.ratio
                    t_more += sum(c * s / (pr.model.predict(g / s) * pr.est.fatigue)
                                  for c, g in S.chunks_ahead(race.elev, wps[j - 1].course_dist, wps[j].course_dist))
                    continue
                g = max(-40.0, min(40.0, (race.elev.at(wps[j].course_dist) - race.elev.at(wps[j - 1].course_dist)) / max(1.0, length) * 100.0))
                s = pr.scale.ratio
                t_more += length * s / (pr.model.predict(g / s) * pr.est.fatigue)
            extra.append(round(t_more))
        frames.append([round(p.t), round(cd), round(p.alt), k, round(dn), round(t_arr - p.t), round(s_arr - race.stops[i]),
                       int(recent_stop), round(final.scale.ratio, 3),
                       *(round(final.model.predict(g), 3) for g in (0.0, 20.0, -20.0)),
                       round(final.est.fatigue, 3), round(race.stops[i]), *etas, legs, extra,
                       # the watch after five past races: its legs, distance ratio, speeds, fatigue
                       [legs_of(learned), round(learned.scale.ratio, 3),
                        *(round(learned.model.predict(g), 3) for g in (0.0, 20.0, -20.0)), round(learned.est.fatigue, 3)]])

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
        "// waypoint to each later one, then each prediction's time (s) from the next waypoint to the next\n"
        "// main checkpoint, one per entry of configs, then the same watch after five past races: [its times\n"
        "// from the next waypoint to each later one, distance ratio, speeds on the flat, up and down, fatigue]]\n"
        "window.HOWFAR_DEMO = " + json.dumps(data, separators=(",", ":"), ensure_ascii=False) + ";\n")
    print(len(frames), "frames,", Path(args.out).stat().st_size, "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())

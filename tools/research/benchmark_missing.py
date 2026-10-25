#!/usr/bin/env python3
"""How good is the field when the watch's course and the pasted profile don't list the same
checkpoints?

    python tools/research/benchmark_missing.py --out missing.json [--activities FOLDER]

Runs the field itself (wpeta.field.FieldLogic) second by second, the way replay.py does, with
the profile matched three ways: the old name-only matching, the current one (places points
the profile doesn't know on it), and no profile at all. Cases:

- complete:  profile and watch list the same checkpoints
- missing:   the profile lacks every other checkpoint the watch has
- extra:     the profile has every checkpoint, the watch only every other one
- longer:    as "missing", with the watch's course 3% longer than the profile's (another
             version of the course), so distanceToDestination can't be trusted

Races: the four of benchmark.py with their real checkpoints and the others as past races.
With --activities, also every activity of at least --min-km, with checkpoints every 5 km
and no past races.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import benchmark as B  # noqa: E402
import replay as R  # noqa: E402
from wpeta.field import FieldLogic  # noqa: E402
from wpeta.profile import FINISH_NAME, Elevation, ProfileMatcher, build_entries, names_match  # noqa: E402
from wpeta.readers import CoursePoint, read_course, read_track  # noqa: E402

STEP = 50
EVAL_EVERY = 30.0
CASES = ("complete", "missing", "extra", "longer")
MODES = ("old", "new", "none")


class OldMatcher:
    """The name-only matching the field used before (CourseProfile.mc up to v0.1)."""

    def __init__(self, step, entries):
        self.step, self.entries = step, entries
        self._pointer, self.current, self._last_name, self._last_dist = 0, None, None, 0.0

    def _find(self, name, dist_next, dist_dest):
        if name is not None:
            for i in range(self._pointer, len(self.entries)):
                if self.entries[i][0] != FINISH_NAME and names_match(self.entries[i][0], name):
                    return i
        if dist_dest is not None and abs(dist_dest - dist_next) < 30:
            last = len(self.entries) - 1
            if last >= self._pointer and self.entries[last][0] == FINISH_NAME:
                return last
        return None

    def update(self, name, dist_next, dist_dest, *_):
        self.target_dist = dist_next
        changed = name != self._last_name or dist_next > self._last_dist + 50
        self._last_name, self._last_dist = name, dist_next
        if changed:
            self.current = None
            idx = self._find(name, dist_next, dist_dest)
            if idx is not None and dist_next <= self.entries[idx][1] * 1.1 + 50:
                self.current, self._pointer = idx, idx + 1
        return self.current is not None

    def target_name(self, watch_name):
        return watch_name

    def target_time(self, est, scale):
        return self.remaining_time(self.target_dist, est, scale)

    def following(self):
        return None

    def remaining_time(self, dist_next, est, scale):
        """Time over the last dist_next metres of the entry (the last chunk may be shorter)."""
        _, length, grades = self.entries[self.current]
        n = len(grades)
        last_len = length - (n - 1) * self.step
        if last_len <= 0:
            last_len = self.step
        t, remaining, i = 0.0, dist_next, n - 1
        while i >= 0 and remaining > 0:
            use = min(last_len if i == n - 1 else self.step, remaining)
            t += est.time_for_grade(use, grades[i] / 10.0, scale)
            remaining -= use
            i -= 1
        if remaining > 0:
            t += est.time_for_grade(remaining, grades[0] / 10.0, scale)
        return t


def replay(points, wps, elev, profile, mode, imported, stretch, unknown):
    """Rows (waypoint index, predicted s, actual s without stops, profile knows the point)."""
    field = FieldLogic(stored=imported)
    if mode != "none":
        field.profile = (OldMatcher if mode == "old" else ProfileMatcher)(STEP, profile)
        field.profile.own_points = False  # scored against the watch's next point
    stops = R.stop_time_index(points)
    arrival, k = {}, 0
    for i, p in enumerate(points):
        while k < len(wps) and p.dist >= wps[k].act_dist:
            arrival[k] = (p.t, stops[i])
            k += 1
    total = elev.length  # distanceToDestination is to the end of the course, also after a DNF
    rows, k, next_eval = [], 0, 0.0
    for i, p in enumerate(points):
        while k < len(wps) and p.dist >= wps[k].act_dist:
            k += 1
        if k >= len(wps):
            break
        wp = wps[k]
        if k == 0:
            course_d = wp.course_dist - (wp.act_dist - p.dist)
        else:
            prev = wps[k - 1]
            frac = (p.dist - prev.act_dist) / max(1.0, wp.act_dist - prev.act_dist)
            course_d = prev.course_dist + frac * (wp.course_dist - prev.course_dist)
        dn = (wp.course_dist - course_d) * stretch
        eta = field.compute(p.t, True, p.dist, p.alt, dn, wp.name, (total - course_d) * stretch, elev.at(wp.course_dist))
        if k == 0 or eta is None or p.t < next_eval:
            continue
        next_eval = p.t + EVAL_EVERY
        t_arr, s_arr = arrival[k]
        rows.append((k, eta, (t_arr - p.t) - (s_arr - stops[i]), k not in unknown))
    return rows


def score(rows):
    """Average error (min) of the predictions made while the point was at most an hour away."""
    out = {}
    for what, keep in (("all", lambda r: True), ("unknown", lambda r: not r[3])):
        e = [abs(eta - act) / 60 for k, eta, act, known in rows if act <= 3600 and keep((k, eta, act, known))]
        out[what] = (sum(e) / len(e), len(e)) if e else None
    return out


def cases(wps, cps_for_profile):
    """(name, watch waypoints, profile checkpoints, stretch, watch indices the profile lacks)."""
    inner = [w for w in wps[1:-1]]
    every_other = {id(w) for j, w in enumerate(inner) if j % 2 == 1}
    out = []
    for c in CASES:
        if c == "extra":
            watch = [w for w in wps if id(w) not in every_other]
            prof = cps_for_profile(wps)
            unknown = set()
        else:
            watch = wps
            prof = cps_for_profile([w for w in wps if id(w) not in every_other or c == "complete"])
            unknown = set() if c == "complete" else {j for j, w in enumerate(wps) if id(w) in every_other}
        out.append((c, watch, prof, 1.03 if c == "longer" else 1.0, unknown))
    return out


def job(args):
    label, points, wps, course_pts, imported = args
    elev = Elevation(course_pts)

    def entries_for(ws):
        cps = [CoursePoint(w.name, w.course_dist) for w in ws[1:]]
        return build_entries(course_pts, cps, STEP)

    result = {}
    for c, watch, prof, stretch, unknown in cases(wps, entries_for):
        for mode in MODES:
            if mode == "none" and c in ("missing", "extra"):
                continue  # same as "complete" without a profile
            rows = replay(points, watch, elev, prof, mode, imported, stretch, unknown)
            result[f"{c}/{mode}"] = score(rows)
    return label, result


def race_jobs():
    out = []
    for key in B.RACES:
        if B.RACES[key][2] is None:
            continue  # no course file to take checkpoints out of
        r = B.race(key)
        course_pts, _ = read_course(str(B.RACES[key][2]))
        out.append((key, r.points, r.waypoints, course_pts, B.past_layer(key)))
    return out


def activity_jobs(folder, min_km):
    for f in sorted(Path(folder).glob("*.gpx")):
        pts = [p for p in read_track(f) if p.t is not None and p.alt is not None]
        if len(pts) < 100 or pts[-1].dist < min_km * 1000:
            continue
        total = pts[-1].dist
        wps = [R.Waypoint("Start", 0.0, 0.0)]
        d = 5000.0
        while d < total - 1000:
            wps.append(R.Waypoint(f"km {d / 1000:.0f}", d, d))
            d += 5000.0
        wps.append(R.Waypoint("Finish", total, total))
        yield (f.name, pts, wps, pts, None)


def summarize(title, results):
    print(f"\n{title}: {len(results)}")
    print(f"{'case':<10} {'matching':<10} {'all points':>11} {'points the profile lacks':>26}")
    for c in CASES:
        for mode in MODES:
            key = f"{c}/{mode}"
            if c in ("missing", "extra") and mode == "none":
                key = "complete/none"
            vals = {}
            for what in ("all", "unknown"):
                xs = [r[key][what] for r in results.values() if r[key][what]]
                vals[what] = sum(x[0] for x in xs) / len(xs) if xs else None
            u = f"{vals['unknown']:.2f} min" if vals["unknown"] is not None and c not in ("complete", "extra") else "-"
            print(f"{c:<10} {mode:<10} {vals['all']:8.2f} min {u:>26}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--activities")
    ap.add_argument("--min-km", type=float, default=25)
    ap.add_argument("--jobs", type=int, default=8)
    args = ap.parse_args()

    out = {}
    with ProcessPoolExecutor(args.jobs) as ex:
        races = dict(ex.map(job, race_jobs()))
        out["races"] = races
        summarize("races", races)
        if args.activities:
            acts = {}
            for n, (name, res) in enumerate(ex.map(job, activity_jobs(args.activities, args.min_km), chunksize=2), 1):
                acts[name] = res
                if n % 20 == 0:
                    print(f"{n} activities", flush=True)
            out["activities"] = acts
            summarize("activities", acts)
    json.dump(out, open(args.out, "w"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Replay a recorded activity through the data field's logic to see how good its ETAs are.

    python tools/replay.py run.gpx --course race_course.fit
    python tools/replay.py run.fit --every 2000
    python tools/replay.py run.fit --past old1.fit old2.gpx

With --course, the course's waypoints (FIT course points or GPX <wpt>) are placed on the
recorded track by position. The course can be the whole race; waypoints the activity
didn't pass are skipped. The field sees course distances and the course's elevation,
as the watch would. Without --course there is a virtual waypoint every --every metres.

It reports the ETA error at 2 km, 1 km and 500 m before each waypoint (also with real
stops such as aid stations left out, since the field can't foresee them), with the
course profile (as if you had pasted one) and with the average-grade fallback.
Negative errors mean the field predicted arriving too early.
"""

import argparse
import bisect
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from wpeta.field import FieldLogic  # noqa: E402
from wpeta.learn import layer_from_files  # noqa: E402
from wpeta.model import Layer  # noqa: E402
from wpeta.profile import Elevation, build_entries  # noqa: E402
from wpeta.readers import CoursePoint, Point, haversine, read_course, read_track  # noqa: E402

CHECKS = (2000, 1000, 500)
STEP = 50
MAX_OFF_TRACK = 200.0  # metres: a course point farther than this from the track wasn't passed


@dataclass
class Waypoint:
    name: str
    act_dist: float  # where the activity passes it
    course_dist: float  # where it is on the course


STOP_DIST = 30.0  # stopped: less than this between 60 s before and 60 s after
SLOW_DIST = 90.0  # or less than this with the altitude within SLOW_ALT: standing at an aid station
SLOW_ALT = 1.5  # while GPS drift moves the distance on (a slow steep climb keeps climbing)


def stop_time_index(points: list[Point]) -> list[float]:
    """Cumulative stopped time at each point. Offline rule (it can look ahead): a second is a
    stop when less than STOP_DIST is covered between 60 s before and 60 s after, or less than
    SLOW_DIST with the altitude within SLOW_ALT over those two minutes."""
    out = [0.0]
    lo = hi = 0
    n = len(points)
    for i in range(1, n):
        t = points[i].t
        while points[lo].t < t - 60:
            lo += 1
        while hi < n - 1 and points[hi].t < t + 60:
            hi += 1
        moved = points[hi].dist - points[lo].dist
        stopped = moved < STOP_DIST
        if not stopped and moved < SLOW_DIST:
            alts = [p.alt for p in points[lo:hi + 1]]
            stopped = None not in alts and max(alts) - min(alts) < SLOW_ALT
        dt = t - points[i - 1].t
        out.append(out[-1] + (dt if stopped and dt < 30 else 0.0))
    return out


def virtual_waypoints(points: list[Point], every: float) -> list[Waypoint]:
    total = points[-1].dist
    wps = [Waypoint(f"WP{i}", d, d) for i, d in enumerate(range(int(every), int(total), int(every)), 1)]
    wps.append(Waypoint("Finish", total, total))
    return wps


def place_course_points(points: list[Point], course_pts: list[Point], cps: list[CoursePoint]) -> list[Waypoint]:
    """Finds where the activity first passes each course point, in order."""
    cdist = [p.dist for p in course_pts]
    track = [p for p in points if p.lat is not None]
    wps: list[Waypoint] = []
    start = 0
    for cp in cps:
        j = min(bisect.bisect_left(cdist, cp.dist), len(course_pts) - 1)
        lat, lon = course_pts[j].lat, course_pts[j].lon
        if lat is None:
            continue
        if wps:
            # look ahead only as far as the course says the point is, with slack for GPS
            limit = track[start].dist + (cp.dist - wps[-1].course_dist) * 1.5 + 2000
        else:
            limit = float("inf")
        best, best_i = None, None
        for i in range(start, len(track)):
            if track[i].dist > limit:
                break
            d = haversine(lat, lon, track[i].lat, track[i].lon)
            if best is None or d < best:
                best, best_i = d, i
            elif best <= MAX_OFF_TRACK and d > best + 300:
                break  # the first pass: on loops and out-and-backs the point is passed again later
        if best is not None and best <= MAX_OFF_TRACK:
            wps.append(Waypoint(cp.name, track[best_i].dist, cp.dist))
            start = best_i
    return wps


def replay(points, waypoints: list[Waypoint], past: Layer | None, profile, elev_next) -> dict:
    """Returns {check distance: [(waypoint name, error s, error excluding stops s), ...]}."""
    field = FieldLogic(stored=past, profile=profile)
    stops = stop_time_index(points)
    total_course = waypoints[-1].course_dist

    arrival = {}
    k = 0
    for i, p in enumerate(points):
        while k < len(waypoints) and p.dist >= waypoints[k].act_dist:
            arrival[k] = (p.t, stops[i])
            k += 1

    errors: dict[int, list[tuple[str, float, float]]] = {c: [] for c in CHECKS}
    done = set()
    k = 0
    for i, p in enumerate(points):
        while k < len(waypoints) and p.dist >= waypoints[k].act_dist:
            k += 1
        if k >= len(waypoints):
            break
        wp = waypoints[k]
        # activity distance -> course distance, linearly between the waypoints around us
        if k == 0:
            course_d = wp.course_dist - (wp.act_dist - p.dist)
            seg_len = float("inf") if wp.course_dist == wp.act_dist else wp.course_dist - course_d
        else:
            prev = waypoints[k - 1]
            frac = (p.dist - prev.act_dist) / max(1.0, wp.act_dist - prev.act_dist)
            course_d = prev.course_dist + frac * (wp.course_dist - prev.course_dist)
            seg_len = wp.course_dist - prev.course_dist
        dist_next = wp.course_dist - course_d
        eta = field.compute(p.t, True, p.dist, p.alt, dist_next, wp.name, total_course - course_d, elev_next(wp))
        for c in CHECKS:
            if eta is not None and dist_next <= c < seg_len and (k, c) not in done:
                done.add((k, c))
                t_arr, s_arr = arrival[k]
                actual = t_arr - p.t
                errors[c].append((wp.name, eta - actual, eta - (actual - (s_arr - stops[i]))))
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("activity", help="activity .fit or .gpx")
    ap.add_argument("--course", help="course .fit or .gpx with waypoints, to use real waypoints")
    ap.add_argument("--every", type=float, default=2000, help="virtual waypoint spacing in metres (default 2000)")
    ap.add_argument("--past", nargs="+", help="earlier activities, as if the watch remembered them")
    ap.add_argument("-v", "--verbose", action="store_true", help="print the error at every waypoint")
    args = ap.parse_args()

    past = layer_from_files(args.past) if args.past else None
    points = [p for p in read_track(args.activity) if p.t is not None and p.alt is not None]

    if args.course:
        skipped: list[str] = []
        course_pts, cps = read_course(args.course, skipped=skipped)
        if skipped:
            print(f"Skipped {len(skipped)} course waypoints more than 200 m off the course track.", file=sys.stderr)
        if not cps:
            print("The course has no waypoints.", file=sys.stderr)
            return 1
        waypoints = place_course_points(points, course_pts, cps)
        if not waypoints:
            print("None of the course's waypoints are on this activity's track.", file=sys.stderr)
            return 1
        print(f"{len(waypoints)} of {len(cps)} course waypoints are on this activity: "
              + ", ".join(w.name for w in waypoints), file=sys.stderr)
        elev = Elevation(course_pts)
        entries = build_entries(course_pts, cps, STEP)
    else:
        waypoints = virtual_waypoints(points, args.every)
        elev = Elevation(points)
        entries = build_entries(points, [CoursePoint(w.name, w.act_dist) for w in waypoints], STEP)

    for label, profile in (("course profile", (STEP, entries)), ("average grade ", None)):
        errors = replay(points, waypoints, past, profile, lambda wp: elev.at(wp.course_dist))
        print(f"{label}:")
        for c in CHECKS:
            e = errors[c]
            if not e:
                continue
            line = f"  {c:5d} m before waypoint (n={len(e):2d}):"
            for j, what in ((1, "all"), (2, "excl. stops")):
                xs = [x[j] for x in e]
                line += f"  {what}: mean abs {sum(abs(x) for x in xs) / len(xs):4.0f} s, bias {sum(xs) / len(xs):+5.0f} s"
            print(line)
            if args.verbose:
                for name, err, err_moving in e:
                    print(f"      {name:<24} {err:+6.0f} s   excl. stops {err_moving:+6.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())

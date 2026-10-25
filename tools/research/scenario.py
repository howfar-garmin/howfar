"""Replay harness for comparing ETA predictors on a recorded run against a real course.

Every predictor sees the same thing a data field would: the run's samples up to now, the
remaining course distance to the next waypoint, the course elevation ahead (only when
"trail ahead" is allowed) and, when "past races" is allowed, other recorded runs.
"""

from __future__ import annotations

import bisect
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import replay as R  # noqa: E402
from wpeta.profile import Elevation  # noqa: E402
from wpeta.readers import CoursePoint, Point, read_course, read_track  # noqa: E402

CHUNK = 50.0  # metres of course per grade value ahead
EVAL_EVERY = 30.0  # seconds of race time between predictions
CHECKS = (2000, 1000, 500)
VIRTUAL_TARGET = 12500.0  # courses without waypoints get equal stretches of about this length (10-15 km)


@dataclass
class Ctx:
    """What a predictor may use when asked for the time to the next waypoint."""

    t: float  # race time, s
    dist: float  # distance the watch has measured so far, m
    alt: float  # current altitude, m
    dist_next: float  # course metres to the next waypoint
    dist_dest: float  # course metres to the finish
    elev_next: float  # course elevation at the next waypoint
    chunks: list[tuple[float, float]]  # (course metres, grade %) from here to the waypoint
    wp_index: int


@dataclass
class Race:
    name: str
    points: list[Point]
    waypoints: list  # replay.Waypoint
    elev: Elevation  # course elevation by course distance
    stops: list[float]  # cumulative stopped time (offline rule) per point
    arrival: dict[int, tuple[float, float]] = field(default_factory=dict)


def load_race(name: str, activity: str, course: str) -> Race:
    pts = [p for p in read_track(activity) if p.t is not None and p.alt is not None]
    cpts, cps = read_course(course)
    length = cpts[-1].dist
    if not cps:
        n = max(1, round(length / VIRTUAL_TARGET))
        cps = [CoursePoint(f"km {length * i / n / 1000:.0f}", length * i / n) for i in range(1, n)]
        cps.append(CoursePoint("Finish", length))
    elif length - cps[-1].dist > 1000:
        cps.append(CoursePoint("Finish", length))  # like the "*" entry of a course profile
    wps = R.place_course_points(pts, cpts, cps)
    # every race starts from a waypoint at the start, so the first stretch has a "previous point"
    if not wps or wps[0].course_dist > 500:
        wps.insert(0, R.Waypoint("Start", pts[0].dist, 0.0))
    race = Race(name, pts, wps, Elevation(cpts), R.stop_time_index(pts))
    k = 0
    for i, p in enumerate(pts):
        while k < len(wps) and p.dist >= wps[k].act_dist:
            race.arrival[k] = (p.t, race.stops[i])
            k += 1
    return race


def chunks_ahead(elev: Elevation, start: float, end: float) -> list[tuple[float, float]]:
    out = []
    d = start
    while d < end - 0.5:
        nxt = min(d + CHUNK, end)
        out.append((nxt - d, (elev.at(nxt) - elev.at(d)) / (nxt - d) * 100.0))
        d = nxt
    return out or [(max(end - start, 0.1), 0.0)]


def first_scored(wps) -> int:
    """Index of the first waypoint worth predicting: skips start-area points under 1 km out
    (the TOR files begin with "Start" and "TORX Finish Line", both in the start town)."""
    for k in range(1, len(wps)):
        if wps[k].course_dist >= 1000:
            return k
    return len(wps)


def run(race: Race, predictor, trail_ahead: bool = True, first_wp: int | None = None):
    """Feeds the race to the predictor. Returns a list of evaluation rows:
    (t, waypoint index, dist_next, predicted s, actual s, actual s excluding stops)."""
    wps = race.waypoints
    if first_wp is None:
        first_wp = first_scored(wps)
    total = wps[-1].course_dist
    rows = []
    k = 0
    next_eval = 0.0
    for i, p in enumerate(race.points):
        predictor.observe(p.t, p.dist, p.alt)
        while k < len(wps) and p.dist >= wps[k].act_dist:
            k += 1
        if k >= len(wps):
            break
        if p.t < next_eval or k < first_wp:
            continue
        next_eval = p.t + EVAL_EVERY
        wp = wps[k]
        prev = wps[k - 1]
        frac = (p.dist - prev.act_dist) / max(1.0, wp.act_dist - prev.act_dist)
        cd = prev.course_dist + frac * (wp.course_dist - prev.course_dist)
        dn = wp.course_dist - cd
        if dn <= 0:
            continue
        elev_next = race.elev.at(wp.course_dist)
        if trail_ahead:
            ch = chunks_ahead(race.elev, cd, wp.course_dist)
        else:
            ch = [(dn, max(-40.0, min(40.0, (elev_next - p.alt) / dn * 100.0)))]
        ctx = Ctx(p.t, p.dist, p.alt, dn, total - cd, elev_next, ch, k)
        eta = predictor.predict(ctx)
        t_arr, s_arr = race.arrival[k]
        actual = t_arr - p.t
        rows.append((p.t, k, dn, eta, actual, actual - (s_arr - race.stops[i])))
    return rows


def score(rows) -> dict:
    """Errors in minutes. 'check' metrics: the moment each waypoint is 2 km / 1 km / 500 m
    away (course distance), once per waypoint. 'hour' metric: every prediction made while the
    waypoint was at most 60 min away. Stops are left out (the field can't foresee them)."""
    out = {}
    for c in CHECKS:
        seen, errs = set(), []
        for t, k, dn, eta, act, act_moving in rows:
            if dn <= c and k not in seen:
                seen.add(k)
                errs.append((eta - act_moving) / 60)
        out[f"mae_{c}"] = sum(abs(e) for e in errs) / len(errs) if errs else float("nan")
        out[f"within5_{c}"] = sum(abs(e) <= 5 for e in errs) / len(errs) if errs else float("nan")
        out[f"bias_{c}"] = sum(errs) / len(errs) if errs else float("nan")
    near = [(eta - am) / 60 for t, k, dn, eta, act, am in rows if am <= 3600]
    out["mae_hour"] = sum(abs(e) for e in near) / len(near)
    out["within5_hour"] = sum(abs(e) <= 5 for e in near) / len(near)
    out["within10_hour"] = sum(abs(e) <= 10 for e in near) / len(near)
    out["bias_hour"] = sum(near) / len(near)
    return out

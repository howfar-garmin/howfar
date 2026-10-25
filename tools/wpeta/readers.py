"""Read activities and courses from FIT or GPX files."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SEMICIRCLE_TO_DEG = 180.0 / 2**31
EARTH_RADIUS = 6371008.8
MAX_WAYPOINT_OFFSET = 200.0  # metres: farther waypoints aren't on this course


@dataclass
class Point:
    t: float | None  # seconds since the first point
    dist: float  # metres along the track
    alt: float | None
    speed: float | None = None
    lat: float | None = None
    lon: float | None = None


@dataclass
class CoursePoint:
    name: str
    dist: float


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS * math.asin(math.sqrt(a))


def _fill_distances(points: list[Point]) -> None:
    """Compute cumulative distance from coordinates where the file has none."""
    total = 0.0
    prev = None
    for p in points:
        if prev is not None and None not in (p.lat, p.lon, prev.lat, prev.lon):
            total += haversine(prev.lat, prev.lon, p.lat, p.lon)
        p.dist = total
        prev = p


def _project(points: list[Point], lat: float, lon: float) -> tuple[float, float]:
    """(distance along the track, metres off the track) of the track point nearest to (lat, lon)."""
    best = min(
        (p for p in points if p.lat is not None),
        key=lambda p: haversine(lat, lon, p.lat, p.lon),
    )
    return best.dist, haversine(lat, lon, best.lat, best.lon)


def _read_fit(path: Path) -> tuple[list[Point], list[CoursePoint], list[tuple[str, float, float]]]:
    import fitdecode

    points: list[Point] = []
    cps: list[CoursePoint] = []
    cps_unplaced: list[tuple[str, float, float]] = []
    t0 = None
    has_dist = True
    with fitdecode.FitReader(str(path)) as fit:
        for frame in fit:
            if frame.frame_type != fitdecode.FIT_FRAME_DATA:
                continue
            if frame.name == "record":
                def val(*names):
                    for n in names:
                        if frame.has_field(n):
                            v = frame.get_value(n)
                            if v is not None:
                                return v
                    return None

                ts = val("timestamp")
                t = None
                if ts is not None:
                    if t0 is None:
                        t0 = ts
                    t = (ts - t0).total_seconds()
                lat, lon = val("position_lat"), val("position_long")
                dist = val("distance")
                if dist is None:
                    has_dist = False
                points.append(
                    Point(
                        t=t,
                        dist=float(dist) if dist is not None else 0.0,
                        alt=_f(val("enhanced_altitude", "altitude")),
                        speed=_f(val("enhanced_speed", "speed")),
                        lat=lat * SEMICIRCLE_TO_DEG if lat is not None else None,
                        lon=lon * SEMICIRCLE_TO_DEG if lon is not None else None,
                    )
                )
            elif frame.name == "course_point":
                name = frame.get_value("name", fallback=None) or ""
                dist = frame.get_value("distance", fallback=None)
                if dist is not None:
                    cps.append(CoursePoint(str(name), float(dist)))
                else:
                    lat = frame.get_value("position_lat", fallback=None)
                    lon = frame.get_value("position_long", fallback=None)
                    if lat is not None and lon is not None:
                        cps_unplaced.append((str(name), lat * SEMICIRCLE_TO_DEG, lon * SEMICIRCLE_TO_DEG))
    if not has_dist:
        _fill_distances(points)
    return points, cps, cps_unplaced


def _f(v) -> float | None:
    return float(v) if v is not None else None


def _tag(el: ET.Element) -> str:
    return el.tag.rsplit("}", 1)[-1]


def _child(el: ET.Element, name: str) -> ET.Element | None:
    for c in el:
        if _tag(c) == name:
            return c
    return None


def _read_gpx(path: Path) -> tuple[list[Point], list[tuple[str, float, float]]]:
    root = ET.parse(path).getroot()
    trkpts = [e for e in root.iter() if _tag(e) == "trkpt"]
    if not trkpts:
        trkpts = [e for e in root.iter() if _tag(e) == "rtept"]
    points: list[Point] = []
    t0 = None
    for e in trkpts:
        ele = _child(e, "ele")
        tm = _child(e, "time")
        t = None
        if tm is not None and tm.text:
            dt = datetime.fromisoformat(tm.text.strip().replace("Z", "+00:00"))
            if t0 is None:
                t0 = dt
            t = (dt - t0).total_seconds()
        points.append(
            Point(
                t=t,
                dist=0.0,
                alt=float(ele.text) if ele is not None and ele.text else None,
                lat=float(e.get("lat")),
                lon=float(e.get("lon")),
            )
        )
    _fill_distances(points)
    wpts = []
    for e in root:
        if _tag(e) == "wpt":
            n = _child(e, "name")
            wpts.append(((n.text or "").strip() if n is not None else "", float(e.get("lat")), float(e.get("lon"))))
    return points, wpts


def read_track(path: str | Path) -> list[Point]:
    """Track points of an activity, sorted by distance."""
    path = Path(path)
    if path.suffix.lower() == ".gpx":
        points, _ = _read_gpx(path)
    else:
        points, _, _ = _read_fit(path)
    return points


def read_course(
    path: str | Path, max_offset: float = MAX_WAYPOINT_OFFSET, skipped: list[str] | None = None
) -> tuple[list[Point], list[CoursePoint]]:
    """Track points and course points (waypoints) of a course, both sorted by distance.

    Waypoints without a distance (GPX <wpt>) are placed at the nearest track point.
    Those more than max_offset metres off the track are dropped (their names go into
    `skipped`): race GPX files often carry every waypoint of the whole race.
    """
    path = Path(path)
    if path.suffix.lower() == ".gpx":
        points, unplaced = _read_gpx(path)
        cps: list[CoursePoint] = []
    else:
        points, cps, unplaced = _read_fit(path)
    for name, lat, lon in unplaced:
        dist, offset = _project(points, lat, lon)
        if offset <= max_offset:
            cps.append(CoursePoint(name, dist))
        elif skipped is not None:
            skipped.append(name)
    cps.sort(key=lambda c: c.dist)
    return points, cps

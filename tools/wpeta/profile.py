"""Course elevation profile split at course points, in the string format the watch reads.

Format:  p1;<step>;<name>|<length m>|<g>,<g>,...;<name>|...
Each entry is the segment from the previous course point (or the start) to the named
point. Grades are in tenths of a percent, one per <step> metres, ordered towards the
point; the chunk next to the point may be shorter than <step>. A final entry named "*"
covers the stretch from the last course point to the finish.
"""

from __future__ import annotations

import bisect

from .model import MAX_GRADE, MIN_GRADE, PROFILE_PREFIX, clamp
from .readers import CoursePoint, Point

FINISH_NAME = "*"
STEPS = (25, 50, 100, 200, 400)


def _clean(name: str) -> str:
    name = "".join(" " if ch in ";|," else ch for ch in name).strip()
    return name if name and name != FINISH_NAME else "?"


class Elevation:
    def __init__(self, points: list[Point]) -> None:
        pts = sorted((p.dist, p.alt) for p in points if p.alt is not None)
        self.d: list[float] = []
        self.a: list[float] = []
        for d, a in pts:
            if self.d and d <= self.d[-1]:
                continue
            self.d.append(d)
            self.a.append(a)
        if len(self.d) < 2:
            raise ValueError("course has no elevation data")

    @property
    def length(self) -> float:
        return self.d[-1]

    def at(self, dist: float) -> float:
        if dist <= self.d[0]:
            return self.a[0]
        if dist >= self.d[-1]:
            return self.a[-1]
        j = bisect.bisect_right(self.d, dist)
        d0, d1 = self.d[j - 1], self.d[j]
        return self.a[j - 1] + (self.a[j] - self.a[j - 1]) * (dist - d0) / (d1 - d0)


def segment_grades(elev: Elevation, start: float, end: float, step: float) -> list[int]:
    grades = []
    d = start
    while d < end - 0.5:
        nxt = min(d + step, end)
        g = (elev.at(nxt) - elev.at(d)) / (nxt - d) * 100.0
        grades.append(int(round(clamp(g, MIN_GRADE, MAX_GRADE) * 10)))
        d = nxt
    return grades or [0]


def build_entries(points: list[Point], cps: list[CoursePoint], step: float) -> list[tuple[str, int, list[int]]]:
    elev = Elevation(points)
    entries = []
    prev = 0.0
    for cp in cps:
        end = clamp(cp.dist, prev, elev.length)
        entries.append((_clean(cp.name), max(1, int(round(end - prev))), segment_grades(elev, prev, end, step)))
        prev = end
    if elev.length - prev > 10:
        entries.append((FINISH_NAME, int(round(elev.length - prev)), segment_grades(elev, prev, elev.length, step)))
    return entries


def profile_string(entries: list[tuple[str, int, list[int]]], step: int) -> str:
    parts = [PROFILE_PREFIX, str(step)]
    for name, length, grades in entries:
        parts.append(f"{name}|{length}|{','.join(str(g) for g in grades)}")
    return ";".join(parts)


def parse_profile(s: str) -> tuple[int, list[tuple[str, int, list[int]]]]:
    parts = s.strip().split(";")
    if len(parts) < 2 or parts[0] != PROFILE_PREFIX:
        raise ValueError("not a p1 course profile string")
    step = int(parts[1])
    entries = []
    for p in parts[2:]:
        f = p.split("|")
        if len(f) != 3:
            continue
        entries.append((f[0], int(f[1]), [int(g) for g in f[2].split(",") if g]))
    return step, entries


def best_profile(points: list[Point], cps: list[CoursePoint], max_len: int, step: int | None = None) -> tuple[int, str]:
    """Profile string at the given step, or at the finest step that fits in max_len characters."""
    for s in (step,) if step else STEPS:
        text = profile_string(build_entries(points, cps, s), s)
        if step or len(text) <= max_len:
            return s, text
    return s, text


def names_match(a: str, b: str) -> bool:
    """Case-insensitive; also matches when one name is a prefix (>= 3 chars) of the other,
    since the watch may truncate course point names."""
    a, b = a.lower(), b.lower()
    if a == b:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 3 and long_.startswith(short)


class ProfileMatcher:
    """Follows the watch's next course point through the profile entries (mirror of CourseProfile.mc)."""

    def __init__(self, step: int, entries: list[tuple[str, int, list[int]]]) -> None:
        self.step = step
        self.entries = entries
        self.reset()

    def reset(self) -> None:
        self._pointer = 0
        self.current: int | None = None
        self.mismatched = False
        self._last_name: str | None = None
        self._last_dist = 0.0

    def _find(self, name: str | None, dist_next: float, dist_dest: float | None) -> int | None:
        if name is not None:
            for i in range(self._pointer, len(self.entries)):
                if self.entries[i][0] != FINISH_NAME and names_match(self.entries[i][0], name):
                    return i
        if dist_dest is not None and abs(dist_dest - dist_next) < 30:
            last = len(self.entries) - 1
            if last >= self._pointer and self.entries[last][0] == FINISH_NAME:
                return last
        return None

    def update(self, name: str | None, dist_next: float, dist_dest: float | None) -> bool:
        """Returns True when a profile segment is active for the current next point."""
        changed = name != self._last_name or dist_next > self._last_dist + 50
        self._last_name = name
        self._last_dist = dist_next
        if changed:
            self.current = None
            self.mismatched = False
            idx = self._find(name, dist_next, dist_dest)
            if idx is not None:
                if dist_next > self.entries[idx][1] * 1.1 + 50:
                    self.mismatched = True
                else:
                    self.current = idx
                    self._pointer = idx + 1
        return self.current is not None

    def entry(self) -> tuple[str, int, list[int]]:
        assert self.current is not None
        return self.entries[self.current]

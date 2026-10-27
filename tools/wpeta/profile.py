"""Course elevation profile split at course points, in the string format the watch reads.

Format:  p1;<step>;<name>|<length m>|<g>,<g>,...;<name>|...
Each entry is the segment from the previous course point (or the start) to the named
point. Grades are in tenths of a percent, one per <step> metres, ordered towards the
point; the chunk next to the point may be shorter than <step>. A final entry named "*"
covers the stretch from the last course point to the finish. A name starting with "+" is a
minor point (a climb top, a hut, a point of your own): the field counts down to the main
points, and on a field of its own lists the minor ones on the way above it.
"""

from __future__ import annotations

import bisect

from .model import MAX_GRADE, MIN_GRADE, PROFILE_PREFIX, clamp
from .readers import CoursePoint, Point

FINISH_NAME = "*"
MINOR_MARK = "+"
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


def half_percent(g: int) -> float:
    """A grade in tenths of a percent as the watch keeps it: to the nearest half percent (half away
    from zero), within +-63.5%."""
    q = (g + 2) // 5 if g >= 0 else -((2 - g) // 5)
    return max(-127, min(127, q)) * 0.5


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
    """Puts the watch's next course point on the profile (mirror of CourseProfile.mc).

    Every next point gets a place on the profile, `loc` (metres from the profile's start), and
    the time to it is the profile's stretch that ends there and is distanceToNextPoint long:
    - a point the profile knows by name: the end of its entry;
    - a point it doesn't know: where you are plus distanceToNextPoint, where you are being the
      profile's length minus distanceToDestination.
    The watch's course may be another version of the course, a bit longer or shorter, so the
    watch's distances are converted with `ratio` (profile metres per watch course metre),
    learned at each point the profile knows from how far both say the finish is.

    What the field counts down to (`target_*`) is the next main profile point ahead of you,
    which can be one the watch's course doesn't have; a watch point the profile doesn't know (a
    turn the watch announces) is never counted down to. `via` is the next minor point before it (a
    climb top or a hut added on the race prep page). Where you are is always taken from the
    watch's next point, so the watch's checkpoints keep anchoring it.
    """

    SLACK = 100.0  # m: a stretch may start this far before the profile's start
    PASSED = 5.0  # m: a profile point this close behind or ahead counts as reached
    own_points = True  # count down to the profile's own points too (research replays turn it off)
    MIN_RATIO_DIST = 2000.0  # m to the finish below which the ratio isn't updated any more
    RATIO_LO = 0.8
    RATIO_HI = 1.25

    def __init__(self, step: int, entries: list[tuple[str, int, list[int]]]) -> None:
        self.step = step
        self.minor = [n.startswith(MINOR_MARK) for n, _, _ in entries]
        self.entries = [(n[1:] if m else n, length, g or [0]) for (n, length, g), m in zip(entries, self.minor)]
        self.starts: list[float] = []
        d = 0.0
        for _, length, _ in self.entries:
            self.starts.append(d)
            d += length
        self.total = d
        self.reset()

    def reset(self) -> None:
        self._pointer = 0
        self.current: int | None = None  # entry of a point known by name
        self.loc: float | None = None  # where the watch's next point is on the profile
        self.mismatched = False
        self.ratio: float | None = None
        self._last_name: str | None = None
        self._last_dist = 0.0
        self._here: float | None = None  # where you were at the last update with a located point
        self._here_watch: float | None = None  # and the watch's distance then
        self.target_end: float | None = None  # profile metres of what the field counts down to
        self.target_index: int | None = None  # its entry, None for a watch point the profile lacks
        self.target_dist = 0.0  # watch course metres to it
        self.via: int | None = None  # entry of the next minor point before it
        self.vias: list[int] = []  # every minor point before it, in order

    # --- walking the profile: stretches of constant grade --------------------------------

    def _seek(self, a: float) -> None:
        i = 0
        while i + 1 < len(self.starts) and self.starts[i + 1] <= a:
            i += 1
        self._ci = i
        self._ck = max(0, min(int((a - self.starts[i]) // self.step), len(self.entries[i][2]) - 1))
        self._ca = a

    def _next(self, b: float) -> tuple[float, float]:
        """Length and grade (%) of the next stretch of constant grade, ending at b at most."""
        while self._ci < len(self.entries) and self._ca < b:
            _, length, grades = self.entries[self._ci]
            last = len(grades) - 1
            start = self.starts[self._ci]
            end = start + length if self._ck >= last else start + (self._ck + 1) * self.step
            grade = half_percent(grades[self._ck])
            hi = min(end, b)
            if hi >= end:
                if self._ck >= last:
                    self._ci += 1
                    self._ck = 0
                else:
                    self._ck += 1
            if hi > self._ca:
                use = hi - self._ca
                self._ca = hi
                return use, grade
        return 0.0, 0.0

    # --- following the next point ----------------------------------------------------------

    def _position(self, dist_dest: float | None, watch_dist: float | None, scale: float) -> float | None:
        r = self.ratio if self.ratio is not None else 1.0
        if dist_dest is not None:
            return max(0.0, self.total - dist_dest * r)
        if self._here is None:
            return None
        p = self._here
        if watch_dist is not None and self._here_watch is not None:
            p += (watch_dist - self._here_watch) / scale * r
        return p

    def _find(self, name: str | None, dist_next: float, dist_dest: float | None, here: float | None) -> int | None:
        """The entry of the next point: the first one ahead with this name whose stretch fits
        where you are; or the finish."""
        r = self.ratio if self.ratio is not None else 1.0
        if name is not None:
            for i in range(self._pointer, len(self.entries)):
                n = self.entries[i][0]
                if n != FINISH_NAME and names_match(n, name):
                    start = self.starts[i] + self.entries[i][1] - dist_next * r
                    if start < -self.SLACK:
                        self.mismatched = True
                    elif here is None or abs(start - here) <= 500 + 0.2 * dist_next:
                        return i
        if dist_dest is not None and abs(dist_dest - dist_next) < 30:
            last = len(self.entries) - 1
            if last >= self._pointer and self.entries[last][0] == FINISH_NAME:
                return last
        return None

    def update(
        self,
        name: str | None,
        dist_next: float,
        dist_dest: float | None,
        watch_dist: float | None = None,
        scale: float = 1.0,
    ) -> bool:
        """Returns True when the next point has a place on the profile."""
        if self.ratio is None and dist_dest is not None and dist_dest > 0:
            # first guess: you start at the start of both courses
            r = self.total / (dist_dest + (watch_dist or 0.0) / scale)
            self.ratio = r if 0.85 <= r <= 1.15 else 1.0
        changed = name != self._last_name or dist_next > self._last_dist + 50
        self._last_name = name
        self._last_dist = dist_next
        if changed:
            self.current = None
            self.loc = None
            self.mismatched = False
            here = self._position(dist_dest, watch_dist, scale)
            idx = self._find(name, dist_next, dist_dest, here if self._here is not None else None)
            if idx is not None:
                self.mismatched = False
                self.current = idx
                self.loc = self.starts[idx] + self.entries[idx][1]
                self._pointer = idx + 1
            elif here is not None:
                x = here + dist_next * (self.ratio or 1.0)
                if x > self.total + self.SLACK:
                    self.mismatched = True
                else:
                    self.loc = min(x, self.total)
        if self.loc is None:
            return False
        r = self.ratio or 1.0
        if self.current is not None and dist_dest is not None:
            left = self.total - self.loc  # profile metres from the point to the finish
            if left > self.MIN_RATIO_DIST and dist_dest - dist_next > self.MIN_RATIO_DIST:
                r = clamp(left / (dist_dest - dist_next), self.RATIO_LO, self.RATIO_HI)
                self.ratio = r
        self._here = self.loc - dist_next * r
        self._here_watch = watch_dist
        self._aim(self._here, r)
        return True

    def _end(self, i: int) -> float:
        return self.starts[i] + self.entries[i][1]

    def _aim(self, here: float, r: float) -> None:
        assert self.loc is not None
        self.target_end, self.target_index = self.loc, self.current
        self.via = None
        self.vias = []
        if self.own_points:
            main = next((i for i in range(len(self.entries)) if not self.minor[i] and self._end(i) > here + self.PASSED), None)
            # the profile's points are the list: a watch point it doesn't know (a turn the watch
            # announces, a checkpoint you unticked) still says where you are, but isn't counted down to
            if main is not None:
                self.target_end, self.target_index = self._end(main), main
            self.vias = [i for i in range(len(self.entries)) if self.minor[i]
                         and here + self.PASSED < self._end(i) < self.target_end - self.PASSED]
            self.via = self.vias[0] if self.vias else None
        self.target_dist = max(0.0, (self.target_end - here) / r)

    def target_name(self, watch_name: str | None) -> str | None:
        """Name of what the field counts down to."""
        if self.target_index is None or self.target_index == self.current:
            return watch_name
        return self.following_name(self.target_index)

    def target_time(self, estimator, scale: float) -> float:
        """Time from where you are to what the field counts down to."""
        assert self._here is not None and self.target_end is not None
        return max(self._time_between(self._here, self.target_end, estimator, scale), 1.0)

    def _time_between(self, a: float, b: float, estimator, scale: float) -> float:
        """Time over the profile from a to b; profile metres before its start count at the
        first grade."""
        r = self.ratio or 1.0
        before = max(0.0, -a)
        t = 0.0
        self._seek(max(0.0, a))
        first = None
        while True:
            use, g = self._next(b)
            if use <= 0:
                break
            if first is None:
                first = g
            t += estimator.time_for_grade(use / r, g * r, scale)
        if before > 0:
            t += estimator.time_for_grade(before / r, (first or 0.0) * r, scale)
        return t

    def remaining_time(self, dist_next: float, estimator, scale: float) -> float:
        """Time over the profile's stretch ending at loc, dist_next watch course metres long."""
        assert self.loc is not None
        return max(self._time_between(self.loc - dist_next * (self.ratio or 1.0), self.loc, estimator, scale), 1.0)

    def following(self) -> int | None:
        """Entry of the main profile point after the one the field counts down to, if any."""
        if self.target_end is None:
            return None
        for i in range(len(self.entries)):
            if not self.minor[i] and self._end(i) > self.target_end + 1:
                return i
        return None

    def following_after(self, i: int) -> int | None:
        """Entry of the main profile point after entry i, if any."""
        for j in range(i + 1, len(self.entries)):
            if not self.minor[j] and self._end(j) > self._end(i) + 1:
                return j
        return None

    def via_time(self, estimator, scale: float) -> float:
        """Time from where you are to the next minor point (`via`)."""
        assert self.via is not None
        return self.minor_time(self.via, estimator, scale)

    def minor_time(self, i: int, estimator, scale: float) -> float:
        """Time from where you are to profile point i (a minor point on the way)."""
        assert self._here is not None
        return max(self._time_between(self._here, self._end(i), estimator, scale), 1.0)

    def following_name(self, i: int) -> str:
        name = self.entries[i][0]
        return "Finish" if name == FINISH_NAME else name

    def following_time(self, i: int, estimator, scale: float) -> float:
        """Time from the point the field counts down to, to profile point i."""
        assert self.target_end is not None
        return self._time_between(self.target_end, self.starts[i] + self.entries[i][1], estimator, scale)

"""Speed-by-grade model, grade tracker and ETA maths.

This is a line-for-line mirror of the Monkey C code in source/ (SpeedGradeModel.mc,
GradeTracker.mc, EtaEstimator.mc). Keep the two in sync: the Python tools build the
strings the watch parses, and the tests here are the reference for the watch logic.
"""

from __future__ import annotations

import math

NUM_BINS = 41
MIN_GRADE = -40.0
MAX_GRADE = 40.0
BIN_STEP = 2.0

PRIOR_CAP = 10.0  # most weight past runs get in a bin vs. this run's observations, at the start
PRIOR_HALF = 10000.0  # metres of this run after which past runs count half as much
PRIOR_MIN = 0.5
MIN_WEIGHT = 3.0  # bins with less total weight are filled from their neighbours
DEFAULT_FLAT_SPEED = 2.8  # m/s, used only when there is no data at all
STORED_DECAY = 0.85  # weight kept by the stored model each time a run is merged in
STORED_CAP = 200.0
RUN_DECAY = 0.995  # fatigue: weight kept by this run's older observations at each new one (~3.5 km half-life)

MODEL_PREFIX = "v1"
PROFILE_PREFIX = "p1"


def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def bin_index(grade_pct: float) -> int:
    g = clamp(grade_pct, MIN_GRADE, MAX_GRADE)
    # floor((g + 40) / 2 + 0.5); the argument is always >= 0.5 so int() == floor
    return min(NUM_BINS - 1, int((g - MIN_GRADE) / BIN_STEP + 0.5))


def bin_center(i: int) -> float:
    return MIN_GRADE + i * BIN_STEP


def tobler_factor(grade_pct: float) -> float:
    """Tobler's hiking function relative to flat ground (1.0 at 0%, peak ~1.19 at -5%)."""
    return math.exp(-3.5 * abs(grade_pct / 100.0 + 0.05)) / math.exp(-3.5 * 0.05)


class Layer:
    """Per-bin mean pace (s/m) and weight (number of observations).

    Pace, not speed, is averaged: travel time is distance x pace, so the mean of speeds
    would make predicted times too short wherever speed varies (up to ~14% on rough flats).
    Strings and the public API still use speed in m/s.
    """

    def __init__(self) -> None:
        self.paces = [0.0] * NUM_BINS
        self.weights = [0.0] * NUM_BINS

    def add_pace(self, i: int, pace: float, weight: float = 1.0) -> None:
        if weight <= 0:
            return
        new_w = self.weights[i] + weight
        self.paces[i] += (pace - self.paces[i]) * weight / new_w
        self.weights[i] = new_w

    def add(self, i: int, speed: float, weight: float = 1.0) -> None:
        if speed > 0:
            self.add_pace(i, 1.0 / speed, weight)

    def speed(self, i: int) -> float:
        return 1.0 / self.paces[i] if self.paces[i] > 0 else 0.0

    def merge_from(self, other: "Layer", decay: float, cap: float) -> None:
        for i in range(NUM_BINS):
            self.weights[i] *= decay
            self.add_pace(i, other.paces[i], other.weights[i])
            if self.weights[i] > cap:
                self.weights[i] = cap

    def total_weight(self) -> float:
        return sum(self.weights)

    def to_string(self) -> str:
        parts = [MODEL_PREFIX]
        for i in range(NUM_BINS):
            w = int(round(self.weights[i]))
            if w > 0:
                parts.append(f"{int(bin_center(i))}:{self.speed(i):.2f}:{w}")
        return ";".join(parts)

    @classmethod
    def from_string(cls, s: str) -> "Layer":
        layer = cls()
        parts = s.strip().split(";")
        if not parts or parts[0] != MODEL_PREFIX:
            raise ValueError("not a v1 speed model string")
        for p in parts[1:]:
            f = p.split(":")
            if len(f) != 3:
                continue
            layer.add(bin_index(float(f[0])), float(f[1]), float(f[2]))
        return layer


class SpeedGradeModel:
    def __init__(self) -> None:
        self.run = Layer()  # this run, older observations fading (for predicting)
        self.run_total = Layer()  # this run, all observations equal (what gets saved)
        self.stored = Layer()
        self.form = 1.0
        self.prior_cap = PRIOR_CAP
        self._curve: list[float] | None = None
        self._prior_curve: list[float] | None = None

    def invalidate(self) -> None:
        self._curve = None
        self._prior_curve = None

    def has_prior(self) -> bool:
        return self.stored.total_weight() > 0

    def set_run_distance(self, metres: float) -> None:
        """Past runs fade as this one goes on: their cap halves every PRIOR_HALF metres."""
        cap = max(PRIOR_MIN, PRIOR_CAP * 0.5 ** (metres / PRIOR_HALF))
        if abs(cap - self.prior_cap) > 0.01 * self.prior_cap:
            self.prior_cap = cap
            self._curve = None

    def observe(self, grade_pct: float, speed: float) -> None:
        if RUN_DECAY < 1.0:
            for i in range(NUM_BINS):
                self.run.weights[i] *= RUN_DECAY
        self.run.add(bin_index(grade_pct), speed, 1.0)
        self.run_total.add(bin_index(grade_pct), speed, 1.0)
        self._curve = None

    def set_form(self, form: float) -> None:
        if abs(form - self.form) > 0.005:
            self.form = form
            self._curve = None

    def commit_run(self) -> None:
        self.stored.merge_from(self.run_total, STORED_DECAY, STORED_CAP)
        self.discard_run()

    def discard_run(self) -> None:
        self.run = Layer()
        self.run_total = Layer()
        self.prior_cap = PRIOR_CAP
        self.invalidate()

    def build_curve(self, use_run: bool, form: float) -> list[float]:
        """Pace (s/m) per bin. form is a speed ratio, so prior paces are divided by it.

        Without this run the curve is the past alone, so its cap doesn't apply. Slopes with
        too little data follow Tobler's shape from the nearest known slope on each side,
        the closer one counting more."""
        values = [0.0] * NUM_BINS
        valid = [False] * NUM_BINS
        for i in range(NUM_BINS):
            wr = self.run.weights[i] if use_run else 0.0
            pw = self.stored.weights[i]
            pw_eff = min(pw, self.prior_cap) if use_run else pw
            tot = wr + pw_eff
            if tot >= MIN_WEIGHT:
                values[i] = (self.run.paces[i] * wr + self.stored.paces[i] / form * pw_eff) / tot
                valid[i] = True
        for i in range(NUM_BINS):
            if valid[i]:
                continue
            lo = i - 1
            while lo >= 0 and not valid[lo]:
                lo -= 1
            hi = i + 1
            while hi < NUM_BINS and not valid[hi]:
                hi += 1
            c = tobler_factor(bin_center(i))
            total = weight = 0.0
            for j in (lo, hi):
                if 0 <= j < NUM_BINS:  # pace scales as 1 / speed factor
                    w = 1.0 / abs(i - j)
                    total += values[j] * tobler_factor(bin_center(j)) / c * w
                    weight += w
            values[i] = total / weight if weight > 0 else 1.0 / (DEFAULT_FLAT_SPEED * form * c)
        return values

    @staticmethod
    def _interp(curve: list[float], grade_pct: float) -> float:
        """Speed (m/s) from the pace curve, interpolated in pace."""
        p = (clamp(grade_pct, MIN_GRADE, MAX_GRADE) - MIN_GRADE) / BIN_STEP
        i = int(p)
        if i >= NUM_BINS - 1:
            pace = curve[NUM_BINS - 1]
        else:
            pace = curve[i] + (curve[i + 1] - curve[i]) * (p - i)
        return 1.0 / pace if pace < 5.0 else 0.2

    def predict(self, grade_pct: float) -> float:
        if self._curve is None:
            self._curve = self.build_curve(True, self.form)
        return self._interp(self._curve, grade_pct)

    def predict_prior(self, grade_pct: float) -> float:
        if self._prior_curve is None:
            self._prior_curve = self.build_curve(False, 1.0)
        return self._interp(self._prior_curve, grade_pct)


class GradeTracker:
    """Turns 1 Hz (time, distance, altitude) samples into (grade, speed) observations."""

    WINDOW = 60.0  # metres each observation spans, to smooth altitude noise
    EMIT_EVERY = 25.0  # metres between observations
    SIZE = 300  # samples kept: 60 m even on a slow steep climb
    STOP_WINDOW = 60.0  # stopped = less than STOP_DIST metres in the last STOP_WINDOW seconds
    STOP_DIST = 15.0
    STOP_SIZE = 90
    MIN_SPEED = 0.2
    MAX_SPEED = 10.0

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._d = [0.0] * self.SIZE
        self._a = [0.0] * self.SIZE
        self._t = [0.0] * self.SIZE
        self._head = 0
        self._count = 0
        self._sd = [0.0] * self.STOP_SIZE
        self._st = [0.0] * self.STOP_SIZE
        self._shead = 0
        self._scount = 0
        self._last_emit: float | None = None
        self._last_time: float | None = None
        self.moving_time = 0.0
        self.observations = 0
        self.last_grade = 0.0
        self.last_speed = 0.0
        self.last_dist = 0.0

    def is_moving(self, time_s: float, dist: float) -> bool:
        """Records the sample and says whether we moved STOP_DIST in the last STOP_WINDOW s.
        Per-second speed is not used: on steep climbs it often dips to almost zero."""
        self._sd[self._shead] = dist
        self._st[self._shead] = time_s
        self._shead = (self._shead + 1) % self.STOP_SIZE
        if self._scount < self.STOP_SIZE:
            self._scount += 1
        for k in range(1, self._scount):
            idx = (self._shead - 1 - k + self.STOP_SIZE) % self.STOP_SIZE
            if self._st[idx] <= time_s - self.STOP_WINDOW:
                return dist - self._sd[idx] >= self.STOP_DIST
        return True  # not enough history yet

    def update(self, time_s: float, dist: float, alt: float) -> bool:
        """time_s is timer time in seconds. Returns True when an observation was emitted."""
        moving = self.is_moving(time_s, dist)
        if self._last_time is not None:
            dt = time_s - self._last_time
            if 0 < dt < 30 and moving:
                self.moving_time += dt
        self._last_time = time_s
        if not moving:
            return False

        self._d[self._head] = dist
        self._a[self._head] = alt
        self._t[self._head] = self.moving_time
        self._head = (self._head + 1) % self.SIZE
        if self._count < self.SIZE:
            self._count += 1

        if self._last_emit is None:
            self._last_emit = dist
            return False
        if dist - self._last_emit < self.EMIT_EVERY:
            return False

        for k in range(1, self._count):
            idx = (self._head - 1 - k + self.SIZE) % self.SIZE
            if self._d[idx] <= dist - self.WINDOW:
                dd = dist - self._d[idx]
                dt = self.moving_time - self._t[idx]
                self._last_emit = dist
                if dt <= 0:
                    return False
                v = dd / dt
                if v < self.MIN_SPEED or v > self.MAX_SPEED:
                    return False
                self.last_grade = clamp((alt - self._a[idx]) / dd * 100.0, MIN_GRADE, MAX_GRADE)
                self.last_speed = v
                self.last_dist = dd
                self.observations += 1
                return True
        return False


class EtaEstimator:
    """Form factor (today vs. past runs), fatigue factor (the last couple of km vs. the model)
    and time integration over grades."""

    ALPHA = 0.06
    MIN_OBS = 8
    FATIGUE_ALPHA = 0.01  # ~70 observations, ~1.7 km half-life
    FATIGUE_LO = 0.6
    FATIGUE_HI = 1.15
    FORM_RANGE_PRIOR = (0.6, 1.6)  # how far today may differ from past races (short fast races vs. ultras)
    FORM_RANGE_DEFAULT = (0.25, 3.0)  # without past races the starting curve is generic

    def __init__(self, model: SpeedGradeModel) -> None:
        self.model = model
        self.reset()

    def reset(self) -> None:
        self._pred = 0.0
        self._act = 0.0
        self._count = 0
        self._fpred = 0.0
        self._fact = 0.0
        self.fatigue = 1.0  # speed ratio: 0.8 = 20% slower than the model right now
        self.model.set_form(1.0)

    def observe(self, grade_pct: float, speed: float, dist: float) -> None:
        """Call before the observation is added to the model's run layer."""
        act = dist / speed
        # fatigue: how the full model (before seeing this observation) did on it
        fpred = dist / self.model.predict(grade_pct)
        if self._count == 0:
            self._fpred, self._fact = fpred, act
        elif self.FATIGUE_ALPHA > 0:
            self._fpred += (fpred - self._fpred) * self.FATIGUE_ALPHA
            self._fact += (act - self._fact) * self.FATIGUE_ALPHA
        if self._count + 1 >= self.MIN_OBS and self._fact > 0 and self.FATIGUE_ALPHA > 0:
            self.fatigue = clamp(self._fpred / self._fact, self.FATIGUE_LO, self.FATIGUE_HI)

        pred = dist / self.model.predict_prior(grade_pct)
        if self._count == 0:
            self._pred, self._act = pred, act
        else:
            self._pred += (pred - self._pred) * self.ALPHA
            self._act += (act - self._act) * self.ALPHA
        self._count += 1
        if self._count >= self.MIN_OBS and self._act > 0:
            lo, hi = self.FORM_RANGE_PRIOR if self.model.has_prior() else self.FORM_RANGE_DEFAULT
            self.model.set_form(clamp(self._pred / self._act, lo, hi))

    def time_for_grade(self, dist: float, grade_pct: float, scale: float = 1.0) -> float:
        """dist is in course metres; scale is your metres per course metre (see CourseScale)."""
        return dist * scale / (self.model.predict(grade_pct / scale) * self.fatigue)


class CourseScale:
    """Your distance per metre of course, learned while navigating.

    The watch measures more distance than the course file has (switchbacks the course line
    cuts, GPS wobble): about 15% more on the Tor des Géants. Speeds and grades are learned
    in your metres, while distanceToNextPoint is in course metres, so remaining distance is
    multiplied by this ratio and course grades divided by it.
    """

    MIN_PROGRESS = 1000.0  # course metres before the ratio is trusted
    LO = 0.85
    HI = 1.5

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.ratio = 1.0
        self._base_dist: float | None = None
        self._base_dest = 0.0
        self._last_dest: float | None = None

    def update(self, dist: float, dist_dest: float) -> float:
        # start over at the first fix, or when the remaining course jumps up (new course, reroute)
        if self._base_dist is None or (self._last_dest is not None and dist_dest > self._last_dest + 200):
            self._base_dist = dist
            self._base_dest = dist_dest
        self._last_dest = dist_dest
        progress = self._base_dest - dist_dest
        walked = dist - self._base_dist
        if progress >= self.MIN_PROGRESS and walked > 0:
            self.ratio = clamp(walked / progress, self.LO, self.HI)
        return self.ratio

"""The field's ETA algorithm (tools/wpeta) with each of its parts switchable, for the benchmark.

  past      speed-by-grade learned from other runs (what the watch remembers)
  ahead     handled by the harness: the course profile ahead, or one average grade
  raceday   form factor, fatigue factor, fading of older run data, course-distance ratio

observe() gets every sample of the run (time, measured distance, altitude); predict() gets a
scenario.Ctx and returns seconds.

Also evaluated on four races and dropped, because none beat this (see the site's comparison):
a projection of the slowdown with effort over the stretch ahead; a self-check that compares the
predicted and actual time of every 1-3 km stretch and corrects later predictions by the ratio
(it carries one stretch's terrain-specific error into the next, worse in every variant); personal
Naismith-Langmuir; Tobler's hiking function; ITRA km-effort; Minetti's energy cost; and
gradient-boosted trees.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wpeta import model as M  # noqa: E402
from wpeta.model import CourseScale, GradeTracker, Layer, SpeedGradeModel, bin_index  # noqa: E402

SMOOTHING = 0.2


def past_observations(points) -> list[tuple[float, float, float]]:
    """(grade %, speed m/s, window m) of a past race, as the watch computes them."""
    tr, out = GradeTracker(), []
    for p in points:
        if tr.update(p.t, p.dist, p.alt):
            out.append((tr.last_grade, tr.last_speed, tr.last_dist))
    return out


def layer_from_obs(obs) -> Layer:
    layer = Layer()
    for g, v, _ in obs:
        layer.add(bin_index(g), v, 1.0)
    return layer


class HowFar:
    def __init__(self, past: Layer | None = None, raceday: bool = True) -> None:
        self.tracker = GradeTracker()
        self.model = SpeedGradeModel()
        if past is not None:
            self.model.stored = past
        self.raceday = raceday
        self.est = M.EtaEstimator(self.model)
        self.scale = CourseScale()
        self._smooth: float | None = None
        self._wp = None
        self._last_dn = 0.0
        self._decay = M.RUN_DECAY

    def observe(self, t, dist, alt):
        if not self.tracker.update(t, dist, alt):
            return
        g, v, w = self.tracker.last_grade, self.tracker.last_speed, self.tracker.last_dist
        self.model.set_run_distance(dist)
        if self.raceday:
            self.est.observe(g, v, w)
        M.RUN_DECAY = self._decay if self.raceday else 1.0
        self.model.observe(g, v)
        M.RUN_DECAY = self._decay

    def predict(self, ctx):
        if self.raceday:
            self.scale.update(ctx.dist, ctx.dist_dest)
        s = self.scale.ratio if self.raceday else 1.0
        fatigue = self.est.fatigue if self.raceday else 1.0
        raw = max(1.0, sum(length * s / (self.model.predict(g / s) * fatigue) for length, g in ctx.chunks))
        # same display smoothing as the field
        if ctx.wp_index != self._wp or ctx.dist_next > self._last_dn + 50:
            self._smooth = None
        self._wp, self._last_dn = ctx.wp_index, ctx.dist_next
        v = ctx.dist_next / raw
        self._smooth = v if self._smooth is None else self._smooth + (v - self._smooth) * SMOOTHING
        return ctx.dist_next / self._smooth


class _PlainStops(GradeTracker):
    """Stops as a simple moving-time clock sees them: less than 15 m in a minute, with no going
    back over the first minute of a stop. Keeps the baseline as it was before the field learned
    to leave stops out entirely."""

    STILL_TIME = float("inf")
    FORGET_STOPS = False


class AveragePace:
    """The usual watch estimate, for comparison: the distance left at your average moving speed
    so far (longer stops left out). No slopes, no course profile, nothing remembered."""

    def __init__(self) -> None:
        self.tracker = _PlainStops()
        self._start: float | None = None
        self._dist = 0.0

    def observe(self, t, dist, alt):
        if self._start is None:
            self._start = dist
        self.tracker.update(t, dist, alt)
        self._dist = dist

    def speed(self) -> float:
        moved = self._dist - (self._start or 0.0)
        if self.tracker.moving_time < 60 or moved < 100:
            return M.DEFAULT_FLAT_SPEED
        return moved / self.tracker.moving_time

    def predict(self, ctx):
        return max(1.0, ctx.dist_next / self.speed())

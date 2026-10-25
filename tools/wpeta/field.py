"""The data field's per-second logic without the drawing (mirror of WaypointEtaView.compute)."""

from __future__ import annotations

from .model import CourseScale, EtaEstimator, GradeTracker, Layer, SpeedGradeModel, clamp
from .profile import ProfileMatcher

MIN_OBS_TO_COMMIT = 20


def shown_seconds(s: float) -> int:
    """The time as the watch shows it (WpUtil.etaText): 30-minute steps from four hours out,
    15-minute steps from two, 5-minute steps from one, whole minutes from 5 minutes out, seconds
    in the last 5."""
    s = max(0, int(round(s)))
    step = 1800 if s >= 13500 else 900 if s >= 6750 else 300 if s >= 3450 else 60 if s >= 300 else 1
    return (s + step // 2) // step * step
SMOOTHING = 0.2


class FieldLogic:
    def __init__(
        self,
        stored: Layer | None = None,
        profile: tuple[int, list[tuple[str, int, list[int]]]] | None = None,
    ) -> None:
        self.model = SpeedGradeModel()
        if stored is not None:
            self.model.stored = stored
        self.tracker = GradeTracker()
        self.estimator = EtaEstimator(self.model)
        self.scale = CourseScale()
        self.profile = ProfileMatcher(*profile) if profile else None
        self.using_profile = False
        self.shown_name: str | None = None  # the point the countdown is for
        self.then_name: str | None = None  # the main profile point after it
        self.then_leg: int | None = None  # its leg's moving time, from leaving the point before it
        self.then2_name: str | None = None  # and the main point after that
        self.then2_leg: int | None = None
        self.via_name: str | None = None  # the next minor profile point on the way
        self.via_eta: int | None = None
        self._smooth_speed: float | None = None
        self._last_name: str | None = None
        self._last_dist = 0.0

    def compute(
        self,
        timer_s: float | None,
        timer_on: bool,
        dist: float | None,
        alt: float | None,
        dist_next: float | None,
        name: str | None,
        dist_dest: float | None,
        elev_next: float | None,
    ) -> int | None:
        if timer_on and None not in (timer_s, dist, alt):
            if self.tracker.update(timer_s, dist, alt):
                g, v, d = self.tracker.last_grade, self.tracker.last_speed, self.tracker.last_dist
                self.model.set_run_distance(dist)
                self.estimator.observe(g, v, d)
                self.model.observe(g, v)

        self.shown_name = name
        if dist_next is None or dist_next <= 0:
            self._smooth_speed = None
            self.then_name = self.then_leg = self.then2_name = self.then2_leg = self.via_name = self.via_eta = None
            return None

        if timer_on and dist is not None and dist_dest is not None:
            self.scale.update(dist, dist_dest)
        scale = self.scale.ratio

        if self.profile is not None and self.profile.update(name, dist_next, dist_dest, dist, scale):
            # the next profile point, which may come before the watch's next point
            name = self.profile.target_name(name)
            dist_next = self.profile.target_dist
            raw = self.profile.target_time(self.estimator, scale)
            self.using_profile = True
        else:
            grade = 0.0
            if alt is not None and elev_next is not None:
                grade = clamp((elev_next - alt) / dist_next * 100.0, -40.0, 40.0)
            raw = self.estimator.time_for_grade(dist_next, grade, scale)
            self.using_profile = False

        if name != self._last_name or dist_next > self._last_dist + 50:
            self._smooth_speed = None
        self._last_name = name
        self._last_dist = dist_next

        self.shown_name = name
        v = max(dist_next, 1.0) / raw
        self._smooth_speed = v if self._smooth_speed is None else self._smooth_speed + (v - self._smooth_speed) * SMOOTHING
        eta = int(max(dist_next, 1.0) / self._smooth_speed + 0.5)

        self.then_name = self.then_leg = self.then2_name = self.then2_leg = self.via_name = self.via_eta = None
        if self.using_profile and self.profile.via is not None:
            self.via_name = self.profile.following_name(self.profile.via)
            self.via_eta = int(self.profile.via_time(self.estimator, scale) + 0.5)
        if self.using_profile:
            i = self.profile.following()
            if i is not None:
                self.then_name = self.profile.following_name(i)
                # leg times: stops at the checkpoints in between can't be known
                t1 = self.profile.following_time(i, self.estimator, scale)
                self.then_leg = int(t1 + 0.5)
                i2 = self.profile.following_after(i)
                if i2 is not None:
                    self.then2_name = self.profile.following_name(i2)
                    self.then2_leg = int(self.profile.following_time(i2, self.estimator, scale) - t1 + 0.5)
        return eta

    def timer_reset(self) -> bool:
        """Activity ended. Returns True when this run was merged into the stored model."""
        committed = False
        if self.tracker.observations >= MIN_OBS_TO_COMMIT:
            self.model.commit_run()
            committed = True
        else:
            self.model.discard_run()
        self.tracker.reset()
        self.estimator.reset()
        self.scale.reset()
        if self.profile is not None:
            self.profile.reset()
        self._smooth_speed = None
        return committed

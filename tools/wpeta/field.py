"""The data field's per-second logic without the drawing (mirror of WaypointEtaView.compute)."""

from __future__ import annotations

from .model import CourseScale, EtaEstimator, GradeTracker, Layer, SpeedGradeModel, clamp
from .profile import ProfileMatcher

MIN_OBS_TO_COMMIT = 20
SMOOTHING = 0.2


class FieldLogic:
    def __init__(
        self,
        imported: Layer | None = None,
        stored: Layer | None = None,
        profile: tuple[int, list[tuple[str, int, list[int]]]] | None = None,
    ) -> None:
        self.model = SpeedGradeModel()
        if imported is not None:
            self.model.imported = imported
        if stored is not None:
            self.model.stored = stored
        self.tracker = GradeTracker()
        self.estimator = EtaEstimator(self.model)
        self.scale = CourseScale()
        self.profile = ProfileMatcher(*profile) if profile else None
        self.using_profile = False
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
                self.estimator.observe(g, v, d)
                self.model.observe(g, v)

        if dist_next is None or dist_next <= 0:
            self._smooth_speed = None
            return None

        if timer_on and dist is not None and dist_dest is not None:
            self.scale.update(dist, dist_dest)
        scale = self.scale.ratio

        if self.profile is not None and self.profile.update(name, dist_next, dist_dest):
            _, length, grades = self.profile.entry()
            raw = self.estimator.time_for_tail(grades, length, self.profile.step, dist_next, scale)
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

        v = dist_next / raw
        self._smooth_speed = v if self._smooth_speed is None else self._smooth_speed + (v - self._smooth_speed) * SMOOTHING
        return int(dist_next / self._smooth_speed + 0.5)

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

import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from synth import samples, write_fit, write_gpx  # noqa: E402
from wpeta.field import FieldLogic  # noqa: E402
from wpeta.learn import layer_from_files  # noqa: E402
from wpeta.model import (  # noqa: E402
    DEFAULT_FLAT_SPEED,
    EtaEstimator,
    Layer,
    SpeedGradeModel,
    bin_index,
    tobler_factor,
)
from wpeta.profile import ProfileMatcher, best_profile, names_match, parse_profile  # noqa: E402
from wpeta.readers import read_course, read_track  # noqa: E402

HILLY = [(2000, 0, 3.0), (1500, 10, 2.0), (1500, -10, 3.4), (1000, 0, 3.0)]


@pytest.fixture
def hilly_fit(tmp_path):
    p = tmp_path / "run.fit"
    write_fit(p, samples(HILLY))
    return p


@pytest.fixture
def hilly_gpx(tmp_path):
    p = tmp_path / "run.gpx"
    write_gpx(p, samples(HILLY))
    return p


# --- readers -------------------------------------------------------------------------

def test_fit_reader_round_trip(hilly_fit):
    recs = samples(HILLY)
    pts = read_track(hilly_fit)
    assert len(pts) == len(recs)
    assert pts[-1].dist == pytest.approx(6000, abs=0.01)
    assert pts[-1].alt == pytest.approx(300, abs=0.3)
    assert max(p.alt for p in pts) == pytest.approx(450, abs=0.3)
    assert pts[10].speed == pytest.approx(3.0)


def test_gpx_reader_computes_distance(hilly_gpx):
    pts = read_track(hilly_gpx)
    assert pts[-1].dist == pytest.approx(6000, rel=0.002)
    assert pts[-1].t == pytest.approx(samples(HILLY)[-1]["t"], abs=0.01)


# --- learning ------------------------------------------------------------------------

@pytest.mark.parametrize("fixture", ["hilly_fit", "hilly_gpx"])
def test_learn_recovers_speed_per_grade(fixture, request):
    # constant speed per segment, so arithmetic and harmonic means agree
    layer = layer_from_files([request.getfixturevalue(fixture)])
    assert layer.speed(bin_index(0)) == pytest.approx(3.0, abs=0.05)
    assert layer.speed(bin_index(10)) == pytest.approx(2.0, abs=0.05)
    assert layer.speed(bin_index(-10)) == pytest.approx(3.4, abs=0.05)
    assert layer.weights[bin_index(10)] >= 50


def test_model_string_round_trip():
    layer = Layer()
    layer.add(bin_index(0), 3.0, 40)
    layer.add(bin_index(-6), 3.3, 7)
    again = Layer.from_string(layer.to_string())
    assert again.to_string() == "v1;-6:3.30:7;0:3.00:40"
    with pytest.raises(ValueError):
        Layer.from_string("p1;50")


def test_cli_prints_model(hilly_fit):
    out = subprocess.run(
        [sys.executable, str(TOOLS / "fit_to_speed_model.py"), "-q", str(hilly_fit)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert out.startswith("v1;")
    assert "10:2.00:" in out


# --- model ---------------------------------------------------------------------------

def test_default_curve_without_data():
    m = SpeedGradeModel()
    assert m.predict(0) == pytest.approx(DEFAULT_FLAT_SPEED)
    assert m.predict(10) == pytest.approx(DEFAULT_FLAT_SPEED * tobler_factor(10))


def test_interpolates_and_extrapolates():
    m = SpeedGradeModel()
    m.imported.add(bin_index(0), 3.0, 30)
    m.imported.add(bin_index(10), 2.0, 30)
    # interpolation is in pace: 1/3 s/m at 0%, 1/2 s/m at 10%
    assert m.predict(4) == pytest.approx(1 / 0.4)
    assert m.predict(5) == pytest.approx(1 / (1 / 3 + 0.5 * (1 / 6)))  # between bins
    assert m.predict(20) == pytest.approx(2.0 * tobler_factor(20) / tobler_factor(10))
    assert m.predict(-10) == pytest.approx(3.0 * tobler_factor(-10) / tobler_factor(0))


def test_run_data_blends_with_capped_prior(monkeypatch):
    monkeypatch.setattr("wpeta.model.RUN_DECAY", 1.0)
    m = SpeedGradeModel()
    m.stored.add(bin_index(0), 3.0, 200)
    for _ in range(20):
        m.observe(0, 2.0)
    # prior counts as 20 observations at most, so 20 run observations weigh the same
    assert m.predict(0) == pytest.approx(1 / ((1 / 3 + 1 / 2) / 2))


def test_form_factor_scales_prior_only():
    m = SpeedGradeModel()
    m.imported.add(bin_index(0), 3.0, 30)
    est = EtaEstimator(m)
    for _ in range(40):
        est.observe(0, 2.7, 60)  # 10% slower than past runs
    assert m.form == pytest.approx(0.9, abs=0.001)
    assert m.predict(0) == pytest.approx(2.7, abs=0.001)


def test_form_factor_clamped_with_prior():
    m = SpeedGradeModel()
    m.imported.add(bin_index(0), 3.0, 30)
    est = EtaEstimator(m)
    for _ in range(40):
        est.observe(0, 1.2, 60)  # 60% slower than past runs: beyond the 0.6 floor
    assert m.form == pytest.approx(0.6)


def test_form_factor_rescales_default_curve():
    m = SpeedGradeModel()
    est = EtaEstimator(m)
    for _ in range(40):
        est.observe(0, 1.4, 60)  # hiking pace
    assert m.predict(0) == pytest.approx(1.4, abs=0.01)


def test_commit_run_decays_stored():
    # the saved run is the unfaded copy: all 50 observations count
    m = SpeedGradeModel()
    m.stored.add(bin_index(0), 3.0, 100)
    for _ in range(50):
        m.observe(0, 2.0)
    m.commit_run()
    assert m.stored.weights[bin_index(0)] == pytest.approx(135)
    assert m.stored.paces[bin_index(0)] == pytest.approx((85 / 3.0 + 50 / 2.0) / 135)
    assert m.run.total_weight() == 0


def test_profile_time_to_point():
    m = SpeedGradeModel()
    m.imported.add(bin_index(0), 3.0, 30)
    m.imported.add(bin_index(10), 2.0, 30)
    est = EtaEstimator(m)
    # segment 230 m: chunks 100, 100, 30 (the 30 m chunk is next to the waypoint)
    p = ProfileMatcher(100, [("X", 230, [100, 100, 0])])
    assert p.update("X", 230, 230, 0.0)
    assert p.remaining_time(230, est, 1.0) == pytest.approx(200 / 2.0 + 30 / 3.0)
    assert p.update("X", 80, 80, 150.0)
    assert p.remaining_time(80, est, 1.0) == pytest.approx(50 / 2.0 + 30 / 3.0)
    # longer than the profile: the extra metres at the first grade
    assert p.remaining_time(300, est, 1.0) == pytest.approx(270 / 2.0 + 30 / 3.0)


# --- course profile ------------------------------------------------------------------

COURSE = [(1500, 0, 3), (1500, 8, 3), (2000, -5, 3)]
POINTS = [("Climb", 1500), ("Water", 3000)]


def _check_course_entries(text):
    step, entries = parse_profile(text)
    names = [e[0] for e in entries]
    assert names == ["Climb", "Water", "*"]
    assert [e[1] for e in entries] == [1500, 1500, 2000]
    assert all(g == 0 for g in entries[0][2])
    assert all(g == pytest.approx(80, abs=10) for g in entries[1][2])
    assert all(g == pytest.approx(-50, abs=10) for g in entries[2][2])
    return step, entries


def test_course_profile_from_fit(tmp_path):
    p = tmp_path / "course.fit"
    write_fit(p, samples(COURSE), POINTS, file_type=6)
    pts, cps = read_course(p)
    step, text = best_profile(pts, cps, 4000)
    assert step == 25
    _check_course_entries(text)


def test_course_profile_from_gpx_waypoints(tmp_path):
    p = tmp_path / "course.gpx"
    write_gpx(p, samples(COURSE), POINTS, with_time=False)
    pts, cps = read_course(p)
    assert [c.name for c in cps] == ["Climb", "Water"]
    assert cps[1].dist == pytest.approx(3000, abs=5)
    _, text = best_profile(pts, cps, 4000, step=100)
    step, entries = parse_profile(text)
    assert step == 100 and [e[0] for e in entries] == ["Climb", "Water", "*"]


def test_profile_step_grows_to_fit(tmp_path):
    p = tmp_path / "course.fit"
    write_fit(p, samples(COURSE), POINTS, file_type=6)
    pts, cps = read_course(p)
    step, text = best_profile(pts, cps, 250)
    assert step == 100 and len(text) <= 250


def test_names_match():
    assert names_match("Water", "water")
    assert names_match("Rifugio Gonella", "Rifugio Gon")
    assert not names_match("Wa", "Water")
    assert not names_match("Climb", "Water")


def test_matcher_follows_repeated_names():
    entries = [("Water", 1000, [0]), ("Water", 2000, [0]), ("*", 500, [0])]
    m = ProfileMatcher(100, entries)
    assert m.update("Water", 1000, 3500) and m.current == 0
    assert m.update("Water", 400, 2900) and m.current == 0
    # passed the first Water: same name, distance jumps up
    assert m.update("Water", 2000, 2500) and m.current == 1
    # finish: no name, next point is the destination
    assert m.update(None, 500, 500) and m.current == 2


def test_matcher_rejects_too_long_distance():
    m = ProfileMatcher(100, [("Climb", 1000, [0])])
    assert not m.update("Climb", 2000, 2000)
    assert m.mismatched


def test_matcher_places_unknown_point():
    m = ProfileMatcher(100, [("Climb", 1000, [0])])
    assert m.update("Left turn", 300, 900, 100.0)  # 100 m in, from the distance to the finish
    assert m.current is None and m.loc == 400
    assert not m.mismatched


def test_matcher_skips_points_the_watch_lacks():
    m = ProfileMatcher(100, [("A", 1000, [0]), ("B", 1000, [0]), ("C", 1000, [0])])
    assert m.update("C", 3000, 3000) and m.current == 2


def test_matcher_picks_the_repeated_name_that_fits():
    m = ProfileMatcher(100, [("Water", 1000, [0]), ("Hut", 3000, [0]), ("Water", 3000, [0])])
    assert m.update("Bridge", 4000, 7000, 0.0) and m.loc == 4000
    # the first Water is behind you: the second one fits where you are
    assert m.update("Water", 3000, 3000, 4000.0) and m.current == 2
    assert not m.mismatched


def test_matcher_learns_a_longer_watch_course():
    # the watch's course is 10% longer than the profile's
    m = ProfileMatcher(100, [("A", 5000, [0]), ("B", 5000, [0]), ("C", 5000, [0])])
    # 4 km in on the profile, 4.4 km on the watch's course
    assert m.update("A", 1100, 12100, 4400.0) and m.current == 0
    assert abs(m.ratio - 1 / 1.1) < 1e-9
    # at A, a point the profile lacks is 2.2 watch km ahead: 2 km after A on the profile
    assert m.update("Hut", 2200, 11000, 5500.0) and m.current is None
    assert abs(m.loc - 7000) < 1e-6


def test_matcher_time_crosses_entries():
    from wpeta.model import EtaEstimator, SpeedGradeModel

    est = EtaEstimator(SpeedGradeModel())
    m = ProfileMatcher(100, [("A", 1000, [0] * 10), ("B", 1000, [0] * 10)])
    assert m.update("B", 2000, 2000)
    assert abs(m.remaining_time(2000, est, 1.0) - est.time_for_grade(2000, 0.0)) < 1e-6


# --- the field as a whole ------------------------------------------------------------

def test_field_shows_nothing_off_course():
    f = FieldLogic()
    assert f.compute(1.0, True, 10.0, 300.0, None, None, None, None) is None


def test_field_commits_only_real_runs():
    f = FieldLogic()
    for i in range(100):
        f.compute(float(i), True, i * 3.0, 300.0, None, None, None, None)
    assert not f.timer_reset()  # 300 m: too few observations
    for i in range(1000):
        f.compute(float(i), True, i * 3.0, 300.0, None, None, None, None)
    assert f.timer_reset()
    assert f.model.stored.speed(bin_index(0)) == pytest.approx(3.0)


def _replay(pts, every, imported, use_profile):
    from replay import replay, virtual_waypoints
    from wpeta.profile import Elevation, build_entries
    from wpeta.readers import CoursePoint

    wps = virtual_waypoints(pts, every)
    elev = Elevation(pts)
    profile = (50, build_entries(pts, [CoursePoint(w.name, w.act_dist) for w in wps], 50)) if use_profile else None
    return replay(pts, wps, imported, profile, lambda wp: elev.at(wp.course_dist))


def test_replay_accuracy_with_learned_model(hilly_fit):
    layer = layer_from_files([hilly_fit])
    pts = read_track(hilly_fit)
    with_profile = _replay(pts, 1500, layer, use_profile=True)
    errs = [abs(e[1]) for c in with_profile.values() for e in c]
    assert errs and max(errs) < 20  # seconds

    # without any prior and with average grade, it still lands within a couple of minutes
    cold = _replay(pts, 1500, None, use_profile=False)
    assert max(abs(e[1]) for c in cold.values() for e in c) < 180


def test_replay_places_course_points_on_track(tmp_path):
    from replay import place_course_points

    course = tmp_path / "course.gpx"
    write_gpx(course, samples(COURSE), POINTS, with_time=False)
    run = tmp_path / "run.gpx"
    # the activity covers only the second half of the course, like one race section
    recs = [r for r in samples(COURSE) if r["dist"] >= 2000]
    write_gpx(run, recs)
    course_pts, cps = read_course(course)
    wps = place_course_points(read_track(run), course_pts, cps)
    assert [w.name for w in wps] == ["Water"]
    assert wps[0].course_dist == pytest.approx(3000, abs=5)
    assert wps[0].act_dist == pytest.approx(1000, abs=5)


def test_tracker_slow_climb_counts_as_moving():
    # 0.4 m/s up 30%: below the old per-second cut-off, but still moving
    from wpeta.model import GradeTracker

    t = GradeTracker()
    for i in range(600):
        t.update(float(i), i * 0.4, 300.0 + i * 0.12)
    assert t.moving_time == pytest.approx(599.0)
    assert t.observations > 0 and t.last_speed == pytest.approx(0.4)


def test_tracker_excludes_stops():
    # 300 s moving, 600 s standing still: at most STOP_WINDOW of the stop counts
    from wpeta.model import GradeTracker

    t = GradeTracker()
    for i in range(900):
        t.update(float(i), min(i, 300) * 1.0, 300.0)
    assert t.moving_time < 300 + 60


def test_layer_averages_pace_not_speed():
    layer = Layer()
    layer.add(bin_index(0), 1.0)
    layer.add(bin_index(0), 3.0)
    # 1 km at each speed takes 1000 s + 333 s: the right average speed is 2000 / 1333
    assert layer.speed(bin_index(0)) == pytest.approx(1.5)


def test_gpx_waypoints_off_the_track_are_dropped(tmp_path):
    # race files often carry every waypoint of the whole race
    p = tmp_path / "course.gpx"
    write_gpx(p, samples(COURSE), POINTS)
    text = p.read_text().replace("<trk>", '<wpt lat="46.5" lon="7.5"><name>Other stage</name></wpt><trk>')
    p.write_text(text)
    skipped = []
    _, cps = read_course(p, skipped=skipped)
    assert [c.name for c in cps] == ["Climb", "Water"]
    assert skipped == ["Other stage"]


def test_course_scale():
    from wpeta.model import CourseScale

    cs = CourseScale()
    assert cs.update(0.0, 10000.0) == 1.0
    assert cs.update(500.0, 9600.0) == 1.0  # not enough progress yet
    assert cs.update(1150.0, 9000.0) == pytest.approx(1.15)
    # reroute: remaining course jumps up, start over
    assert cs.update(1200.0, 12000.0) == pytest.approx(1.15)
    assert cs.update(2400.0, 11000.0) == pytest.approx(1.2)


def test_time_scales_distance_and_grade():
    m = SpeedGradeModel()
    m.imported.add(bin_index(0), 3.0, 30)
    m.imported.add(bin_index(10), 2.0, 30)
    est = EtaEstimator(m)
    # 1000 course metres at 11.5% course grade = 1150 of your metres at 10%
    assert est.time_for_grade(1000, 11.5, 1.15) == pytest.approx(1150 / 2.0)
    p = ProfileMatcher(1000, [("X", 1000, [115])])
    assert p.update("X", 1000, 1000)
    assert p.remaining_time(1000, est, 1.15) == pytest.approx(1150 / 2.0)


def test_older_run_observations_fade():
    from wpeta.model import RUN_DECAY

    m = SpeedGradeModel()
    for _ in range(200):
        m.observe(0, 3.0)  # fresh
    for _ in range(200):
        m.observe(0, 2.0)  # tired
    w_fresh = 200 * RUN_DECAY**200  # roughly: what's left of the fresh block
    assert m.predict(0) < 2.2  # dominated by the recent, tired pace
    assert m.run_total.weights[bin_index(0)] == pytest.approx(400)
    assert w_fresh < 100


def test_fatigue_factor_tracks_recent_slowdown(monkeypatch):
    monkeypatch.setattr("wpeta.model.RUN_DECAY", 1.0)
    m = SpeedGradeModel()
    m.imported.add(bin_index(0), 3.0, 30)
    est = EtaEstimator(m)
    for _ in range(100):
        est.observe(0, 3.0, 60)
        m.observe(0, 3.0)
    assert est.fatigue == pytest.approx(1.0, abs=0.01)
    for _ in range(300):
        est.observe(0, 2.4, 60)
        m.observe(0, 2.4)
    assert est.fatigue < 0.97  # still slower than the (lagging) model says
    assert est.time_for_grade(1000, 0) > 1000 / m.predict(0)

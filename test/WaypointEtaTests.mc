import Toybox.Lang;
import Toybox.System;
import Toybox.Test;

// Same cases as tools/tests/test_tools.py, run on the watch code (monkeyc -t, then the simulator).

// helper, not a test: (:test) would make the runner call it
(:debug)
function near(a as Float, b as Float, tol as Float) as Boolean {
    return (a - b).abs() <= tol;
}

(:test)
function testBinIndex(logger as Test.Logger) as Boolean {
    Test.assertEqual(Wp.binIndex(0.0), 20);
    Test.assertEqual(Wp.binIndex(-40.0), 0);
    Test.assertEqual(Wp.binIndex(55.0), 40);
    Test.assertEqual(Wp.binIndex(0.9), 20);
    Test.assertEqual(Wp.binIndex(1.1), 21);
    return true;
}

(:test)
function testFormatDuration(logger as Test.Logger) as Boolean {
    var a = WpUtil.etaText(65);
    Test.assert(a[0].equals("1:05") && a[1].equals("min"));
    a = WpUtil.etaText(2530);  // 42 min 10 s
    Test.assert(a[0].equals("42") && a[1].equals("min"));
    a = WpUtil.etaText(3725);  // 1 h 2 min: 5-minute steps from an hour out
    Test.assert(a[0].equals("1:00") && a[1].equals("h"));
    a = WpUtil.etaText(7890);  // 2 h 11.5 min: 15-minute steps from two hours out
    Test.assert(a[0].equals("2:15") && a[1].equals("h"));
    a = WpUtil.etaText(6600);  // 1 h 50 min: still 5-minute steps
    Test.assert(a[0].equals("1:50") && a[1].equals("h"));
    Test.assert(WpUtil.etaHm(10000).equals("2:45"));
    Test.assert(WpUtil.etaHm(16000).equals("4:30"));  // 30-minute steps from four hours out
    Test.assert(WpUtil.reliability(2699) == 0 && WpUtil.reliability(2700) == 1);  // the dot: green, yellow
    Test.assert(WpUtil.reliability(7199) == 1 && WpUtil.reliability(7200) == 2);  // yellow, red
    Test.assert(WpUtil.etaHm(2700).equals("0:45"));
    Test.assert(WpUtil.etaHm(4740).equals("1:20"));  // 1:19 rounds to 5 minutes from an hour out
    a = WpUtil.etaText(3449);  // just under: whole minutes
    Test.assert(a[0].equals("57") && a[1].equals("min"));
    return true;
}

(:test)
function testDefaultCurve(logger as Test.Logger) as Boolean {
    var m = new SpeedGradeModel();
    Test.assert(near(m.predict(0.0), Wp.DEFAULT_FLAT_SPEED, 0.001));
    Test.assert(near(m.predict(10.0), Wp.DEFAULT_FLAT_SPEED * Wp.toblerFactor(10.0), 0.001));
    return true;
}

(:test)
function testInterpolation(logger as Test.Logger) as Boolean {
    var m = new SpeedGradeModel();
    m.stored.add(Wp.binIndex(0.0), 3.0, 30.0);
    m.stored.add(Wp.binIndex(10.0), 2.0, 30.0);
    // unseen slopes follow Tobler's shape from both sides, the closer side counting more
    var t4 = Wp.toblerFactor(4.0);
    var pace4 = ((1.0 / 3.0) * Wp.toblerFactor(0.0) / t4 / 2.0 + 0.5 * Wp.toblerFactor(10.0) / t4 / 3.0) / (1.0 / 2.0 + 1.0 / 3.0);
    Test.assert(near(m.predict(4.0), 1.0 / pace4, 0.001));
    return true;
}

(:test :full)
function testSteepClimbFromGentlerOne(logger as Test.Logger) as Boolean {
    var m = new SpeedGradeModel();
    m.stored.add(Wp.binIndex(0.0), 3.0, 30.0);
    m.stored.add(Wp.binIndex(10.0), 2.0, 30.0);
    // steep climbs with no data of their own climb as many metres per hour as the 10% slope
    Test.assert(near(m.predict(20.0), 2.0 * 10.0 / 20.0, 0.001));
    // without the course profile they keep Tobler's shape
    m.setSteepPool(false);
    Test.assert(near(m.predict(20.0), 2.0 * Wp.toblerFactor(20.0) / Wp.toblerFactor(10.0), 0.001));
    return true;
}

(:test :full)
function testSteepClimbsShareOneClimbRate(logger as Test.Logger) as Boolean {
    var m = new SpeedGradeModel();
    m.stored.add(Wp.binIndex(0.0), 3.0, 30.0);
    m.stored.add(Wp.binIndex(14.0), 0.8, 30.0);
    m.stored.add(Wp.binIndex(20.0), 0.5, 5.0);
    m.stored.add(Wp.binIndex(30.0), 0.4, 5.0);
    // seconds per metre climbed, over every steep slope with data, by weight
    var vp = (100.0 / (14.0 * 0.8) * 30.0 + 100.0 / (20.0 * 0.5) * 5.0 + 100.0 / (30.0 * 0.4) * 5.0) / 40.0;
    // a slope with enough data keeps its own pace, the others climb at the pooled rate
    Test.assert(near(m.predictPrior(14.0), 0.8, 0.001));
    Test.assert(near(m.predictPrior(20.0), 100.0 / (vp * 20.0), 0.001));
    Test.assert(near(m.predictPrior(24.0), 100.0 / (vp * 24.0), 0.001));
    Test.assert(near(m.predictPrior(40.0), 100.0 / (vp * 40.0), 0.001));
    Test.assert(near(m.predictPrior(0.0), 3.0, 0.001));
    return true;
}

(:test :lite)
function testLiteKeepsToblerOnSteepClimbs(logger as Test.Logger) as Boolean {
    var m = new SpeedGradeModel();
    m.stored.add(Wp.binIndex(0.0), 3.0, 30.0);
    m.stored.add(Wp.binIndex(10.0), 2.0, 30.0);
    Test.assert(near(m.predict(20.0), 2.0 * Wp.toblerFactor(20.0) / Wp.toblerFactor(10.0), 0.001));
    return true;
}

(:test)
function testPriorCap(logger as Test.Logger) as Boolean {
    var m = new SpeedGradeModel();
    m.stored.add(Wp.binIndex(0.0), 3.0, 200.0);
    m.run.add(Wp.binIndex(0.0), 2.0, 20.0);
    m.invalidate();
    // past runs count as 10 observations at most at the start: paces (20 x 1/2 + 10 x 1/3) / 30
    Test.assert(near(m.predict(0.0), 2.25, 0.001));
    // and half that after 10 km of this run
    m.setRunDistance(10000.0);
    Test.assert(near(m.predict(0.0), 1.0 / ((10.0 + 5.0 / 3.0) / 25.0), 0.001));
    // the past alone keeps all its weight
    Test.assert(near(m.predictPrior(0.0), 3.0, 0.001));
    return true;
}

(:test)
function testFormFactor(logger as Test.Logger) as Boolean {
    var m = new SpeedGradeModel();
    m.stored.add(Wp.binIndex(0.0), 3.0, 30.0);
    var est = new EtaEstimator(m);
    for (var i = 0; i < 40; i++) {
        est.observe(0.0, 2.7, 60.0);
    }
    Test.assert(near(m.form, 0.9, 0.001));
    Test.assert(near(m.predict(0.0), 2.7, 0.001));
    return true;
}

(:test :full)
function testProfileTime(logger as Test.Logger) as Boolean {
    var m = new SpeedGradeModel();
    m.stored.add(Wp.binIndex(0.0), 3.0, 30.0);
    m.stored.add(Wp.binIndex(10.0), 2.0, 30.0);
    var est = new EtaEstimator(m);
    // segment 230 m: chunks 100, 100, 30 (the 30 m chunk is next to the waypoint)
    var p = new CourseProfile("p1;100;X|230|100,100,0").parseAll();
    Test.assert(p.update("X", 230.0, 230.0, 0.0, 1.0));
    Test.assert(near(p.remainingTime(230.0, est, 1.0), 200.0 / 2.0 + 30.0 / 3.0, 0.01));
    Test.assert(p.update("X", 80.0, 80.0, 150.0, 1.0));
    Test.assert(near(p.remainingTime(80.0, est, 1.0), 50.0 / 2.0 + 30.0 / 3.0, 0.01));
    Test.assert(near(p.remainingTime(300.0, est, 1.0), 270.0 / 2.0 + 30.0 / 3.0, 0.01));
    return true;
}

(:test)
function testTrackerRecoversGrade(logger as Test.Logger) as Boolean {
    var t = new GradeTracker();
    var got = false;
    // 2 m/s up a 10% grade, 1 Hz
    for (var i = 0; i < 200; i++) {
        if (t.update(i.toFloat(), i * 2.0, 300.0 + i * 0.2)) {
            got = true;
            Test.assert(near(t.lastGrade, 10.0, 0.01));
            Test.assert(near(t.lastSpeed, 2.0, 0.01));
        }
    }
    Test.assert(got);
    return true;
}

(:test)
function testTrackerSlowClimbIsMoving(logger as Test.Logger) as Boolean {
    // 0.4 m/s up 30%: below the old per-second cut-off, but still moving
    var t = new GradeTracker();
    for (var i = 0; i < 600; i++) {
        t.update(i.toFloat(), i * 0.4, 300.0 + i * 0.12);
    }
    Test.assert(near(t.movingTime, 599.0, 0.01));
    Test.assert(t.observations > 0 && near(t.lastSpeed, 0.4, 0.01));
    return true;
}

(:test)
function testTrackerStop(logger as Test.Logger) as Boolean {
    // 300 s moving, 600 s standing still: none of the stop counts
    var t = new GradeTracker();
    for (var i = 0; i < 900; i++) {
        t.update(i.toFloat(), (i < 300 ? i : 300) * 1.0, 300.0);
    }
    Test.assert(near(t.movingTime, 300.0, 2.0));
    return true;
}

(:test)
function testTrackerDriftNotLearned(logger as Test.Logger) as Boolean {
    // GPS drift while standing: 0.4 m/s with the altitude still is no observation, but 0.4 m/s
    // up 30% is one
    var t = new GradeTracker();
    for (var i = 0; i < 600; i++) {
        t.update(i.toFloat(), i * 0.4, 300.0);
    }
    Test.assert(t.observations == 0);
    t = new GradeTracker();
    for (var i = 0; i < 600; i++) {
        t.update(i.toFloat(), i * 0.4, 300.0 + i * 0.12);
    }
    Test.assert(t.observations > 0);
    return true;
}

(:test)
function testTrackerShortStop(logger as Test.Logger) as Boolean {
    // 2.5 m/s, a 20 s stop to read the watch at 600 m, then on: no slow observation after it
    var t = new GradeTracker();
    var d = 0.0;
    var slowest = 100.0;
    for (var i = 0; i < 700; i++) {
        if (i < 240 || i >= 260) {
            d += 2.5;
        }
        if (t.update(i.toFloat(), d, 300.0) && t.lastSpeed < slowest) {
            slowest = t.lastSpeed;
        }
    }
    Test.assert(near(t.movingTime, 679.0, 2.0));
    Test.assert(near(slowest, 2.5, 0.05));
    return true;
}

(:test)
function testFatigueNotStuckOnSlowStart(logger as Test.Logger) as Boolean {
    // the first 250 m at half speed (a warm-up, a crowded start), then 1 km at the usual pace
    var m = new SpeedGradeModel();
    m.stored.add(Wp.binIndex(0.0), 3.0, 30.0);
    var est = new EtaEstimator(m);
    for (var i = 0; i < 10; i++) {
        est.observe(0.0, 1.5, 25.0);
        m.observe(0.0, 1.5);
    }
    for (var i = 0; i < 40; i++) {
        est.observe(0.0, 3.0, 25.0);
        m.observe(0.0, 3.0);
    }
    Test.assert(est.fatigue > 0.85);
    return true;
}

(:test)
function testLayerAveragesPace(logger as Test.Logger) as Boolean {
    var l = new ModelLayer();
    l.add(20, 1.0, 1.0);
    l.add(20, 3.0, 1.0);
    Test.assert(near(l.speed(20), 1.5, 0.001));
    return true;
}

(:test)
function testCourseScale(logger as Test.Logger) as Boolean {
    var cs = new CourseScale();
    Test.assert(near(cs.update(0.0, 10000.0), 1.0, 0.001));
    Test.assert(near(cs.update(500.0, 9600.0), 1.0, 0.001));
    Test.assert(near(cs.update(1150.0, 9000.0), 1.15, 0.001));
    Test.assert(near(cs.update(1200.0, 12000.0), 1.15, 0.001));  // reroute: start over
    Test.assert(near(cs.update(2400.0, 11000.0), 1.2, 0.001));
    // a cut: 3 km of course gone in 100 m of running, start over instead of sticking at the floor
    Test.assert(near(cs.update(2500.0, 8000.0), 1.2, 0.001));
    Test.assert(near(cs.update(3600.0, 7000.0), 1.1, 0.001));
    return true;
}

(:test)
function testTimeScalesDistanceAndGrade(logger as Test.Logger) as Boolean {
    var m = new SpeedGradeModel();
    m.stored.add(Wp.binIndex(0.0), 3.0, 30.0);
    m.stored.add(Wp.binIndex(10.0), 2.0, 30.0);
    var est = new EtaEstimator(m);
    // 1000 course metres at 11.5% course grade = 1150 of your metres at 10%
    Test.assert(near(est.timeForGrade(1000.0, 11.5, 1.15), 575.0, 0.01));
    return true;
}

(:test)
function testOlderRunObservationsFade(logger as Test.Logger) as Boolean {
    var m = new SpeedGradeModel();
    for (var i = 0; i < 200; i++) {
        m.observe(0.0, 3.0);
    }
    for (var i = 0; i < 200; i++) {
        m.observe(0.0, 2.0);
    }
    Test.assert(m.predict(0.0) < 2.2);
    Test.assert(near(m.runTotal.weights[Wp.binIndex(0.0)], 400.0, 0.01));
    return true;
}

(:test :full)
function testNamesMatch(logger as Test.Logger) as Boolean {
    Test.assert(WpUtil.namesMatch("Water", "water"));
    Test.assert(WpUtil.namesMatch("Rifugio Gonella", "Rifugio Gon"));
    Test.assert(!WpUtil.namesMatch("Wa", "Water"));
    Test.assert(!WpUtil.namesMatch("Climb", "Water"));
    return true;
}

(:test :full)
function testProfileRepeatedNames(logger as Test.Logger) as Boolean {
    var p = new CourseProfile("p1;100;Water|1000|0;Water|2000|0;*|500|0").parseAll();
    Test.assert(p.isLoaded());
    Test.assert(p.update("Water", 1000.0, 3500.0, 0.0, 1.0) && p.current == 0);
    Test.assert(p.update("Water", 400.0, 2900.0, 600.0, 1.0) && p.current == 0);
    Test.assert(p.update("Water", 2000.0, 2500.0, 1000.0, 1.0) && p.current == 1);
    Test.assert(p.update(null, 500.0, 500.0, 3000.0, 1.0) && p.current == 2);
    return true;
}

(:test :full)
function testProfilePlacesUnknownPoint(logger as Test.Logger) as Boolean {
    var p = new CourseProfile("p1;100;Climb|1000|0").parseAll();
    Test.assert(p.update("Left turn", 300.0, 900.0, 100.0, 1.0));
    Test.assert(p.current == null && near(p.loc as Float, 400.0, 0.01));
    return true;
}

(:test :full)
function testProfileSkipsPointsTheWatchLacks(logger as Test.Logger) as Boolean {
    var p = new CourseProfile("p1;100;A|1000|0;B|1000|0;C|1000|0").parseAll();
    Test.assert(p.update("C", 3000.0, 3000.0, 0.0, 1.0) && p.current == 2);
    return true;
}

(:test :full)
function testProfileRepeatedNameThatFits(logger as Test.Logger) as Boolean {
    var p = new CourseProfile("p1;100;Water|1000|0;Hut|3000|0;Water|3000|0").parseAll();
    Test.assert(p.update("Bridge", 4000.0, 7000.0, 0.0, 1.0) && near(p.loc as Float, 4000.0, 0.01));
    Test.assert(p.update("Water", 3000.0, 3000.0, 4000.0, 1.0) && p.current == 2);
    Test.assert(!p.mismatched);
    return true;
}

(:test :full)
function testProfileLongerWatchCourse(logger as Test.Logger) as Boolean {
    // the watch's course is 10% longer than the profile's
    var p = new CourseProfile("p1;100;A|5000|0;B|5000|0;C|5000|0").parseAll();
    Test.assert(p.update("A", 1100.0, 12100.0, 4400.0, 1.0) && p.current == 0);
    Test.assert(near(p.ratio as Float, 1.0 / 1.1, 0.0001));
    Test.assert(p.update("Hut", 2200.0, 11000.0, 5500.0, 1.0) && p.current == null);
    Test.assert(near(p.loc as Float, 7000.0, 0.5));
    return true;
}

(:test :full)
function testProfileMismatch(logger as Test.Logger) as Boolean {
    var p = new CourseProfile("p1;100;Climb|1000|0").parseAll();
    Test.assert(!p.update("Climb", 2000.0, 2000.0, 0.0, 1.0));
    Test.assert(p.mismatched);
    return true;
}

(:test :full)
function testProfileFollowingPoint(logger as Test.Logger) as Boolean {
    var m = new SpeedGradeModel();
    var est = new EtaEstimator(m);
    var p = new CourseProfile("p1;100;A|1000|0;B|2000|0;*|500|0").parseAll();
    Test.assert(p.update("A", 600.0, 3100.0, 400.0, 1.0));
    var i = p.following() as Number;
    Test.assert(p.followingName(i).equals("B"));
    Test.assert(near(p.followingTime(i, est, 1.0), est.timeForGrade(2000.0, 0.0, 1.0), 0.01));
    // a point the profile lacks, 500 m ahead (a turn the watch announces): still counting down to B
    Test.assert(p.update("Turn Rgt.", 500.0, 2000.0, 1500.0, 1.0) && p.current == null);
    Test.assert((p.targetName("Turn Rgt.") as String).equals("B") && near(p.targetDist, 1500.0, 0.01));
    Test.assert(p.followingName(p.following() as Number).equals("Finish"));
    Test.assert(p.update("B", 500.0, 1000.0, 2500.0, 1.0));
    Test.assert(p.followingName(p.following() as Number).equals("Finish"));
    Test.assert(p.update(null, 500.0, 500.0, 3000.0, 1.0));
    Test.assert(p.following() == null);
    return true;
}

(:test :full)
function testProfileCountsDownToItsOwnPoints(logger as Test.Logger) as Boolean {
    var est = new EtaEstimator(new SpeedGradeModel());
    // the watch knows only B; the profile also has a climb top 800 m in
    var p = new CourseProfile("p1;100;Top 900m|800|0;B|1200|0").parseAll();
    Test.assert(p.update("B", 1700.0, 1700.0, 300.0, 1.0));
    Test.assert((p.targetName("B") as String).equals("Top 900m"));
    Test.assert(near(p.targetDist, 500.0, 0.01));
    Test.assert(near(p.targetTime(est, 1.0), est.timeForGrade(500.0, 0.0, 1.0), 0.01));
    Test.assert(p.followingName(p.following() as Number).equals("B"));
    // past the top: the watch's point again
    Test.assert(p.update("B", 1100.0, 1100.0, 900.0, 1.0));
    Test.assert((p.targetName("B") as String).equals("B"));
    Test.assert(near(p.targetDist, 1100.0, 0.01));
    return true;
}

(:test :full)
function testProfileMinorPointOnTheWay(logger as Test.Logger) as Boolean {
    var est = new EtaEstimator(new SpeedGradeModel());
    // a climb top marked minor ("+"): the field keeps counting down to B, the top is on the way
    var p = new CourseProfile("p1;100;+Top 900m|800|0;B|1200|0").parseAll();
    Test.assert(p.update("B", 1700.0, 1700.0, 300.0, 1.0));
    Test.assert((p.targetName("B") as String).equals("B"));
    Test.assert(near(p.targetDist, 1700.0, 0.01));
    Test.assert(p.followingName(p.via as Number).equals("Top 900m"));
    Test.assert(near(p.viaTime(est, 1.0), est.timeForGrade(500.0, 0.0, 1.0), 0.01));
    // past the top: nothing on the way any more
    Test.assert(p.update("B", 1100.0, 1100.0, 900.0, 1.0));
    Test.assert(p.via == null);
    // the watch's course has the top too, but it's minor: count down to B through it
    var q = new CourseProfile("p1;100;+Top 900m|800|0;B|1200|0").parseAll();
    Test.assert(q.update("Top 900m", 500.0, 1700.0, 300.0, 1.0));
    Test.assert((q.targetName("Top 900m") as String).equals("B"));
    Test.assert(near(q.targetDist, 1700.0, 0.01));
    return true;
}

(:test :full)
function testProfileReadInSteps(logger as Test.Logger) as Boolean {
    var text = "p1;100";
    for (var i = 0; i < 40; i++) {
        text += ";P" + i + "|1000|37,-37,120,-120,0,5,-5,1000,-1000,2";
    }
    var p = new CourseProfile(text);
    Test.assert(!p.isLoaded());
    var calls = 1;
    while (!p.parseSome()) {
        calls++;
    }
    Test.assert(calls > 1 && p.isLoaded());
    Test.assert(p.update("P39", 1000.0, 1000.0, 39000.0, 1.0) && p.current == 39);
    return true;
}

(:test :full)
function testProfileSkipsMalformedEntries(logger as Test.Logger) as Boolean {
    var p = new CourseProfile("p1;100;Bad|1000;A|1000|0;C|5|0|9;B|1000|0").parseAll();
    Test.assert(p.update("B", 1000.0, 1000.0, 1000.0, 1.0) && p.current == 1);
    Test.assert(!(new CourseProfile("p2;100;A|1000|0").parseAll().isLoaded()));
    return true;
}

(:test :full)
function testProfileGradesToHalfPercent(logger as Test.Logger) as Boolean {
    var est = new EtaEstimator(new SpeedGradeModel());
    // 3.7% -> 3.5%, -3.7% -> -3.5%, 100% -> 63.5% (the model clamps to 40% anyway)
    var p = new CourseProfile("p1;100;X|300|37,-37,1000").parseAll();
    Test.assert(p.update("X", 300.0, 300.0, 0.0, 1.0));
    var t = est.timeForGrade(100.0, 3.5, 1.0) + est.timeForGrade(100.0, -3.5, 1.0) + est.timeForGrade(100.0, 63.5, 1.0);
    Test.assert(near(p.remainingTime(300.0, est, 1.0), t, 0.01));
    return true;
}

(:test :full)
function testProfileOneSecondsWork(logger as Test.Logger) as Boolean {
    var m = new SpeedGradeModel();
    var est = new EtaEstimator(m);
    // a 3,500-character profile at a 25 m step, as the race prep page makes them: 5 km legs,
    // two minor points before A
    var text = "p1;25";
    var names = ["+M1", "+M2", "A", "B", "C", "*"];
    var lens = [2000, 1500, 1500, 5000, 5000, 5000];
    var gs = ["37", "-120", "85", "0", "-15", "210", "-260", "5"];
    for (var e = 0; e < names.size(); e++) {
        text += ";" + names[e] + "|" + lens[e] + "|";
        for (var k = 0; k < lens[e] / 25; k++) {
            text += (k > 0 ? "," : "") + gs[(k + e) % gs.size()];
        }
    }
    var p = new CourseProfile(text);
    while (!p.parseSome()) {
    }
    m.setSteepPool(true);
    Test.assert(p.update("A", 5000.0, 20000.0, 0.0, 1.0));
    // one second, as compute and updateList do it
    var t0 = System.getTimer();
    var t = p.targetTime(est, 1.0);
    var i = p.following() as Number;
    var i2 = p.followingAfter(i) as Number;
    Test.assert(p.canWalk(null, i) && p.canWalk(i, i2));
    var t1 = p.followingTime(i, est, 1.0);
    var leg2 = p.legTime(i, i2, est, 1.0);
    logger.debug("one second: " + (System.getTimer() - t0) + " ms, " + p.walked + " stretches");
    // the same times as walking each one on its own
    Test.assert(p.viaTimes.size() == 2);
    Test.assert(near(p.viaTimes[0], p.minorTime(p.vias[0], est, 1.0), 0.01));
    Test.assert(near(p.viaTimes[1], p.minorTime(p.vias[1], est, 1.0), 0.01));
    Test.assert(near(leg2, p.followingTime(i2, est, 1.0) - t1, 0.05));
    Test.assert(t > 1.0 && t1 > 1.0 && leg2 > 1.0);
    // a leg that would take this second past MAX_WALK is left out
    p.walked = p.MAX_WALK - 100;
    Test.assert(p.canWalk(i, i2) == false && p.canWalk(null, i) == false);
    p.walked = p.MAX_WALK - 200;
    Test.assert(p.canWalk(null, i));
    return true;
}

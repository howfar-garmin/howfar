import Toybox.Lang;
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
function testSplit(logger as Test.Logger) as Boolean {
    var p = WpUtil.split("a;;b", ';');
    Test.assertEqual(p.size(), 3);
    Test.assert(p[0].equals("a") && p[1].equals("") && p[2].equals("b"));
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
    a = WpUtil.etaText(7890);  // 2 h 11.5 min
    Test.assert(a[0].equals("2:10") && a[1].equals("h"));
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
    m.imported.add(Wp.binIndex(0.0), 3.0, 30.0);
    m.imported.add(Wp.binIndex(10.0), 2.0, 30.0);
    // interpolation is in pace: 1/3 s/m at 0%, 1/2 s/m at 10%
    Test.assert(near(m.predict(4.0), 2.5, 0.001));
    Test.assert(near(m.predict(5.0), 1.0 / (1.0 / 3.0 + 0.5 / 6.0), 0.001));
    Test.assert(near(m.predict(20.0), 2.0 * Wp.toblerFactor(20.0) / Wp.toblerFactor(10.0), 0.001));
    return true;
}

(:test)
function testPriorCap(logger as Test.Logger) as Boolean {
    var m = new SpeedGradeModel();
    m.stored.add(Wp.binIndex(0.0), 3.0, 200.0);
    m.run.add(Wp.binIndex(0.0), 2.0, 20.0);
    m.invalidate();
    // prior counts as 20 observations at most, so 20 run observations weigh the same
    Test.assert(near(m.predict(0.0), 2.4, 0.001));
    return true;
}

(:test)
function testFormFactor(logger as Test.Logger) as Boolean {
    var m = new SpeedGradeModel();
    m.imported.add(Wp.binIndex(0.0), 3.0, 30.0);
    var est = new EtaEstimator(m);
    for (var i = 0; i < 40; i++) {
        est.observe(0.0, 2.7, 60.0);
    }
    Test.assert(near(m.form, 0.9, 0.001));
    Test.assert(near(m.predict(0.0), 2.7, 0.001));
    return true;
}

(:test)
function testModelString(logger as Test.Logger) as Boolean {
    var l = new ModelLayer();
    Test.assert(l.loadString("v1;-6:3.30:7;0:3.00:40"));
    Test.assert(near(l.speed(Wp.binIndex(-6.0)), 3.3, 0.001));
    Test.assert(near(l.weights[Wp.binIndex(0.0)], 40.0, 0.001));
    Test.assert(!new ModelLayer().loadString("p1;50"));
    return true;
}

(:test)
function testProfileTime(logger as Test.Logger) as Boolean {
    var m = new SpeedGradeModel();
    m.imported.add(Wp.binIndex(0.0), 3.0, 30.0);
    m.imported.add(Wp.binIndex(10.0), 2.0, 30.0);
    var est = new EtaEstimator(m);
    // segment 230 m: chunks 100, 100, 30 (the 30 m chunk is next to the waypoint)
    var p = new CourseProfile("p1;100;X|230|100,100,0");
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
    // 300 s moving, 600 s standing still: at most STOP_WINDOW of the stop counts
    var t = new GradeTracker();
    for (var i = 0; i < 900; i++) {
        t.update(i.toFloat(), (i < 300 ? i : 300) * 1.0, 300.0);
    }
    Test.assert(t.movingTime < 300.0 + 60.0);
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
    return true;
}

(:test)
function testTimeScalesDistanceAndGrade(logger as Test.Logger) as Boolean {
    var m = new SpeedGradeModel();
    m.imported.add(Wp.binIndex(0.0), 3.0, 30.0);
    m.imported.add(Wp.binIndex(10.0), 2.0, 30.0);
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

(:test)
function testNamesMatch(logger as Test.Logger) as Boolean {
    Test.assert(WpUtil.namesMatch("Water", "water"));
    Test.assert(WpUtil.namesMatch("Rifugio Gonella", "Rifugio Gon"));
    Test.assert(!WpUtil.namesMatch("Wa", "Water"));
    Test.assert(!WpUtil.namesMatch("Climb", "Water"));
    return true;
}

(:test)
function testProfileRepeatedNames(logger as Test.Logger) as Boolean {
    var p = new CourseProfile("p1;100;Water|1000|0;Water|2000|0;*|500|0");
    Test.assert(p.isLoaded());
    Test.assert(p.update("Water", 1000.0, 3500.0, 0.0, 1.0) && p.current == 0);
    Test.assert(p.update("Water", 400.0, 2900.0, 600.0, 1.0) && p.current == 0);
    Test.assert(p.update("Water", 2000.0, 2500.0, 1000.0, 1.0) && p.current == 1);
    Test.assert(p.update(null, 500.0, 500.0, 3000.0, 1.0) && p.current == 2);
    return true;
}

(:test)
function testProfilePlacesUnknownPoint(logger as Test.Logger) as Boolean {
    var p = new CourseProfile("p1;100;Climb|1000|0");
    Test.assert(p.update("Left turn", 300.0, 900.0, 100.0, 1.0));
    Test.assert(p.current == null && near(p.loc as Float, 400.0, 0.01));
    return true;
}

(:test)
function testProfileSkipsPointsTheWatchLacks(logger as Test.Logger) as Boolean {
    var p = new CourseProfile("p1;100;A|1000|0;B|1000|0;C|1000|0");
    Test.assert(p.update("C", 3000.0, 3000.0, 0.0, 1.0) && p.current == 2);
    return true;
}

(:test)
function testProfileRepeatedNameThatFits(logger as Test.Logger) as Boolean {
    var p = new CourseProfile("p1;100;Water|1000|0;Hut|3000|0;Water|3000|0");
    Test.assert(p.update("Bridge", 4000.0, 7000.0, 0.0, 1.0) && near(p.loc as Float, 4000.0, 0.01));
    Test.assert(p.update("Water", 3000.0, 3000.0, 4000.0, 1.0) && p.current == 2);
    Test.assert(!p.mismatched);
    return true;
}

(:test)
function testProfileLongerWatchCourse(logger as Test.Logger) as Boolean {
    // the watch's course is 10% longer than the profile's
    var p = new CourseProfile("p1;100;A|5000|0;B|5000|0;C|5000|0");
    Test.assert(p.update("A", 1100.0, 12100.0, 4400.0, 1.0) && p.current == 0);
    Test.assert(near(p.ratio as Float, 1.0 / 1.1, 0.0001));
    Test.assert(p.update("Hut", 2200.0, 11000.0, 5500.0, 1.0) && p.current == null);
    Test.assert(near(p.loc as Float, 7000.0, 0.5));
    return true;
}

(:test)
function testProfileMismatch(logger as Test.Logger) as Boolean {
    var p = new CourseProfile("p1;100;Climb|1000|0");
    Test.assert(!p.update("Climb", 2000.0, 2000.0, 0.0, 1.0));
    Test.assert(p.mismatched);
    return true;
}

(:test)
function testProfileFollowingPoint(logger as Test.Logger) as Boolean {
    var m = new SpeedGradeModel();
    var est = new EtaEstimator(m);
    var p = new CourseProfile("p1;100;A|1000|0;B|2000|0;*|500|0");
    Test.assert(p.update("A", 600.0, 3100.0, 400.0, 1.0));
    var i = p.following() as Number;
    Test.assert(p.followingName(i).equals("B"));
    Test.assert(near(p.followingTime(i, est, 1.0), est.timeForGrade(2000.0, 0.0, 1.0), 0.01));
    // a point the profile lacks, 500 m before B: the one after it is still B
    Test.assert(p.update("Hut", 1000.0, 2000.0, 1500.0, 1.0) && p.current == null);
    Test.assert(p.followingName(p.following() as Number).equals("B"));
    Test.assert(p.update("B", 500.0, 1000.0, 2500.0, 1.0));
    Test.assert(p.followingName(p.following() as Number).equals("Finish"));
    Test.assert(p.update(null, 500.0, 500.0, 3000.0, 1.0));
    Test.assert(p.following() == null);
    return true;
}

(:test)
function testProfileCountsDownToItsOwnPoints(logger as Test.Logger) as Boolean {
    var est = new EtaEstimator(new SpeedGradeModel());
    // the watch knows only B; the profile also has a climb top 800 m in
    var p = new CourseProfile("p1;100;Top 900m|800|0;B|1200|0");
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

import Toybox.Lang;

// Turns 1 Hz (timer, distance, altitude) samples into (grade, speed) observations.
// Mirrors GradeTracker in tools/wpeta/model.py.
class GradeTracker {
    const WINDOW = 60.0;      // metres each observation spans, to smooth altitude noise
    const EMIT_EVERY = 25.0;  // metres between observations
    (:full) const SIZE = 300;  // samples kept: 60 m even on a slow steep climb
    (:full) const MIN_STEP = 0.0;  // m: every sample is kept
    // 32 KB watches keep a sample only every 2 m or more, so 40 of them still span 60 m, and one
    // every 5 s for the stop check. Their windows start up to 2 m or 5 s earlier than with every
    // sample, as tools/wpeta keeps.
    (:lite) const SIZE = 40;
    (:lite) const MIN_STEP = 2.0;
    const STOP_WINDOW = 60.0; // stopped = less than STOP_DIST metres in the last STOP_WINDOW seconds
    const STOP_DIST = 15.0;
    (:full) const STOP_SIZE = 90;
    (:full) const STOP_EVERY = 0.0;  // s
    (:lite) const STOP_SIZE = 18;
    (:lite) const STOP_EVERY = 5.0;
    const STILL_DIST = 2.0;   // also stopped: less than this many metres for STILL_TIME seconds (a short stop to read the watch)
    const STILL_TIME = 10.0;
    const MIN_SPEED = 0.2;
    const MAX_SPEED = 10.0;
    // standing at an aid station, GPS drift can move the distance on faster than STOP_DIST a
    // minute: slower than DRIFT_SPEED with the altitude within DRIFT_ALT is no pace to learn
    const DRIFT_SPEED = 1.0;
    const DRIFT_ALT = 1.0;

    var movingTime as Float = 0.0;
    var observations as Number = 0;
    var lastGrade as Float = 0.0;
    var lastSpeed as Float = 0.0;
    var lastDist as Float = 0.0;

    hidden var _d as Array<Float>;
    hidden var _a as Array<Float>;
    hidden var _t as Array<Float>;
    hidden var _head as Number = 0;
    hidden var _count as Number = 0;
    hidden var _sd as Array<Float>;
    hidden var _st as Array<Float>;
    hidden var _shead as Number = 0;
    hidden var _scount as Number = 0;
    hidden var _lastEmit as Float?;
    hidden var _lastTime as Float?;
    hidden var _stillDist as Float?;    // where the distance last moved on by STILL_DIST
    hidden var _stillSince as Float = 0.0;  // and when
    hidden var _wasMoving as Boolean = true;

    function initialize() {
        _d = new Array<Float>[SIZE];
        _a = new Array<Float>[SIZE];
        _t = new Array<Float>[SIZE];
        _sd = new Array<Float>[STOP_SIZE];
        _st = new Array<Float>[STOP_SIZE];
        reset();
    }

    // the buffers' old samples stay: only the _count / _scount newest are ever read
    function reset() as Void {
        _head = 0;
        _count = 0;
        _shead = 0;
        _scount = 0;
        _lastEmit = null;
        _lastTime = null;
        _stillDist = null;
        _stillSince = 0.0;
        _wasMoving = true;
        movingTime = 0.0;
        observations = 0;
        lastGrade = 0.0;
        lastSpeed = 0.0;
        lastDist = 0.0;
    }

    // Records the sample and says whether we moved STOP_DIST in the last STOP_WINDOW s.
    // currentSpeed is not used: on steep climbs it often dips to almost zero.
    hidden function isMoving(timeS as Float, dist as Float) as Boolean {
        if (_scount == 0 || timeS - _st[(_shead - 1 + STOP_SIZE) % STOP_SIZE] >= STOP_EVERY) {
            _sd[_shead] = dist;
            _st[_shead] = timeS;
            _shead = (_shead + 1) % STOP_SIZE;
            if (_scount < STOP_SIZE) {
                _scount++;
            }
        }
        var stillDist = _stillDist;
        if (stillDist == null || dist - stillDist >= STILL_DIST) {
            _stillDist = dist;
            _stillSince = timeS;
        }
        if (timeS - _stillSince >= STILL_TIME) {
            return false;
        }
        for (var k = 1; k < _scount; k++) {
            var idx = (_shead - 1 - k + STOP_SIZE) % STOP_SIZE;
            if (_st[idx] <= timeS - STOP_WINDOW) {
                return dist - _sd[idx] >= STOP_DIST;
            }
        }
        return true;  // not enough history yet
    }

    // timeS is timer time in seconds. Returns true when an observation was emitted
    // (read it from lastGrade / lastSpeed / lastDist).
    function update(timeS as Float, dist as Float, alt as Float) as Boolean {
        var moving = isMoving(timeS, dist);
        var lastTime = _lastTime;
        if (lastTime != null) {
            var dt = timeS - lastTime;
            if (dt > 0.0 && dt < 30.0 && moving) {
                movingTime += dt;
            }
        }
        _lastTime = timeS;
        if (_wasMoving && !moving) {
            // a stop is seen only after a while: the seconds already spent standing weren't moving
            movingTime -= WpUtil.clamp(timeS - _stillSince, 0.0, STOP_WINDOW);
        } else if (moving && !_wasMoving) {
            // the first observation after a stop starts after it
            _count = 0;
            _lastEmit = null;
        }
        _wasMoving = moving;
        if (!moving) {
            return false;
        }

        if (_count == 0 || dist - _d[(_head - 1 + SIZE) % SIZE] >= MIN_STEP) {
            _d[_head] = dist;
            _a[_head] = alt;
            _t[_head] = movingTime;
            _head = (_head + 1) % SIZE;
            if (_count < SIZE) {
                _count++;
            }
        }

        var lastEmit = _lastEmit;
        if (lastEmit == null) {
            _lastEmit = dist;
            return false;
        }
        if (dist - lastEmit < EMIT_EVERY) {
            return false;
        }

        for (var k = 1; k < _count; k++) {
            var idx = (_head - 1 - k + SIZE) % SIZE;
            if (_d[idx] <= dist - WINDOW) {
                var dd = dist - _d[idx];
                var dt = movingTime - _t[idx];
                _lastEmit = dist;
                if (dt <= 0.0) {
                    return false;
                }
                var v = dd / dt;
                if (v < MIN_SPEED || v > MAX_SPEED) {
                    return false;
                }
                if (v < DRIFT_SPEED && (alt - _a[idx]).abs() < DRIFT_ALT) {
                    return false;
                }
                lastGrade = WpUtil.clamp((alt - _a[idx]) / dd * 100.0, Wp.MIN_GRADE, Wp.MAX_GRADE);
                lastSpeed = v;
                lastDist = dd;
                observations++;
                return true;
            }
        }
        return false;
    }
}

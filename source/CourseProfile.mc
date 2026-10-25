import Toybox.Lang;

// Elevation profile between course points, pasted into settings from the race prep page:
//   p1;<step>;<name>|<length m>|<g>,<g>,...;...
// A name starting with "+" is a minor point (a climb top, a hut, a point of your own).
// Every next point gets a place on the profile (loc, metres from its start), and the time to
// it is the profile's stretch that ends there and is distanceToNextPoint long:
// - a point the profile knows by name: the end of its entry;
// - a point it doesn't know: where you are plus distanceToNextPoint, where you are being the
//   profile's length minus distanceToDestination.
// The watch's course may be another version of the course, so the watch's distances are
// converted with ratio (profile metres per watch course metre), learned at each known point.
// What the field counts down to (target*) is the next main profile point ahead of you, which
// can be one the watch's course doesn't have, or the watch's next point when that comes first
// and the profile doesn't know it. via is the next minor point before it. Where you are is
// always taken from the watch's next point, so the watch's checkpoints keep anchoring it.
// Mirrors ProfileMatcher in tools/wpeta/profile.py.
class CourseProfile {
    const FINISH_NAME = "*";
    const SLACK = 100.0;            // m: a stretch may start this far before the profile's start
    const PASSED = 5.0;             // m: a profile point this close behind or ahead counts as reached
    const MIN_RATIO_DIST = 2000.0;  // m to the finish below which the ratio isn't updated any more
    const RATIO_LO = 0.8;
    const RATIO_HI = 1.25;

    var step as Float = 50.0;
    var current as Number?;   // entry of a point known by name
    var loc as Float?;        // where the watch's next point is on the profile
    var targetEnd as Float?;  // profile metres of what the field counts down to
    var targetIndex as Number?;  // its entry, null for a watch point the profile lacks
    var targetDist as Float = 0.0;  // watch course metres to it
    var via as Number?;       // entry of the next minor point before it
    var vias as Array<Number> = [] as Array<Number>;  // every minor point before it, in order
    var mismatched as Boolean = false;
    var ratio as Float?;
    var total as Float = 0.0;

    hidden var _names as Array<String>;
    hidden var _minor as Array<Boolean>;
    hidden var _lengths as Array<Float>;
    hidden var _starts as Array<Float>;
    hidden var _grades as Array<Array<Number> >;
    hidden var _pointer as Number = 0;
    hidden var _lastName as String?;
    hidden var _lastDist as Float = 0.0;
    hidden var _here as Float?;       // where you were at the last update with a located point
    hidden var _hereWatch as Float?;  // and the watch's distance then
    // walking cursor
    hidden var _ci as Number = 0;
    hidden var _ck as Number = 0;
    hidden var _ca as Float = 0.0;
    hidden var _cg as Float = 0.0;

    function initialize(text as String) {
        _names = [] as Array<String>;
        _minor = [] as Array<Boolean>;
        _lengths = [] as Array<Float>;
        _starts = [] as Array<Float>;
        _grades = [] as Array<Array<Number> >;
        parse(text);
    }

    hidden function parse(text as String) as Void {
        var parts = WpUtil.split(text, ';');
        if (parts.size() < 2 || !parts[0].equals("p1")) {
            return;
        }
        var s = parts[1].toFloat();
        if (s == null || s <= 0.0) {
            return;
        }
        step = s;
        for (var p = 2; p < parts.size(); p++) {
            var f = WpUtil.split(parts[p], '|');
            if (f.size() != 3) {
                continue;
            }
            var len = f[1].toFloat();
            if (len == null) {
                continue;
            }
            var grades = [] as Array<Number>;
            var g = WpUtil.split(f[2], ',');
            for (var i = 0; i < g.size(); i++) {
                var v = g[i].toNumber();
                if (v != null) {
                    grades.add(v);
                }
            }
            if (grades.size() == 0) {
                grades.add(0);
            }
            var name = f[0];
            var head = name.substring(0, 1);
            var rest = name.substring(1, name.length());
            var minor = head != null && head.equals("+") && rest != null;
            _minor.add(minor);
            _names.add(minor ? rest as String : name);
            _lengths.add(len);
            _starts.add(total);
            _grades.add(grades);
            total += len;
        }
    }

    function isLoaded() as Boolean {
        return _names.size() > 0;
    }

    function reset() as Void {
        _pointer = 0;
        current = null;
        loc = null;
        mismatched = false;
        ratio = null;
        _lastName = null;
        _lastDist = 0.0;
        _here = null;
        _hereWatch = null;
        targetEnd = null;
        targetIndex = null;
        targetDist = 0.0;
        via = null;
        vias = [] as Array<Number>;
    }

    // --- walking the profile: stretches of constant grade

    hidden function seek(a as Float) as Void {
        var i = 0;
        while (i + 1 < _starts.size() && _starts[i + 1] <= a) {
            i++;
        }
        var k = ((a - _starts[i]) / step).toNumber();
        var last = _grades[i].size() - 1;
        _ci = i;
        _ck = k < 0 ? 0 : (k > last ? last : k);
        _ca = a;
    }

    // Length of the next stretch of constant grade, ending at b at most; its grade (%) in _cg
    hidden function next(b as Float) as Float {
        while (_ci < _names.size() && _ca < b) {
            var grades = _grades[_ci];
            var last = grades.size() - 1;
            var start = _starts[_ci];
            var end = _ck >= last ? start + _lengths[_ci] : start + (_ck + 1) * step;
            var grade = grades[_ck] / 10.0;
            var hi = end < b ? end : b;
            if (hi >= end) {
                if (_ck >= last) {
                    _ci++;
                    _ck = 0;
                } else {
                    _ck++;
                }
            }
            if (hi > _ca) {
                var use = hi - _ca;
                _ca = hi;
                _cg = grade;
                return use;
            }
        }
        return 0.0;
    }

    // --- following the next point

    hidden function position(distDest as Float?, watchDist as Float?, scale as Float) as Float? {
        var r = ratio != null ? ratio : 1.0;
        if (distDest != null) {
            var p = total - distDest * r;
            return p > 0.0 ? p : 0.0;
        }
        var here = _here;
        if (here == null) {
            return null;
        }
        var hw = _hereWatch;
        if (watchDist != null && hw != null) {
            here += (watchDist - hw) / scale * r;
        }
        return here;
    }

    // The entry of the next point: the first one ahead with this name whose stretch fits
    // where you are; or the finish
    hidden function find(name as String?, distNext as Float, distDest as Float?, here as Float?) as Number? {
        var r = ratio != null ? ratio : 1.0;
        if (name != null) {
            for (var i = _pointer; i < _names.size(); i++) {
                if (!_names[i].equals(FINISH_NAME) && WpUtil.namesMatch(_names[i], name)) {
                    var start = _starts[i] + _lengths[i] - distNext * r;
                    if (start < -SLACK) {
                        mismatched = true;
                    } else if (here == null || (start - here).abs() <= 500.0 + 0.2 * distNext) {
                        return i;
                    }
                }
            }
        }
        if (distDest != null && (distDest - distNext).abs() < 30.0) {
            var last = _names.size() - 1;
            if (last >= _pointer && _names[last].equals(FINISH_NAME)) {
                return last;
            }
        }
        return null;
    }

    // Returns true when the next point has a place on the profile
    function update(name as String?, distNext as Float, distDest as Float?, watchDist as Float?, scale as Float) as Boolean {
        if (ratio == null && distDest != null && distDest > 0.0) {
            // first guess: you start at the start of both courses
            var r = total / (distDest + (watchDist != null ? watchDist : 0.0) / scale);
            ratio = (r >= 0.85 && r <= 1.15) ? r : 1.0;
        }
        var lastName = _lastName;
        var sameName = (name == null && lastName == null)
            || (name != null && lastName != null && name.equals(lastName));
        var changed = !sameName || distNext > _lastDist + 50.0;
        _lastName = name;
        _lastDist = distNext;
        if (changed) {
            current = null;
            loc = null;
            mismatched = false;
            var here = position(distDest, watchDist, scale);
            var idx = find(name, distNext, distDest, _here != null ? here : null);
            if (idx != null) {
                mismatched = false;
                current = idx;
                loc = _starts[idx] + _lengths[idx];
                _pointer = idx + 1;
            } else if (here != null) {
                var x = here + distNext * (ratio != null ? ratio : 1.0);
                if (x > total + SLACK) {
                    mismatched = true;
                } else {
                    loc = x < total ? x : total;
                }
            }
        }
        var at = loc;
        if (at == null) {
            return false;
        }
        var rr = ratio != null ? ratio : 1.0;
        if (current != null && distDest != null) {
            var left = total - at;  // profile metres from the point to the finish
            if (left > MIN_RATIO_DIST && distDest - distNext > MIN_RATIO_DIST) {
                rr = WpUtil.clamp(left / (distDest - distNext), RATIO_LO, RATIO_HI);
                ratio = rr;
            }
        }
        var here = at - distNext * rr;
        _here = here;
        _hereWatch = watchDist;
        aim(here, at, rr);
        return true;
    }

    hidden function aim(here as Float, at as Float, r as Float) as Void {
        targetEnd = at;
        targetIndex = current;
        via = null;
        for (var i = 0; i < _names.size(); i++) {
            var end = _starts[i] + _lengths[i];
            if (!_minor[i] && end > here + PASSED) {
                // the watch's next point, when the profile doesn't know it, counts as main
                if (!(current == null && at < end - PASSED)) {
                    targetEnd = end;
                    targetIndex = i;
                }
                break;
            }
        }
        vias = [] as Array<Number>;
        for (var i = 0; i < _names.size(); i++) {
            var end = _starts[i] + _lengths[i];
            if (end >= (targetEnd as Float) - PASSED) {
                break;
            }
            if (_minor[i] && end > here + PASSED) {
                vias.add(i);
            }
        }
        via = vias.size() > 0 ? vias[0] : null;
        var d = (targetEnd as Float - here) / r;
        targetDist = d > 0.0 ? d : 0.0;
    }

    // Name of what the field counts down to
    function targetName(watchName as String?) as String? {
        var i = targetIndex;
        if (i == null || i == current) {
            return watchName;
        }
        return followingName(i);
    }

    // Time from where you are to what the field counts down to
    function targetTime(estimator as EtaEstimator, scale as Float) as Float {
        var t = timeBetween(_here as Float, targetEnd as Float, estimator, scale);
        return t > 1.0 ? t : 1.0;
    }

    // Time over the profile from a to b; profile metres before its start count at the first grade
    hidden function timeBetween(a as Float, b as Float, estimator as EtaEstimator, scale as Float) as Float {
        var r = ratio != null ? ratio : 1.0;
        var t = 0.0;
        var first = null;
        seek(a > 0.0 ? a : 0.0);
        while (true) {
            var use = next(b);
            if (use <= 0.0) {
                break;
            }
            if (first == null) {
                first = _cg;
            }
            t += estimator.timeForGrade(use / r, _cg * r, scale);
        }
        if (a < 0.0) {
            t += estimator.timeForGrade(-a / r, (first != null ? first : 0.0) * r, scale);
        }
        return t;
    }

    // Time over the profile's stretch ending at loc, distNext watch course metres long
    function remainingTime(distNext as Float, estimator as EtaEstimator, scale as Float) as Float {
        var b = loc as Float;
        var t = timeBetween(b - distNext * (ratio != null ? ratio : 1.0), b, estimator, scale);
        return t > 1.0 ? t : 1.0;
    }

    // Entry of the main profile point after the one the field counts down to, if any
    function following() as Number? {
        var at = targetEnd;
        if (at == null) {
            return null;
        }
        for (var i = 0; i < _names.size(); i++) {
            if (!_minor[i] && _starts[i] + _lengths[i] > at + 1.0) {
                return i;
            }
        }
        return null;
    }

    // Entry of the main profile point after entry i, if any
    function followingAfter(i as Number) as Number? {
        var at = _starts[i] + _lengths[i];
        for (var j = i + 1; j < _names.size(); j++) {
            if (!_minor[j] && _starts[j] + _lengths[j] > at + 1.0) {
                return j;
            }
        }
        return null;
    }

    // Time from where you are to the next minor point (via)
    function viaTime(estimator as EtaEstimator, scale as Float) as Float {
        return minorTime(via as Number, estimator, scale);
    }

    // Time from where you are to profile point i (a minor point on the way)
    function minorTime(i as Number, estimator as EtaEstimator, scale as Float) as Float {
        var t = timeBetween(_here as Float, _starts[i] + _lengths[i], estimator, scale);
        return t > 1.0 ? t : 1.0;
    }

    function followingName(i as Number) as String {
        return _names[i].equals(FINISH_NAME) ? "Finish" : _names[i];
    }

    // Time from the point the field counts down to, to profile point i
    function followingTime(i as Number, estimator as EtaEstimator, scale as Float) as Float {
        return timeBetween(targetEnd as Float, _starts[i] + _lengths[i], estimator, scale);
    }
}

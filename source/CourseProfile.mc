import Toybox.Lang;

// Elevation profile between course points, pasted into settings from the race prep page:
//   p1;<step>;<name>|<length m>|<g>,<g>,...;...
// Every next point gets a place on the profile (loc, metres from its start), and the time to
// it is the profile's stretch that ends there and is distanceToNextPoint long:
// - a point the profile knows by name: the end of its entry;
// - a point it doesn't know: where you are plus distanceToNextPoint, where you are being the
//   profile's length minus distanceToDestination.
// The watch's course may be another version of the course, so the watch's distances are
// converted with ratio (profile metres per watch course metre), learned at each known point.
// Mirrors ProfileMatcher in tools/wpeta/profile.py.
class CourseProfile {
    const FINISH_NAME = "*";
    const SLACK = 100.0;            // m: a stretch may start this far before the profile's start
    const MIN_RATIO_DIST = 2000.0;  // m to the finish below which the ratio isn't updated any more
    const RATIO_LO = 0.8;
    const RATIO_HI = 1.25;

    var step as Float = 50.0;
    var current as Number?;   // entry of a point known by name
    var loc as Float?;
    var mismatched as Boolean = false;
    var ratio as Float?;
    var total as Float = 0.0;

    hidden var _names as Array<String>;
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
            _names.add(f[0]);
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
        _here = at - distNext * rr;
        _hereWatch = watchDist;
        return true;
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

    // Entry of the profile point after the next point, if there is one
    function following() as Number? {
        var at = loc;
        if (at == null) {
            return null;
        }
        for (var i = 0; i < _names.size(); i++) {
            if (_starts[i] + _lengths[i] > at + 1.0) {
                return i;
            }
        }
        return null;
    }

    function followingName(i as Number) as String {
        return _names[i].equals(FINISH_NAME) ? "Finish" : _names[i];
    }

    // Time from the next point to profile point i
    function followingTime(i as Number, estimator as EtaEstimator, scale as Float) as Float {
        return timeBetween(loc as Float, _starts[i] + _lengths[i], estimator, scale);
    }
}

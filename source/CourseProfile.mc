import Toybox.Lang;

// Elevation profile between course points, pasted into settings from tools/course_to_profile.py:
//   p1;<step>;<name>|<length m>|<g>,<g>,...;...
// Follows the watch's next course point through the entries.
// Mirrors ProfileMatcher in tools/wpeta/profile.py.
class CourseProfile {
    const FINISH_NAME = "*";

    var step as Float = 50.0;
    var current as Number?;
    var mismatched as Boolean = false;

    hidden var _names as Array<String>;
    hidden var _lengths as Array<Float>;
    hidden var _grades as Array<Array<Number> >;
    hidden var _pointer as Number = 0;
    hidden var _lastName as String?;
    hidden var _lastDist as Float = 0.0;

    function initialize(text as String) {
        _names = [] as Array<String>;
        _lengths = [] as Array<Float>;
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
            _names.add(f[0]);
            _lengths.add(len);
            _grades.add(grades);
        }
    }

    function isLoaded() as Boolean {
        return _names.size() > 0;
    }

    function reset() as Void {
        _pointer = 0;
        current = null;
        mismatched = false;
        _lastName = null;
        _lastDist = 0.0;
    }

    hidden function find(name as String?, distNext as Float, distDest as Float?) as Number? {
        if (name != null) {
            for (var i = _pointer; i < _names.size(); i++) {
                if (!_names[i].equals(FINISH_NAME) && WpUtil.namesMatch(_names[i], name)) {
                    return i;
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

    // Returns true when a profile segment is active for the current next point
    function update(name as String?, distNext as Float, distDest as Float?) as Boolean {
        var lastName = _lastName;
        var sameName = (name == null && lastName == null)
            || (name != null && lastName != null && name.equals(lastName));
        var changed = !sameName || distNext > _lastDist + 50.0;
        _lastName = name;
        _lastDist = distNext;
        if (changed) {
            current = null;
            mismatched = false;
            var idx = find(name, distNext, distDest);
            if (idx != null) {
                if (distNext > _lengths[idx] * 1.1 + 50.0) {
                    mismatched = true;
                } else {
                    current = idx;
                    _pointer = idx + 1;
                }
            }
        }
        return current != null;
    }

    function remainingTime(distNext as Float, estimator as EtaEstimator, scale as Float) as Float {
        var idx = current as Number;
        return estimator.timeForTail(_grades[idx], _lengths[idx], step, distNext, scale);
    }
}

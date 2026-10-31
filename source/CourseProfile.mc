import Toybox.Lang;
import Toybox.System;

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
// can be one the watch's course doesn't have; a watch point the profile doesn't know (a turn the
// watch announces) is never counted down to. via is the next minor point before it. Where you are is
// always taken from the watch's next point, so the watch's checkpoints keep anchoring it.
// Mirrors ProfileMatcher in tools/wpeta/profile.py. The full build only: the lite build (32 KB watches)
// has no room for a profile.
(:full)
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
    var via as Number?;  // entry of the next minor point before it
    var vias as Array<Number> = [] as Array<Number>;  // every minor point before it, in order
    var mismatched as Boolean = false;
    var ratio as Float?;
    var total as Float = 0.0;

    hidden var _names as Array<String>;
    hidden var _minor as Array<Boolean>;
    hidden var _lengths as Array<Float>;
    hidden var _starts as Array<Float>;
    // every entry's grades in one array, a byte each in half percents (next), entry i's from _first[i]
    hidden var _grades as ByteArray = []b;
    hidden var _first as Array<Number>;
    hidden var _pointer as Number = 0;
    hidden var _lastName as String?;
    hidden var _lastDist as Float = 0.0;
    hidden var _here as Float?;       // where you were at the last update with a located point
    hidden var _hereWatch as Float?;  // and the watch's distance then

    // The times of one second walk the profile ahead stretch by stretch, and all of it must run
    // well within the watchdog's limit (an Enduro 3 tripped it with a few legs ahead at a 25 m
    // step). So the walk keeps the time per metre at each grade (by its byte) instead of asking
    // the model each time (the model, fatigue, ratio and scale don't change within a second),
    // and walked counts this second's stretches: the list's legs are left out when they would
    // take it past MAX_WALK.
    const MAX_WALK = 1200;
    var walked as Number = 0;
    var viaTimes as Array<Float> = [] as Array<Float>;  // time to each of vias, by targetTime
    hidden var _paces as Array<Float?> = new [256] as Array<Float?>;
    hidden var _paceKey as Array<Float> = [0.0, 0.0, 0.0] as Array<Float>;  // ratio, scale, fatigue

    // Reading the text, a little at a time (parseSome): reading all of a long profile at once
    // trips the watchdog on older watches, and splitting it all at once takes several times its size
    const PARSE_CHARS = 600;  // characters read per parseSome call
    const CHUNK = 100;        // characters turned into a Char array at a time
    const RESERVE = 2500;     // bytes of free memory a profile must leave, for the field's work every second
    hidden var _text as String?;  // null once read
    hidden var _pos as Number = 0;
    hidden var _field as Number = 0;  // 0 name, 1 length, 2 grades
    hidden var _tokStart as Number = 0;
    hidden var _name as String?;
    hidden var _len as Float?;
    hidden var _bad as Boolean = false;
    hidden var _num as Number = 0;
    hidden var _neg as Boolean = false;
    hidden var _digits as Boolean = false;
    hidden var _entry as Array<Number> = [] as Array<Number>;

    // The text is read by parseSome; parseAll reads it at once (tests, short profiles)
    function initialize(text as String) {
        _names = [] as Array<String>;
        _minor = [] as Array<Boolean>;
        _lengths = [] as Array<Float>;
        _starts = [] as Array<Float>;
        _first = [] as Array<Number>;
        // header: p1;<step>;
        var n = text.length();
        var head = text.substring(0, n < 24 ? n : 24) as String;
        if (!head.substring(0, 3).equals("p1;")) {
            return;
        }
        var rest = head.substring(3, head.length()) as String;
        var j = rest.find(";");
        if (j == null) {
            return;
        }
        var s = rest.substring(0, j).toFloat();
        if (s == null || s <= 0.0) {
            return;
        }
        step = s;
        _text = text;
        _pos = 4 + j;
        _tokStart = _pos;
    }

    function parseAll() as CourseProfile {
        while (!parseSome()) {
        }
        return self;
    }

    // Reads the next PARSE_CHARS characters; true once the whole text is read
    function parseSome() as Boolean {
        var text = _text;
        if (text == null) {
            return true;
        }
        var n = text.length();
        var stop = _pos + PARSE_CHARS < n ? _pos + PARSE_CHARS : n;
        while (_pos < stop) {
            var end = _pos + CHUNK < stop ? _pos + CHUNK : stop;
            var chars = (text.substring(_pos, end) as String).toCharArray();
            for (var i = 0; i < chars.size(); i++) {
                readChar(text, chars[i], _pos + i);
            }
            _pos = end;
            if (System.getSystemStats().freeMemory < RESERVE) {
                // too long for this watch's memory: no profile, the average grade instead
                _names = [] as Array<String>;
                _minor = [] as Array<Boolean>;
                _lengths = [] as Array<Float>;
                _starts = [] as Array<Float>;
                _first = [] as Array<Number>;
                _grades = []b;
                _entry = [] as Array<Number>;
                _text = null;
                return true;
            }
        }
        if (_pos >= n) {
            endEntry();
            _text = null;
            return true;
        }
        return false;
    }

    // <name>|<length>|<g>,<g>,...; an entry without exactly these three fields is skipped
    hidden function readChar(text as String, c as Char, at as Number) as Void {
        if (c == ';') {
            endEntry();
            _tokStart = at + 1;
        } else if (c == '|') {
            if (_field == 0) {
                _name = text.substring(_tokStart, at);
            } else if (_field == 1) {
                _len = text.substring(_tokStart, at).toFloat();
            } else {
                _bad = true;
            }
            _field++;
            _tokStart = at + 1;
        } else if (_field == 2) {
            if (c == ',') {
                endGrade();
            } else if (c == '-') {
                _neg = true;
            } else {
                var d = c.toNumber() - 48;
                if (d >= 0 && d <= 9) {
                    _num = _num * 10 + d;
                    _digits = true;
                }
            }
        }
    }

    hidden function endGrade() as Void {
        if (_digits) {
            _entry.add(_neg ? -_num : _num);
        }
        _num = 0;
        _neg = false;
        _digits = false;
    }

    hidden function endEntry() as Void {
        var name = _name;
        var len = _len;
        if (_field == 2 && !_bad && name != null && len != null) {
            endGrade();
            if (_entry.size() == 0) {
                _entry.add(0);
            }
            var b = new [_entry.size()]b;
            for (var k = 0; k < _entry.size(); k++) {
                // tenths of a percent to half percents, rounded half away from zero, -63.5% to 63.5%
                var v = _entry[k];
                v = v >= 0 ? (v + 2) / 5 : -((2 - v) / 5);
                b[k] = (v < -127 ? -127 : (v > 127 ? 127 : v)) & 0xFF;
            }
            var head = name.substring(0, 1);
            var rest = name.substring(1, name.length());
            var minor = head != null && head.equals("+") && rest != null;
            _minor.add(minor);
            _names.add(minor ? rest as String : name);
            _lengths.add(len);
            _starts.add(total);
            _first.add(_grades.size());
            _grades.addAll(b);
            total += len;
        }
        _field = 0;
        _name = null;
        _len = null;
        _bad = false;
        _num = 0;
        _neg = false;
        _digits = false;
        _entry = [] as Array<Number>;
    }

    function isLoaded() as Boolean {
        return _text == null && _names.size() > 0;
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
        setVias(null);
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
        walked = 0;
        viaTimes = [] as Array<Float>;
        _paces = new [256] as Array<Float?>;  // the model may have learned since the last second
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
        for (var i = 0; i < _names.size(); i++) {
            var end = _starts[i] + _lengths[i];
            if (!_minor[i] && end > here + PASSED) {
                // the profile's points are the list: a watch point it doesn't know (a turn the watch
                // announces, a checkpoint you unticked) still says where you are, but isn't counted down to
                targetEnd = end;
                targetIndex = i;
                break;
            }
        }
        setVias(here);
        var d = (targetEnd as Float - here) / r;
        targetDist = d > 0.0 ? d : 0.0;
    }

    // The minor points between here and what the field counts down to (none for null), for the list
    hidden function setVias(here as Float?) as Void {
        vias = [] as Array<Number>;
        for (var i = 0; here != null && i < _names.size(); i++) {
            var end = _starts[i] + _lengths[i];
            if (end >= (targetEnd as Float) - PASSED) {
                break;
            }
            if (_minor[i] && end > here + PASSED) {
                vias.add(i);
            }
        }
        via = vias.size() > 0 ? vias[0] : null;
    }

    // Name of what the field counts down to
    function targetName(watchName as String?) as String? {
        var i = targetIndex;
        if (i == null || i == current) {
            return watchName;
        }
        return followingName(i);
    }

    // Time from where you are to what the field counts down to; on the way, the time to each of
    // vias into viaTimes, so the profile ahead is walked once
    function targetTime(estimator as EtaEstimator, scale as Float) as Float {
        var a = _here as Float;
        var t = 0.0;
        viaTimes = [] as Array<Float>;
        for (var j = 0; j < vias.size(); j++) {
            var end = _starts[vias[j]] + _lengths[vias[j]];
            t += timeBetween(a, end, estimator, scale);
            viaTimes.add(t > 1.0 ? t : 1.0);
            a = end;
        }
        t += timeBetween(a, targetEnd as Float, estimator, scale);
        return t > 1.0 ? t : 1.0;
    }

    // Time over the profile from a to b; profile metres before its start count at the first grade
    hidden function timeBetween(a as Float, b as Float, estimator as EtaEstimator, scale as Float) as Float {
        var r = ratio != null ? ratio : 1.0;
        if (r != _paceKey[0] || scale != _paceKey[1] || estimator.fatigue != _paceKey[2]) {
            _paces = new [256] as Array<Float?>;
            _paceKey = [r, scale, estimator.fatigue] as Array<Float>;
        }
        // the model builds its curve here if it must, outside walk's frame: a data field's stack
        // is small, and building the curve is the deepest chain the field has
        estimator.timeForGrade(1.0, 0.0, scale);
        return walk(a, b, estimator, scale, r);
    }

    // timeBetween's walk, stretch by stretch of constant grade. One loop on locals, the fewest
    // that will do: it's the field's hottest code (see MAX_WALK).
    hidden function walk(a as Float, b as Float, estimator as EtaEstimator, scale as Float, r as Float) as Float {
        var paces = _paces;
        var n = _starts.size();
        var t = 0.0;  // profile metres times s per metre, divided by r at the end
        var first = null;  // the first stretch's s per metre
        var x = a > 0.0 ? a : 0.0;
        var i = 0;
        while (i + 1 < n && _starts[i + 1] <= x) {
            i++;
        }
        for (; i < n && x < b; i++) {
            var start = _starts[i];
            var end = start + _lengths[i];
            end = end < b ? end : b;
            var f = _first[i];
            var last = (i + 1 < n ? _first[i + 1] : _grades.size()) - f - 1;
            var k = ((x - start) / step).toNumber();
            k = k < 0 ? 0 : (k > last ? last : k);
            while (x < end) {
                var hi = k >= last ? end : start + (k + 1) * step;
                hi = hi < end ? hi : end;
                if (hi > x) {
                    var raw = _grades[f + k];
                    var pace = paces[raw];
                    if (pace == null) {
                        pace = estimator.timeForGrade(1.0, (raw >= 128 ? raw - 256 : raw) * 0.5 * r, scale);
                        paces[raw] = pace;
                    }
                    if (first == null) {
                        first = pace;
                    }
                    t += (hi - x) * pace;
                    x = hi;
                    walked++;
                }
                k++;
            }
        }
        if (a < 0.0) {
            t += -a * (first != null ? first : estimator.timeForGrade(1.0, 0.0, scale));
        }
        return t / r;
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

    // Time from profile point i to profile point j
    function legTime(i as Number, j as Number, estimator as EtaEstimator, scale as Float) as Float {
        return timeBetween(_starts[i] + _lengths[i], _starts[j] + _lengths[j], estimator, scale);
    }

    // Whether walking on to profile point j, from point i (null: what the field counts down to),
    // still fits this second (MAX_WALK)
    function canWalk(i as Number?, j as Number) as Boolean {
        var a = i != null ? _starts[i] + _lengths[i] : targetEnd as Float;
        return walked + (_starts[j] + _lengths[j] - a) / step <= MAX_WALK;
    }
}

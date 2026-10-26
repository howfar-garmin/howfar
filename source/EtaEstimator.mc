import Toybox.Lang;

// Form factor (today vs. past runs), fatigue factor (the last couple of km vs. the model)
// and time integration over grades. Mirrors EtaEstimator in tools/wpeta/model.py.
class EtaEstimator {
    const ALPHA = 0.06;
    const MIN_OBS = 8;
    const FATIGUE_ALPHA = 0.01;  // ~70 observations, ~1.7 km half-life
    const FATIGUE_LO = 0.6;
    const FATIGUE_HI = 1.15;
    const FORM_LO_PRIOR = 0.6;   // how far today may differ from past races (short fast races vs. ultras)
    const FORM_HI_PRIOR = 1.6;

    var fatigue as Float = 1.0;  // speed ratio: 0.8 = 20% slower than the model right now

    hidden var _model as SpeedGradeModel;
    hidden var _pred as Float = 0.0;
    hidden var _act as Float = 0.0;
    hidden var _fpred as Float = 0.0;
    hidden var _fact as Float = 0.0;
    hidden var _count as Number = 0;

    function initialize(model as SpeedGradeModel) {
        _model = model;
        reset();
    }

    function reset() as Void {
        _pred = 0.0;
        _act = 0.0;
        _fpred = 0.0;
        _fact = 0.0;
        _count = 0;
        fatigue = 1.0;
        _model.setForm(1.0);
    }

    // Call before the observation is added to the model's run layer
    function observe(gradePct as Float, speed as Float, dist as Float) as Void {
        var act = dist / speed;
        // fatigue: how the full model (before seeing this observation) did on it
        var fpred = dist / _model.predict(gradePct);
        if (_count == 0) {
            // averages that start empty, so the first metres don't outweigh the next kilometres
            _fpred = 0.0;
            _fact = 0.0;
        }
        _fpred += (fpred - _fpred) * FATIGUE_ALPHA;
        _fact += (act - _fact) * FATIGUE_ALPHA;
        if (_count + 1 >= MIN_OBS && _fact > 0.0) {
            fatigue = WpUtil.clamp(_fpred / _fact, FATIGUE_LO, FATIGUE_HI);
        }

        var pred = dist / _model.predictPrior(gradePct);
        if (_count == 0) {
            _pred = pred;
            _act = act;
        } else {
            _pred += (pred - _pred) * ALPHA;
            _act += (act - _act) * ALPHA;
        }
        _count++;
        if (_count >= MIN_OBS && _act > 0.0) {
            var hasPrior = _model.hasPrior();
            _model.setForm(WpUtil.clamp(_pred / _act, hasPrior ? FORM_LO_PRIOR : 0.25, hasPrior ? FORM_HI_PRIOR : 3.0));
        }
    }

    // dist is in course metres; scale is your metres per course metre (see CourseScale)
    hidden function speedAt(gradePct as Float, scale as Float) as Float {
        return _model.predict(gradePct / scale) * fatigue;
    }

    function timeForGrade(dist as Float, gradePct as Float, scale as Float) as Float {
        return dist * scale / speedAt(gradePct, scale);
    }
}

// Your distance per metre of course, learned while navigating.
// The watch measures more distance than the course file has (switchbacks the course line
// cuts, GPS wobble): about 15% more on the Tor des Geants. Speeds and grades are learned
// in your metres, while distanceToNextPoint is in course metres.
// Mirrors CourseScale in tools/wpeta/model.py.
class CourseScale {
    const MIN_PROGRESS = 1000.0;  // course metres before the ratio is trusted
    const LO = 0.85;
    const HI = 1.5;

    var ratio as Float = 1.0;
    hidden var _baseDist as Float?;
    hidden var _baseDest as Float = 0.0;
    hidden var _lastDest as Float?;
    hidden var _lastDist as Float?;

    function initialize() {
        reset();
    }

    function reset() as Void {
        ratio = 1.0;
        _baseDist = null;
        _baseDest = 0.0;
        _lastDest = null;
        _lastDist = null;
    }

    function update(dist as Float, distDest as Float) as Float {
        // start over at the first fix, when the remaining course jumps up (new course, reroute)
        // or drops by more than you ran (you cut part of the course)
        var lastDest = _lastDest;
        var lastDist = _lastDist;
        var baseDist = _baseDist;
        var cut = lastDest != null && lastDist != null && lastDest - distDest > dist - lastDist + 200.0;
        if (baseDist == null || cut || (lastDest != null && distDest > lastDest + 200.0)) {
            baseDist = dist;
            _baseDist = dist;
            _baseDest = distDest;
        }
        _lastDest = distDest;
        _lastDist = dist;
        var progress = _baseDest - distDest;
        var walked = dist - baseDist;
        if (progress >= MIN_PROGRESS && walked > 0.0) {
            ratio = WpUtil.clamp(walked / progress, LO, HI);
        }
        return ratio;
    }
}

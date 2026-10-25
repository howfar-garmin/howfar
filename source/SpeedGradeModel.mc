import Toybox.Lang;
import Toybox.Math;

// Speed-by-grade model. Mirrors tools/wpeta/model.py; keep the two in sync.
module Wp {
    const NUM_BINS = 41;
    const MIN_GRADE = -40.0;
    const MAX_GRADE = 40.0;
    const BIN_STEP = 2.0;

    const PRIOR_CAP = 20.0;          // most weight past runs get in a bin vs. this run's observations
    const MIN_WEIGHT = 3.0;          // bins with less total weight are filled from their neighbours
    const DEFAULT_FLAT_SPEED = 2.8;  // m/s, used only when there is no data at all
    const STORED_DECAY = 0.85;       // weight kept by the stored model each time a run is merged in
    const STORED_CAP = 200.0;
    const RUN_DECAY = 0.995;         // fatigue: weight kept by this run's older observations at each new one

    function binIndex(gradePct as Float) as Number {
        var g = WpUtil.clamp(gradePct, MIN_GRADE, MAX_GRADE);
        var i = ((g - MIN_GRADE) / BIN_STEP + 0.5).toNumber();
        return i > NUM_BINS - 1 ? NUM_BINS - 1 : i;
    }

    function binCenter(i as Number) as Float {
        return MIN_GRADE + i * BIN_STEP;
    }

    // Tobler's hiking function relative to flat ground (1.0 at 0%, peak ~1.19 at -5%)
    function toblerFactor(gradePct as Float) as Float {
        var x = (gradePct / 100.0 + 0.05).abs();
        return Math.pow(Math.E, -3.5 * x + 3.5 * 0.05).toFloat();
    }
}

// Per-bin mean pace (s/m) and weight (number of observations).
// Pace, not speed, is averaged: travel time is distance x pace, so the mean of speeds
// would make predicted times too short wherever speed varies. Strings use speed in m/s.
class ModelLayer {
    var paces as Array<Float>;
    var weights as Array<Float>;

    function initialize() {
        paces = new Array<Float>[Wp.NUM_BINS];
        weights = new Array<Float>[Wp.NUM_BINS];
        for (var i = 0; i < Wp.NUM_BINS; i++) {
            paces[i] = 0.0;
            weights[i] = 0.0;
        }
    }

    function addPace(i as Number, pace as Float, weight as Float) as Void {
        if (weight <= 0.0) {
            return;
        }
        var newW = weights[i] + weight;
        paces[i] = paces[i] + (pace - paces[i]) * weight / newW;
        weights[i] = newW;
    }

    function add(i as Number, speed as Float, weight as Float) as Void {
        if (speed > 0.0) {
            addPace(i, 1.0 / speed, weight);
        }
    }

    function speed(i as Number) as Float {
        return paces[i] > 0.0 ? 1.0 / paces[i] : 0.0;
    }

    function mergeFrom(other as ModelLayer, decay as Float, cap as Float) as Void {
        for (var i = 0; i < Wp.NUM_BINS; i++) {
            weights[i] = weights[i] * decay;
            addPace(i, other.paces[i], other.weights[i]);
            if (weights[i] > cap) {
                weights[i] = cap;
            }
        }
    }

    function totalWeight() as Float {
        var t = 0.0;
        for (var i = 0; i < Wp.NUM_BINS; i++) {
            t += weights[i];
        }
        return t;
    }

    // Flat array for Application.Storage: paces then weights
    function toArray() as Array<Float> {
        var a = new Array<Float>[2 * Wp.NUM_BINS];
        for (var i = 0; i < Wp.NUM_BINS; i++) {
            a[i] = paces[i];
            a[Wp.NUM_BINS + i] = weights[i];
        }
        return a;
    }

    function loadArray(a as Array) as Boolean {
        if (a.size() != 2 * Wp.NUM_BINS) {
            return false;
        }
        for (var i = 0; i < Wp.NUM_BINS; i++) {
            paces[i] = (a[i] as Numeric).toFloat();
            weights[i] = (a[Wp.NUM_BINS + i] as Numeric).toFloat();
        }
        return true;
    }

    // "v1;<grade>:<speed>:<weight>;..." as printed by tools/fit_to_speed_model.py
    function loadString(s as String) as Boolean {
        var parts = WpUtil.split(s, ';');
        if (parts.size() < 1 || !parts[0].equals("v1")) {
            return false;
        }
        for (var p = 1; p < parts.size(); p++) {
            var f = WpUtil.split(parts[p], ':');
            if (f.size() != 3) {
                continue;
            }
            var g = f[0].toFloat();
            var v = f[1].toFloat();
            var w = f[2].toFloat();
            if (g != null && v != null && w != null) {
                add(Wp.binIndex(g), v, w);
            }
        }
        return true;
    }
}

class SpeedGradeModel {
    var run as ModelLayer;        // this run, older observations fading (for predicting)
    var runTotal as ModelLayer;   // this run, all observations equal (what gets saved)
    var stored as ModelLayer;
    var imported as ModelLayer;
    var form as Float = 1.0;
    hidden var _curve as Array<Float>?;
    hidden var _priorCurve as Array<Float>?;

    function initialize() {
        run = new ModelLayer();
        runTotal = new ModelLayer();
        stored = new ModelLayer();
        imported = new ModelLayer();
    }

    function invalidate() as Void {
        _curve = null;
        _priorCurve = null;
    }

    function hasPrior() as Boolean {
        return stored.totalWeight() + imported.totalWeight() > 0.0;
    }

    function observe(gradePct as Float, speed as Float) as Void {
        for (var i = 0; i < Wp.NUM_BINS; i++) {
            run.weights[i] = run.weights[i] * Wp.RUN_DECAY;
        }
        run.add(Wp.binIndex(gradePct), speed, 1.0);
        runTotal.add(Wp.binIndex(gradePct), speed, 1.0);
        _curve = null;
    }

    function setForm(f as Float) as Void {
        if ((f - form).abs() > 0.005) {
            form = f;
            _curve = null;
        }
    }

    function commitRun() as Void {
        stored.mergeFrom(runTotal, Wp.STORED_DECAY, Wp.STORED_CAP);
        discardRun();
    }

    function discardRun() as Void {
        run = new ModelLayer();
        runTotal = new ModelLayer();
        invalidate();
    }

    // Pace (s/m) per bin. f is a speed ratio, so prior paces are divided by it.
    function buildCurve(useRun as Boolean, f as Float) as Array<Float> {
        var values = new Array<Float>[Wp.NUM_BINS];
        var valid = new Array<Boolean>[Wp.NUM_BINS];
        for (var i = 0; i < Wp.NUM_BINS; i++) {
            var wr = useRun ? run.weights[i] : 0.0;
            var ws = stored.weights[i];
            var wi = imported.weights[i];
            var pw = ws + wi;
            var pp = pw > 0.0 ? (stored.paces[i] * ws + imported.paces[i] * wi) / pw : 0.0;
            var pwEff = pw < Wp.PRIOR_CAP ? pw : Wp.PRIOR_CAP;
            var tot = wr + pwEff;
            values[i] = 0.0;
            valid[i] = false;
            if (tot >= Wp.MIN_WEIGHT) {
                values[i] = (run.paces[i] * wr + pp / f * pwEff) / tot;
                valid[i] = true;
            }
        }
        for (var i = 0; i < Wp.NUM_BINS; i++) {
            if (valid[i]) {
                continue;
            }
            var lo = i - 1;
            while (lo >= 0 && !valid[lo]) {
                lo--;
            }
            var hi = i + 1;
            while (hi < Wp.NUM_BINS && !valid[hi]) {
                hi++;
            }
            var c = Wp.binCenter(i);
            if (lo >= 0 && hi < Wp.NUM_BINS) {
                values[i] = values[lo] + (values[hi] - values[lo]) * (i - lo).toFloat() / (hi - lo);
            } else if (lo >= 0) {
                values[i] = values[lo] * Wp.toblerFactor(Wp.binCenter(lo)) / Wp.toblerFactor(c);
            } else if (hi < Wp.NUM_BINS) {
                values[i] = values[hi] * Wp.toblerFactor(Wp.binCenter(hi)) / Wp.toblerFactor(c);
            } else {
                values[i] = 1.0 / (Wp.DEFAULT_FLAT_SPEED * f * Wp.toblerFactor(c));
            }
        }
        return values;
    }

    // Speed (m/s) from the pace curve, interpolated in pace
    hidden function interp(curve as Array<Float>, gradePct as Float) as Float {
        var p = (WpUtil.clamp(gradePct, Wp.MIN_GRADE, Wp.MAX_GRADE) - Wp.MIN_GRADE) / Wp.BIN_STEP;
        var i = p.toNumber();
        var pace;
        if (i >= Wp.NUM_BINS - 1) {
            pace = curve[Wp.NUM_BINS - 1];
        } else {
            pace = curve[i] + (curve[i + 1] - curve[i]) * (p - i);
        }
        return pace < 5.0 ? 1.0 / pace : 0.2;
    }

    // Predicted speed (m/s) at a grade: this run blended with past runs scaled by today's form
    function predict(gradePct as Float) as Float {
        var c = _curve;
        if (c == null) {
            c = buildCurve(true, form);
            _curve = c;
        }
        return interp(c, gradePct);
    }

    // Past runs only, at normal form: the baseline the form factor is measured against
    function predictPrior(gradePct as Float) as Float {
        var c = _priorCurve;
        if (c == null) {
            c = buildCurve(false, 1.0);
            _priorCurve = c;
        }
        return interp(c, gradePct);
    }
}

import Toybox.Activity;
import Toybox.Application;
import Toybox.Graphics;
import Toybox.Lang;
import Toybox.WatchUi;

// Per-second logic mirrors FieldLogic in tools/wpeta/field.py.
class WaypointEtaView extends WatchUi.DataField {
    const MIN_OBS_TO_COMMIT = 20;  // ~500 m of moving data before a run updates the stored model
    const SMOOTHING = 0.2;
    const STORAGE_KEY = "stored";

    hidden var _model as SpeedGradeModel;
    hidden var _tracker as GradeTracker;
    hidden var _estimator as EtaEstimator;
    hidden var _scale as CourseScale;
    hidden var _profile as CourseProfile?;

    hidden var _etaSec as Number?;
    hidden var _name as String?;
    hidden var _usingProfile as Boolean = false;
    hidden var _smoothSpeed as Float?;
    hidden var _lastName as String?;
    hidden var _lastDist as Float = 0.0;

    function initialize() {
        DataField.initialize();
        _model = new SpeedGradeModel();
        _tracker = new GradeTracker();
        _estimator = new EtaEstimator(_model);
        _scale = new CourseScale();
        var stored = Application.Storage.getValue(STORAGE_KEY);
        if (stored instanceof Array) {
            _model.stored.loadArray(stored as Array);
        }
        loadSettings();
    }

    function loadSettings() as Void {
        var reset = Application.Properties.getValue("resetModel");
        if (reset instanceof Boolean && reset) {
            Application.Storage.deleteValue(STORAGE_KEY);
            _model.stored = new ModelLayer();
            Application.Properties.setValue("resetModel", false);
        }

        _model.imported = new ModelLayer();
        var s = Application.Properties.getValue("importedSpeedModel");
        if (s instanceof String && (s as String).length() > 0) {
            _model.imported.loadString(s as String);
        }
        _model.invalidate();

        _profile = null;
        var p = Application.Properties.getValue("courseProfile");
        if (p instanceof String && (p as String).length() > 0) {
            var cp = new CourseProfile(p as String);
            if (cp.isLoaded()) {
                _profile = cp;
            }
        }
    }

    function compute(info as Activity.Info) as Void {
        var timer = info.timerTime;
        var dist = info.elapsedDistance;
        var alt = info.altitude;
        if (info.timerState == Activity.TIMER_STATE_ON && timer != null && dist != null && alt != null) {
            if (_tracker.update(timer / 1000.0, dist, alt)) {
                var g = _tracker.lastGrade;
                var v = _tracker.lastSpeed;
                _estimator.observe(g, v, _tracker.lastDist);
                _model.observe(g, v);
            }
        }

        var distNext = info.distanceToNextPoint;
        var name = info.nameOfNextPoint;
        _name = name;
        if (distNext == null || distNext <= 0.0) {
            _etaSec = null;
            _smoothSpeed = null;
            return;
        }

        var distDest = info.distanceToDestination;
        if (info.timerState == Activity.TIMER_STATE_ON && dist != null && distDest != null) {
            _scale.update(dist, distDest);
        }
        var scale = _scale.ratio;

        var raw;
        var profile = _profile;
        if (profile != null && profile.update(name, distNext, distDest)) {
            raw = profile.remainingTime(distNext, _estimator, scale);
            _usingProfile = true;
        } else {
            var grade = 0.0;
            var elevNext = info.elevationAtNextPoint;
            if (alt != null && elevNext != null) {
                grade = WpUtil.clamp((elevNext - alt) / distNext * 100.0, Wp.MIN_GRADE, Wp.MAX_GRADE);
            }
            raw = _estimator.timeForGrade(distNext, grade, scale);
            _usingProfile = false;
        }

        // smooth the effective speed, not the time, so the countdown doesn't lag
        var lastName = _lastName;
        var sameName = (name == null && lastName == null)
            || (name != null && lastName != null && name.equals(lastName));
        if (!sameName || distNext > _lastDist + 50.0) {
            _smoothSpeed = null;
        }
        _lastName = name;
        _lastDist = distNext;

        var v = distNext / raw;
        var sv = _smoothSpeed;
        if (sv == null) {
            sv = v;
        } else {
            sv = sv + (v - sv) * SMOOTHING;
        }
        _smoothSpeed = sv;
        _etaSec = (distNext / sv + 0.5).toNumber();
    }

    // Activity saved or discarded: learn from it if it was a real run, then start fresh
    function onTimerReset() as Void {
        if (_tracker.observations >= MIN_OBS_TO_COMMIT) {
            _model.commitRun();
            Application.Storage.setValue(STORAGE_KEY, _model.stored.toArray() as Array<Application.Storage.ValueType>);
        } else {
            _model.discardRun();
        }
        _tracker.reset();
        _estimator.reset();
        _scale.reset();
        var profile = _profile;
        if (profile != null) {
            profile.reset();
        }
        _smoothSpeed = null;
        _lastName = null;
        _lastDist = 0.0;
        _etaSec = null;
    }

    const MIN_FONT_WITH_EXTRAS = 4;  // FONT_MEDIUM: smallest font the time gets when label and arrival are shown too

    hidden function fonts() as Array<Graphics.FontDefinition> {
        return [
            Graphics.FONT_NUMBER_THAI_HOT,
            Graphics.FONT_NUMBER_HOT,
            Graphics.FONT_NUMBER_MEDIUM,
            Graphics.FONT_NUMBER_MILD,
            Graphics.FONT_MEDIUM,
            Graphics.FONT_SMALL,
            Graphics.FONT_XTINY,
        ] as Array<Graphics.FontDefinition>;
    }

    // Index into fonts() of the largest font that fits text in maxW x maxH (the last one if none does)
    hidden function fitFont(dc as Graphics.Dc, text as String, maxW as Float, maxH as Float) as Number {
        var f = fonts();
        for (var i = 0; i < f.size() - 1; i++) {
            if (dc.getTextWidthInPixels(text, f[i]) <= maxW && dc.getFontHeight(f[i]) <= maxH) {
                return i;
            }
        }
        return f.size() - 1;
    }

    function onUpdate(dc as Graphics.Dc) as Void {
        var bg = getBackgroundColor();
        var fg = bg == Graphics.COLOR_BLACK ? Graphics.COLOR_WHITE : Graphics.COLOR_BLACK;
        dc.setColor(fg, bg);
        dc.clear();

        var w = dc.getWidth();
        var h = dc.getHeight();
        var obs = getObscurityFlags();
        var sidesObscured = (obs & (WatchUi.DataField.OBSCURE_LEFT | WatchUi.DataField.OBSCURE_RIGHT)) != 0;
        var maxW = w * (sidesObscured ? 0.72 : 0.94);
        var center = Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER;
        var f = fonts();

        var eta = _etaSec;
        var main = eta == null ? "--" : WpUtil.formatDuration(eta);

        // label and arrival only when the time can still be big; otherwise the time alone
        var withExtras = fitFont(dc, main, maxW, h * 0.5);
        if (h < 90 || withExtras > MIN_FONT_WITH_EXTRAS) {
            dc.drawText(w / 2, h / 2, f[fitFont(dc, main, maxW, h * 0.95)], main, center);
            return;
        }

        var topY = h * ((obs & WatchUi.DataField.OBSCURE_TOP) != 0 ? 0.24 : 0.15);
        var bottomY = h * ((obs & WatchUi.DataField.OBSCURE_BOTTOM) != 0 ? 0.76 : 0.85);
        var label = "WPT ETA";
        var name = _name;
        if (eta != null) {
            label = (_usingProfile ? "P " : "~ ") + (name != null ? name : "WPT");
            while (label.length() > 1 && dc.getTextWidthInPixels(label, Graphics.FONT_XTINY) > maxW) {
                label = label.substring(0, label.length() - 1) as String;
            }
        }
        dc.drawText(w / 2, topY, Graphics.FONT_XTINY, label, center);
        dc.drawText(w / 2, h * 0.5, f[withExtras], main, center);
        if (eta != null) {
            dc.drawText(w / 2, bottomY, Graphics.FONT_XTINY, "@ " + WpUtil.formatClock(eta), center);
        }
    }
}

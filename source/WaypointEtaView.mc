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
    hidden var _thenWord as String;   // "then", in the watch's language
    hidden var _viaWord as String;    // "via": the bottom line names a minor point on the way
    hidden var _learningWord as String;
    hidden var _thenName as String?;  // the minor point on the way, or the main point after the next one
    hidden var _thenVia as Boolean = false;
    hidden var _thenSec as Number?;
    hidden var _smoothSpeed as Float?;
    hidden var _lastName as String?;
    hidden var _lastDist as Float = 0.0;

    function initialize() {
        DataField.initialize();
        _model = new SpeedGradeModel();
        _tracker = new GradeTracker();
        _estimator = new EtaEstimator(_model);
        _scale = new CourseScale();
        _thenWord = WatchUi.loadResource(Rez.Strings.Then) as String;
        _viaWord = WatchUi.loadResource(Rez.Strings.Via) as String;
        _learningWord = WatchUi.loadResource(Rez.Strings.Learning) as String;
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
                _model.setRunDistance(dist);
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
            _thenName = null;
            _thenSec = null;
            return;
        }

        var distDest = info.distanceToDestination;
        if (info.timerState == Activity.TIMER_STATE_ON && dist != null && distDest != null) {
            _scale.update(dist, distDest);
        }
        var scale = _scale.ratio;

        var raw;
        var profile = _profile;
        if (profile != null && profile.update(name, distNext, distDest, dist, scale)) {
            // the next profile point, which may come before the watch's next point
            name = profile.targetName(name);
            distNext = profile.targetDist > 1.0 ? profile.targetDist : 1.0;
            raw = profile.targetTime(_estimator, scale);
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

        _name = name;

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
        var eta = (distNext / sv + 0.5).toNumber();
        _etaSec = eta;

        _thenName = null;
        _thenSec = null;
        _thenVia = false;
        if (_usingProfile && profile != null && profile.via != null) {
            _thenName = profile.followingName(profile.via as Number);
            _thenSec = (profile.viaTime(_estimator, scale) + 0.5).toNumber();
            _thenVia = true;
        } else if (_usingProfile && profile != null) {
            var i = profile.following();
            if (i != null) {
                _thenName = profile.followingName(i);
                _thenSec = eta + (profile.followingTime(i, _estimator, scale) + 0.5).toNumber();
            }
        }
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
        _thenName = null;
        _thenSec = null;
    }

    const MIN_FONT_WITH_EXTRAS = 4;  // FONT_MEDIUM: smallest font the time gets when label and arrival are shown too
    const MIN_HEIGHT_WITH_THEN = 150;  // px: fields this tall also show the checkpoint after the next
    const LEARN_OBS = 160;  // ~4 km of moving: until then today's form is still a guess (grey digits)

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
        var parts = eta == null ? ["--", ""] as Array<String> : WpUtil.etaText(eta);
        var main = parts[0];
        var unit = parts[1];
        var learning = eta != null && _tracker.observations < LEARN_OBS;
        var timeColor = !learning ? fg : (bg == Graphics.COLOR_BLACK ? Graphics.COLOR_LT_GRAY : Graphics.COLOR_DK_GRAY);
        // the unit sits next to the digits, so they get the rest of the width
        var unitW = unit.length() > 0 ? dc.getTextWidthInPixels(unit, Graphics.FONT_XTINY) + 4 : 0;
        var digitsW = maxW - unitW;

        // the checkpoint after the next on tall fields, while the time can still be big
        var thenName = _thenName;
        var thenSec = _thenSec;
        var withThen = eta != null && thenName != null && thenSec != null && h >= MIN_HEIGHT_WITH_THEN
            && fitFont(dc, main, digitsW, h * 0.36) <= MIN_FONT_WITH_EXTRAS;

        // label and arrival only when the time can still be big; otherwise the time alone
        var withExtras = fitFont(dc, main, digitsW, h * (withThen ? 0.36 : 0.5));
        if (h < 90 || withExtras > MIN_FONT_WITH_EXTRAS) {
            drawTime(dc, w / 2, h / 2, f[fitFont(dc, main, digitsW, h * 0.95)], main, unit, timeColor, fg, bg);
            return;
        }

        var bottomObscured = (obs & WatchUi.DataField.OBSCURE_BOTTOM) != 0;
        var topY = h * ((obs & WatchUi.DataField.OBSCURE_TOP) != 0 ? 0.24 : 0.15);
        var bottomY = h * (bottomObscured ? 0.76 : 0.85);
        var label = "WPT ETA";
        var name = _name;
        if (eta != null) {
            label = (_usingProfile ? "P " : "~ ") + (name != null ? name : "WPT");
            label = fitText(dc, label, "", maxW);
        }
        dc.drawText(w / 2, topY, Graphics.FONT_XTINY, label, center);
        var arrive = eta == null ? "" : "@ " + WpUtil.formatClock(eta) + (learning ? " " + _learningWord : "");
        if (withThen) {
            drawTime(dc, w / 2, h * 0.45, f[withExtras], main, unit, timeColor, fg, bg);
            dc.drawText(w / 2, h * 0.64, Graphics.FONT_XTINY, arrive, center);
            var then = fitText(dc, (_thenVia ? _viaWord : _thenWord) + " " + thenName, " @ " + WpUtil.formatClock(thenSec as Number),
                bottomObscured ? w * 0.8 : maxW);  // a round screen is still 0.8 wide this low
            dc.drawText(w / 2, h * (bottomObscured ? 0.80 : 0.86), Graphics.FONT_XTINY, then, center);
            return;
        }
        drawTime(dc, w / 2, h * 0.5, f[withExtras], main, unit, timeColor, fg, bg);
        if (eta != null) {
            dc.drawText(w / 2, bottomY, Graphics.FONT_XTINY, arrive, center);
        }
    }

    // The digits centred on x, with the unit small after them, level with their lower part
    hidden function drawTime(dc as Graphics.Dc, x as Number or Float, y as Number or Float, font as Graphics.FontDefinition,
            digits as String, unit as String, color as Graphics.ColorType, fg as Graphics.ColorType, bg as Graphics.ColorType) as Void {
        var dw = dc.getTextWidthInPixels(digits, font);
        var uw = unit.length() > 0 ? dc.getTextWidthInPixels(unit, Graphics.FONT_XTINY) + 4 : 0;
        var left = x - (dw + uw) / 2.0;
        dc.setColor(color, Graphics.COLOR_TRANSPARENT);
        dc.drawText(left, y, font, digits, Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
        dc.setColor(fg, Graphics.COLOR_TRANSPARENT);
        if (uw > 0) {
            dc.drawText(left + dw + 4, y + dc.getFontHeight(font) * 0.18, Graphics.FONT_XTINY, unit,
                Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
        }
    }

    // text + tail, shortening text until it fits maxW in FONT_XTINY
    hidden function fitText(dc as Graphics.Dc, text as String, tail as String, maxW as Float) as String {
        while (text.length() > 1 && dc.getTextWidthInPixels(text + tail, Graphics.FONT_XTINY) > maxW) {
            text = text.substring(0, text.length() - 1) as String;
        }
        return text + tail;
    }
}

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
    hidden var _inWord as String;     // "in": the minor point on the way and the time to it
    hidden var _learningWord as String;
    hidden var _thenName as String?;  // the main profile point after the next one
    hidden var _thenSec as Number?;   // its leg's moving time, from leaving the point before it
    hidden var _then2Name as String?; // and the main point after that
    hidden var _then2Sec as Number?;  // ... and its leg's
    hidden var _viaName as String?;   // the next minor profile point on the way
    hidden var _viaSec as Number?;
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
        _inWord = WatchUi.loadResource(Rez.Strings.In) as String;
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
            _viaName = null;
            _viaSec = null;
            _then2Name = null;
            _then2Sec = null;
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
        _viaName = null;
        _viaSec = null;
        _then2Name = null;
        _then2Sec = null;
        if (_usingProfile && profile != null && profile.via != null) {
            _viaName = profile.followingName(profile.via as Number);
            _viaSec = (profile.viaTime(_estimator, scale) + 0.5).toNumber();
        }
        if (_usingProfile && profile != null) {
            var i = profile.following();
            if (i != null) {
                // leg times: stops at the checkpoints in between can't be known, so these don't
                // count from now but from leaving the point before
                var t1 = profile.followingTime(i, _estimator, scale);
                _thenName = profile.followingName(i);
                _thenSec = (t1 + 0.5).toNumber();
                var i2 = profile.followingAfter(i);
                if (i2 != null) {
                    _then2Name = profile.followingName(i2);
                    _then2Sec = (profile.followingTime(i2, _estimator, scale) - t1 + 0.5).toNumber();
                }
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
        _viaName = null;
        _viaSec = null;
        _then2Name = null;
        _then2Sec = null;
    }

    const MIN_FONT_WITH_EXTRAS = 4;  // FONT_MEDIUM: smallest font the time gets when label and arrival are shown too
    const MIN_HEIGHT_WITH_THEN = 150;  // px: fields this tall also show the checkpoint after the next
    hidden var _dotR as Float = 3.0;  // px: radius of the coloured dot before each time
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
        // a coloured dot before each time says how far off it may be
        _dotR = w * 0.013 > 2.0 ? w * 0.013 : 2.0;
        var dotW = eta != null ? _dotR * 6 + 2 : 0.0;  // the big number's dot is twice the size
        var dot = eta != null ? dotColor(eta, bg) : null;
        // the unit sits next to the digits, so they get the rest of the width
        var unitW = unit.length() > 0 ? dc.getTextWidthInPixels(unit, Graphics.FONT_XTINY) + 4 : 0;
        var digitsW = maxW - unitW - dotW;

        // tall fields: the arrival beside the time, freeing two lines below it for the minor point
        // on the way (via) and the main point after the next (then), while the time can still be big
        var thenName = _thenName;
        var thenSec = _thenSec;
        var viaName = _viaName;
        var viaSec = _viaSec;
        var arriveSide = eta == null ? "" : "@" + WpUtil.formatClock(eta);
        var sideW = (unitW > dc.getTextWidthInPixels(arriveSide, Graphics.FONT_XTINY) + 4
            ? unitW : dc.getTextWidthInPixels(arriveSide, Graphics.FONT_XTINY) + 4);
        var withThen = eta != null && (thenName != null || viaName != null) && h >= MIN_HEIGHT_WITH_THEN
            && fitFont(dc, main, maxW - sideW - dotW, h * 0.5) <= MIN_FONT_WITH_EXTRAS;

        // label and arrival only when the time can still be big; otherwise the time alone
        var withExtras = fitFont(dc, main, withThen ? maxW - sideW - dotW : digitsW, h * 0.5);
        if (h < 90 || withExtras > MIN_FONT_WITH_EXTRAS) {
            drawTime(dc, w / 2, h / 2, f[fitFont(dc, main, digitsW, h * 0.95)], main, unit, timeColor, fg, dot);
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
        var arrive = eta == null ? "" : "@ " + WpUtil.formatClock(eta) + (learning ? " " + _learningWord : "");
        if (!withThen) {
            dc.drawText(w / 2, topY, Graphics.FONT_XTINY, label, center);
        } else {
            // top to bottom in the order you meet them: the minor point on the way (grey, its time
            // from now), the main checkpoint and the time to it, then the next main checkpoints with
            // their leg's moving time (+h:mm). The arrival is the big number's only.
            var grey = bg == Graphics.COLOR_BLACK ? Graphics.COLOR_LT_GRAY : Graphics.COLOR_DK_GRAY;
            var hasVia = viaName != null && viaSec != null;
            var botW = (bottomObscured ? w * 0.8 : maxW) - dotW;  // a round screen is still 0.8 wide this low
            var then2Name = _then2Name;
            var then2Sec = _then2Sec;
            var lowY = h * (hasVia ? 0.74 : 0.67);
            var lowW = (sidesObscured ? w * 0.84 : maxW) - dotW;  // a round screen is about 0.85 wide there
            var lowerY = h * (bottomObscured ? 0.80 : 0.84);
            if (hasVia) {
                // near the top a round screen is only about 0.6 wide
                drawLine(dc, w / 2, h * 0.13, fitText(dc, viaName as String, " " + _inWord + " " + WpUtil.etaHm(viaSec as Number), w * 0.6 - dotW),
                    grey, dotColor(viaSec as Number, bg));
                dc.setColor(fg, Graphics.COLOR_TRANSPARENT);
            }
            dc.drawText(w / 2, hasVia ? h * 0.26 : topY, Graphics.FONT_XTINY, label, center);
            drawTimeWithArrival(dc, w / 2, h * (hasVia ? 0.49 : 0.42), f[withExtras], main, unit, arriveSide, timeColor, fg, dot);
            var lowFree = true;
            var lowerFree = !hasVia;
            if (thenName != null && thenSec != null) {
                drawLine(dc, w / 2, lowY, fitText(dc, _thenWord + " " + thenName, " +" + WpUtil.etaHm(thenSec as Number), lowW),
                    fg, dotColor(thenSec as Number, bg));
                lowFree = false;
                if (!hasVia && then2Name != null && then2Sec != null) {
                    drawLine(dc, w / 2, lowerY, fitText(dc, _thenWord + " " + then2Name, " +" + WpUtil.etaHm(then2Sec as Number), botW),
                        fg, dotColor(then2Sec as Number, bg));
                    lowerFree = false;
                }
            }
            // while learning, the word takes a free line (the grey digits say it anyway)
            if (learning && (lowFree || lowerFree)) {
                drawLine(dc, w / 2, lowFree ? lowY : lowerY, _learningWord, grey, null);
            }
            dc.setColor(fg, Graphics.COLOR_TRANSPARENT);
            return;
        }
        drawTime(dc, w / 2, h * 0.5, f[withExtras], main, unit, timeColor, fg, dot);
        if (eta != null) {
            dc.drawText(w / 2, bottomY, Graphics.FONT_XTINY, arrive, center);
        }
    }

    // Green, yellow or red for a time this far away (WpUtil.reliability), darker on white
    hidden function dotColor(seconds as Number, bg as Graphics.ColorType) as Graphics.ColorType {
        var r = WpUtil.reliability(seconds);
        if (r == 0) {
            return bg == Graphics.COLOR_BLACK ? Graphics.COLOR_GREEN : Graphics.COLOR_DK_GREEN;
        }
        return r == 1 ? Graphics.COLOR_YELLOW : Graphics.COLOR_RED;
    }

    // The dot of radius r, starting at x, centred on y; returns the width it takes with the gap after it
    hidden function drawDot(dc as Graphics.Dc, x as Float, y as Number or Float, color as Graphics.ColorType?, r as Float) as Float {
        if (color == null) {
            return 0.0;
        }
        dc.setColor(color, Graphics.COLOR_TRANSPARENT);
        dc.fillCircle(x + r, y, r);
        return r * 3 + 2;
    }

    // A small line centred on x, after its dot when it has one
    hidden function drawLine(dc as Graphics.Dc, x as Number or Float, y as Number or Float, text as String,
            color as Graphics.ColorType, dot as Graphics.ColorType?) as Void {
        var tw = dc.getTextWidthInPixels(text, Graphics.FONT_XTINY);
        var left = x - (tw + (dot != null ? _dotR * 3 + 2 : 0.0)) / 2.0;
        left += drawDot(dc, left, y, dot, _dotR);
        dc.setColor(color, Graphics.COLOR_TRANSPARENT);
        dc.drawText(left, y, Graphics.FONT_XTINY, text, Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
    }

    // The digits centred on x (after the dot), with the unit small after them, level with their lower part
    hidden function drawTime(dc as Graphics.Dc, x as Number or Float, y as Number or Float, font as Graphics.FontDefinition,
            digits as String, unit as String, color as Graphics.ColorType, fg as Graphics.ColorType, dot as Graphics.ColorType?) as Void {
        var dw = dc.getTextWidthInPixels(digits, font);
        var uw = unit.length() > 0 ? dc.getTextWidthInPixels(unit, Graphics.FONT_XTINY) + 4 : 0;
        var left = x - (dw + uw + (dot != null ? _dotR * 6 + 2 : 0.0)) / 2.0;
        left += drawDot(dc, left, y, dot, _dotR * 2);
        dc.setColor(color, Graphics.COLOR_TRANSPARENT);
        dc.drawText(left, y, font, digits, Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
        dc.setColor(fg, Graphics.COLOR_TRANSPARENT);
        if (uw > 0) {
            dc.drawText(left + dw + 4, y + dc.getFontHeight(font) * 0.18, Graphics.FONT_XTINY, unit,
                Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
        }
    }

    // The digits centred on x (after the dot) with the unit small after them, top, and the arrival under the unit
    hidden function drawTimeWithArrival(dc as Graphics.Dc, x as Number or Float, y as Number or Float,
            font as Graphics.FontDefinition, digits as String, unit as String, arrival as String,
            color as Graphics.ColorType, fg as Graphics.ColorType, dot as Graphics.ColorType?) as Void {
        var dw = dc.getTextWidthInPixels(digits, font);
        var uw = dc.getTextWidthInPixels(unit, Graphics.FONT_XTINY);
        var aw = dc.getTextWidthInPixels(arrival, Graphics.FONT_XTINY);
        var sw = (uw > aw ? uw : aw) + 4;
        var left = x - (dw + sw + (dot != null ? _dotR * 6 + 2 : 0.0)) / 2.0;
        left += drawDot(dc, left, y, dot, _dotR * 2);
        var fh = dc.getFontHeight(font);
        dc.setColor(color, Graphics.COLOR_TRANSPARENT);
        dc.drawText(left, y, font, digits, Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
        dc.setColor(fg, Graphics.COLOR_TRANSPARENT);
        dc.drawText(left + dw + 4, y - fh * 0.08, Graphics.FONT_XTINY, unit, Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
        dc.drawText(left + dw + 4, y + fh * 0.14, Graphics.FONT_XTINY, arrival, Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
    }

    // text + tail, shortening text until it fits maxW in FONT_XTINY
    hidden function fitText(dc as Graphics.Dc, text as String, tail as String, maxW as Float) as String {
        while (text.length() > 1 && dc.getTextWidthInPixels(text + tail, Graphics.FONT_XTINY) > maxW) {
            text = text.substring(0, text.length() - 1) as String;
        }
        return text + tail;
    }
}

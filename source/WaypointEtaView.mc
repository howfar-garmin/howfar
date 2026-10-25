import Toybox.Activity;
import Toybox.Application;
import Toybox.Graphics;
import Toybox.Lang;
import Toybox.Math;
import Toybox.System;
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
    hidden var _minorNames as Array<String> = [] as Array<String>;  // the first minor points on the way
    hidden var _minorSecs as Array<Number> = [] as Array<Number>;   // ... and the time to each, from now
    hidden var _minorCount as Number = 0;                            // all of them, before the main checkpoint
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
            _minorNames = [] as Array<String>;
            _minorSecs = [] as Array<Number>;
            _minorCount = 0;
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
        _minorNames = [] as Array<String>;
        _minorSecs = [] as Array<Number>;
        _minorCount = 0;
        _then2Name = null;
        _then2Sec = null;
        if (_usingProfile && profile != null) {
            var vias = profile.vias;
            _minorCount = vias.size();
            for (var j = 0; j < vias.size() && j < MAX_MINOR_LINES; j++) {
                _minorNames.add(profile.followingName(vias[j]));
                _minorSecs.add((profile.minorTime(vias[j], _estimator, scale) + 0.5).toNumber());
            }
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
        _minorNames = [] as Array<String>;
        _minorSecs = [] as Array<Number>;
        _minorCount = 0;
        _then2Name = null;
        _then2Sec = null;
    }

    const MIN_FONT_WITH_EXTRAS = 4;  // FONT_MEDIUM: smallest font the time gets when label and arrival are shown too
    const MIN_HEIGHT_WITH_THEN = 150;  // px: fields this tall show the points around the checkpoint (full screen)
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

        // the arrival beside the time; on tall fields, the points around it in the order you meet them
        var thenName = _thenName;
        var minorCount = _minorCount;
        var arriveSide = eta == null ? "" : "@" + WpUtil.formatClock(eta);
        var arriveW = dc.getTextWidthInPixels(arriveSide, Graphics.FONT_XTINY) + 4;
        var sideW = unitW > arriveW ? unitW : arriveW;
        var grey = bg == Graphics.COLOR_BLACK ? Graphics.COLOR_LT_GRAY : Graphics.COLOR_DK_GRAY;
        var lineH = dc.getFontHeight(Graphics.FONT_XTINY);
        var label = "WPT ETA";
        var name = _name;
        if (eta != null) {
            label = (_usingProfile ? "P " : "~ ") + (name != null ? name : "WPT");
            label = fitText(dc, label, "", maxW);
        }

        // the list only on a field of its own (a data screen with one field); smaller fields get the countdown
        var fullScreen = h >= System.getDeviceSettings().screenHeight * 0.75;
        if (eta != null && fullScreen && h >= MIN_HEIGHT_WITH_THEN && (thenName != null || minorCount > 0)
                && drawList(dc, w, h, f, main, unit, arriveSide, sideW, dotW, dot, timeColor, fg, bg, grey, lineH, label,
                    learning, sidesObscured)) {
            return;
        }

        // label and arrival only when the time can still be big; otherwise the time alone
        var withExtras = fitFont(dc, main, maxW - sideW - dotW, h * 0.6);
        if (h < 90 || withExtras > MIN_FONT_WITH_EXTRAS) {
            drawTime(dc, w / 2, h / 2, f[fitFont(dc, main, digitsW, h * 0.95)], main, unit, timeColor, fg, dot);
            return;
        }
        // the countdown: the main checkpoint, the time with its arrival, and the word while learning
        var topY = h * ((obs & WatchUi.DataField.OBSCURE_TOP) != 0 ? 0.24 : 0.15);
        var bottomY = h * ((obs & WatchUi.DataField.OBSCURE_BOTTOM) != 0 ? 0.76 : 0.85);
        dc.drawText(w / 2, topY, Graphics.FONT_XTINY, label, center);
        if (eta == null) {
            drawTime(dc, w / 2, h * 0.55, f[withExtras], main, unit, timeColor, fg, null);
            return;
        }
        drawTimeWithArrival(dc, w / 2, h * 0.55, f[withExtras], main, unit, arriveSide, timeColor, fg, dot);
        if (learning) {
            drawLine(dc, w / 2, bottomY, _learningWord, grey, null);
        }
    }

    const MAX_MINOR_LINES = 3;

    // A full-screen field, top to bottom in the order you meet them: the minor points on the way
    // (grey, each with its time from now; the last line shown counts the others), the main
    // checkpoint with the time to it and the arrival, then the next main checkpoints with their
    // leg's moving time (+h:mm). Small screens get two of these lines, big ones four; minor points
    // come first. Returns false when even the main checkpoint alone doesn't fit.
    hidden function drawList(dc as Graphics.Dc, w as Number, h as Number, f as Array<Graphics.FontDefinition>,
            main as String, unit as String, arriveSide as String, sideW as Number or Float, dotW as Float,
            dot as Graphics.ColorType?, timeColor as Graphics.ColorType, fg as Graphics.ColorType,
            bg as Graphics.ColorType, grey as Graphics.ColorType, lineH as Number, label as String,
            learning as Boolean, round as Boolean) as Boolean {
        var center = Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER;
        var budget = h >= 400 ? 4 : 2;
        var minors = _minorNames.size();
        var m = minors < budget ? minors : budget;
        var thens = _thenName != null && _thenSec != null ? (_then2Name != null && _then2Sec != null ? 2 : 1) : 0;
        var t = budget - m < thens ? budget - m : thens;
        var note = learning && m + t < budget ? 1 : 0;
        var maxW = w * (round ? 0.72 : 0.94);
        while (true) {
            var small = m + t + note;
            // the number font's top and bottom padding may overlap the lines around it
            var avail = (h * 0.86 - (small + 1) * lineH) / 0.75;
            var fi = fitFont(dc, main, maxW - sideW - dotW, avail);
            if (fi <= MIN_FONT_WITH_EXTRAS) {
                var bigH = dc.getFontHeight(f[fi]) * 0.75;
                var y = (h - (small + 1) * lineH - bigH) / 2.0 + lineH / 2.0;
                for (var j = 0; j < m; j++) {
                    var tail = " " + _inWord + " " + WpUtil.etaHm(_minorSecs[j]);
                    if (j == m - 1 && _minorCount > m) {
                        tail += " (+" + (_minorCount - m) + ")";
                    }
                    drawLine(dc, w / 2, y, fitText(dc, _minorNames[j], tail, chordW(w, h, y, round) - dotW / 2), grey,
                        dotColor(_minorSecs[j], bg));
                    y += lineH;
                }
                dc.setColor(fg, Graphics.COLOR_TRANSPARENT);
                dc.drawText(w / 2, y, Graphics.FONT_XTINY, label, center);
                y += lineH / 2.0 + bigH / 2.0;
                drawTimeWithArrival(dc, w / 2, y, f[fi], main, unit, arriveSide, timeColor, fg, dot);
                y += bigH / 2.0 + lineH / 2.0;
                if (t > 0) {
                    var ts = _thenSec as Number;
                    drawLine(dc, w / 2, y, fitText(dc, _thenWord + " " + _thenName, " +" + WpUtil.etaHm(ts), chordW(w, h, y, round) - dotW / 2),
                        fg, dotColor(ts, bg));
                    y += lineH;
                }
                if (t > 1) {
                    var ts2 = _then2Sec as Number;
                    drawLine(dc, w / 2, y, fitText(dc, _thenWord + " " + _then2Name, " +" + WpUtil.etaHm(ts2), chordW(w, h, y, round) - dotW / 2),
                        fg, dotColor(ts2, bg));
                    y += lineH;
                }
                if (note > 0) {
                    drawLine(dc, w / 2, y, _learningWord, grey, null);
                }
                dc.setColor(fg, Graphics.COLOR_TRANSPARENT);
                return true;
            }
            // not enough room: drop the learning word, then the "then" lines, then minor lines
            if (note > 0) {
                note = 0;
            } else if (t > 0) {
                t--;
            } else if (m > 1) {
                m--;
            } else {
                return false;
            }
        }
        return false;
    }

    // Width for a line centred at y: the chord of a round screen there, with a little margin
    hidden function chordW(w as Number, h as Number, y as Number or Float, round as Boolean) as Float {
        if (!round) {
            return w * 0.94;
        }
        var r = w / 2.0;
        var d = y - h / 2.0;
        var c = r * r - d * d;
        return c > 0 ? Math.sqrt(c).toFloat() * 2 * 0.9 : 0.0;
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

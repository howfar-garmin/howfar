import Toybox.Lang;
import Toybox.System;
import Toybox.Time;
import Toybox.Time.Gregorian;

module WpUtil {

    function clamp(x as Float, lo as Float, hi as Float) as Float {
        if (x < lo) {
            return lo;
        }
        if (x > hi) {
            return hi;
        }
        return x;
    }

    // Splits on a single character. Empty parts are kept.
    function split(str as String, delim as Char) as Array<String> {
        var parts = [] as Array<String>;
        var chars = str.toCharArray();
        var start = 0;
        for (var i = 0; i < chars.size(); i++) {
            if (chars[i] == delim) {
                parts.add(str.substring(start, i) as String);
                start = i + 1;
            }
        }
        parts.add(str.substring(start, chars.size()) as String);
        return parts;
    }

    // Rounding step (s) for a time this far away: the prediction is good to ~10-15% of the
    // time left, so seconds two hours out would promise far more than it knows
    function etaStep(seconds as Number) as Number {
        return seconds >= 13500 ? 1800 : (seconds >= 6750 ? 900 : (seconds >= 3450 ? 300 : (seconds >= 300 ? 60 : 1)));
    }

    // What the countdown shows: [digits, unit]. h:mm in 30-minute steps from four hours out,
    // 15-minute steps from two and 5-minute steps from one,
    // whole minutes from 5 minutes out, m:ss in the last 5 minutes.
    function etaText(seconds as Number) as Array<String> {
        if (seconds < 0) {
            seconds = 0;
        }
        var step = etaStep(seconds);
        var r = ((seconds + step / 2) / step) * step;
        if (r >= 3600) {
            return [(r / 3600).format("%d") + ":" + ((r % 3600) / 60).format("%02d"), "h"] as Array<String>;
        }
        if (r >= 300) {
            return [(r / 60).format("%d"), "min"] as Array<String>;
        }
        return [(r / 60).format("%d") + ":" + (r % 60).format("%02d"), "min"] as Array<String>;
    }

    // Clock time `seconds` from now, in the watch's 12/24 h setting, rounded like the countdown
    // Time to go as h:mm, for the lines under the countdown: rounded like it, whole minutes
    // in the last 5 minutes
    function etaHm(seconds as Number) as String {
        if (seconds < 0) {
            seconds = 0;
        }
        var step = etaStep(seconds) > 60 ? etaStep(seconds) : 60;
        var r = ((seconds + step / 2) / step) * step;
        return (r / 3600).format("%d") + ":" + ((r % 3600) / 60).format("%02d");
    }

    function formatClock(seconds as Number) as String {
        var info = Gregorian.info(Time.now().add(new Time.Duration(seconds)), Time.FORMAT_SHORT);
        var step = etaStep(seconds) >= 300 ? etaStep(seconds) / 60 : 1;
        var mins = (info.hour as Number) * 60 + (info.min as Number) + ((info.sec as Number) >= 30 ? 1 : 0);
        mins = (((mins + step / 2) / step) * step) % 1440;
        var hour = mins / 60;
        if (!System.getDeviceSettings().is24Hour) {
            hour = hour % 12;
            if (hour == 0) {
                hour = 12;
            }
        }
        return hour.format("%d") + ":" + (mins % 60).format("%02d");
    }

    // Case-insensitive; also matches when one name is a prefix (>= 3 chars) of the
    // other, since the watch may truncate course point names.
    function namesMatch(a as String, b as String) as Boolean {
        a = a.toLower();
        b = b.toLower();
        if (a.equals(b)) {
            return true;
        }
        var shorter = a.length() <= b.length() ? a : b;
        var longer = a.length() <= b.length() ? b : a;
        return shorter.length() >= 3 && (longer.substring(0, shorter.length()) as String).equals(shorter);
    }
}

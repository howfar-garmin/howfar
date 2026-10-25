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

    // m:ss below an hour, h:mm:ss above
    function formatDuration(seconds as Number) as String {
        if (seconds < 0) {
            seconds = 0;
        }
        var h = seconds / 3600;
        var m = (seconds % 3600) / 60;
        var s = seconds % 60;
        if (h > 0) {
            return h.format("%d") + ":" + m.format("%02d") + ":" + s.format("%02d");
        }
        return m.format("%d") + ":" + s.format("%02d");
    }

    // Clock time `seconds` from now, in the watch's 12/24 h setting
    function formatClock(seconds as Number) as String {
        var info = Gregorian.info(Time.now().add(new Time.Duration(seconds)), Time.FORMAT_SHORT);
        var hour = info.hour as Number;
        if (!System.getDeviceSettings().is24Hour) {
            hour = hour % 12;
            if (hour == 0) {
                hour = 12;
            }
        }
        return hour.format("%d") + ":" + (info.min as Number).format("%02d");
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

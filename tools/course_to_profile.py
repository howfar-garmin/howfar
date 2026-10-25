#!/usr/bin/env python3
"""Turn a course into the elevation profile the data field uses between course points.

    python tools/course_to_profile.py course.fit
    python tools/course_to_profile.py course.gpx --step 100

FIT courses use their course points. GPX courses use their <wpt> waypoints, placed on
the track at the nearest track point. Prints a string to paste into the data field's
"Course profile" setting. Without --step it picks the finest step that fits in --max-len.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from wpeta.profile import best_profile, parse_profile  # noqa: E402
from wpeta.readers import read_course  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("course", help="course .fit or .gpx file")
    ap.add_argument("--step", type=int, help="metres per grade value (default: automatic)")
    ap.add_argument("--max-len", type=int, default=4000, help="longest string to produce (default 4000)")
    ap.add_argument("-q", "--quiet", action="store_true", help="print only the settings string")
    args = ap.parse_args()

    skipped: list[str] = []
    points, cps = read_course(args.course, skipped=skipped)
    if skipped and not args.quiet:
        print(f"Skipped {len(skipped)} waypoints more than 200 m off the track or another race's finish.", file=sys.stderr)
    if not cps:
        print("Warning: the course has no course points/waypoints; only the finish segment is included.", file=sys.stderr)
    try:
        step, text = best_profile(points, cps, args.max_len, args.step)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if not args.quiet:
        _, entries = parse_profile(text)
        print(f"step {step} m, {len(text)} characters", file=sys.stderr)
        for name, length, grades in entries:
            gain = sum(max(g, 0) for g in grades) / 1000 * step
            print(f"  {name:<20} {length / 1000:6.2f} km  ~{gain:4.0f} m up", file=sys.stderr)
        if len(text) > args.max_len:
            print(f"Warning: longer than {args.max_len} characters; use a larger --step.", file=sys.stderr)
        print(file=sys.stderr)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

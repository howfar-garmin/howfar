#!/usr/bin/env python3
"""Writes web-tests/fixtures/: synthetic courses (GPX and FIT) and the profile texts the
Python tools make from them, which web-tests/core.test.mjs checks the browser code against.
With --private it also writes the expected texts for the race files in courses/
(kept out of git) to web-tests/private-expected.json.

    .venv/bin/python tools/tests/make_web_fixtures.py [--private]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE), str(HERE.parent)]

from synth import samples, write_fit, write_gpx  # noqa: E402
from wpeta.profile import best_profile  # noqa: E402
from wpeta.readers import read_course  # noqa: E402

COURSE = [(1500, 0, 3), (1500, 8, 3), (2000, -5, 3)]
POINTS = [("Climb", 1500), ("Water; refill", 3000)]


def expected_for(courses):
    out = {"profiles": {}}
    for name, path in courses.items():
        skipped = []
        pts, cps = read_course(str(path), skipped=skipped)
        step, text = best_profile(pts, cps, 4000)
        out["profiles"][name] = {"step": step, "text": text, "skipped": skipped}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", action="store_true", help="also the race files in courses/")
    args = ap.parse_args()

    fx = ROOT / "web-tests" / "fixtures"
    fx.mkdir(parents=True, exist_ok=True)
    write_fit(fx / "course.fit", samples(COURSE), POINTS, file_type=6)
    write_gpx(fx / "course.gpx", samples(COURSE), POINTS, with_time=False)
    # a course GPX with a waypoint from somewhere else, which must be dropped
    text = (fx / "course.gpx").read_text().replace("<trk>", '<wpt lat="46.5" lon="7.5"><name>Other stage</name></wpt><trk>')
    (fx / "course-extra-wpt.gpx").write_text(text)

    expected = expected_for(
        {"course.fit": fx / "course.fit", "course.gpx": fx / "course.gpx", "course-extra-wpt.gpx": fx / "course-extra-wpt.gpx"},
    )
    (fx / "expected.json").write_text(json.dumps(expected, indent=1, ensure_ascii=False))
    print("fixtures:", sorted(p.name for p in fx.iterdir()))

    if args.private:
        courses = {p.name: p for p in sorted((ROOT / "courses").glob("*")) if p.suffix.lower() in (".gpx", ".fit")}
        priv = expected_for(courses)
        (ROOT / "web-tests" / "private-expected.json").write_text(json.dumps(priv, indent=1, ensure_ascii=False))
        print("private:", list(courses))
    return 0


if __name__ == "__main__":
    sys.exit(main())

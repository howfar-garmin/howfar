#!/usr/bin/env python3
"""How long a stretch should the slope be measured over? Replays the races of benchmark.py
(and, with --activities, every activity of at least 25 km with virtual checkpoints) with
GradeTracker.WINDOW set to each value, for the field's learning and for the pasted pace alike.

    python tools/research/test_window.py [--activities FOLDER]
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import benchmark as B  # noqa: E402
import benchmark_activities as BA  # noqa: E402
import predictors as P  # noqa: E402
import scenario as S  # noqa: E402
from wpeta import model as M  # noqa: E402
from wpeta.field import shown_seconds  # noqa: E402

WINDOWS = [40.0, 60.0, 100.0, 150.0, 200.0]
CONFIGS = {"profile only": dict(past=False, ahead=True, raceday=True), "full race prep": dict(past=True, ahead=True, raceday=True)}


def errs(rows):
    return [abs(shown_seconds(eta) - am) / 60 for t, k, dn, eta, act, am in rows if am <= 3600]


def race_job(args):
    key, window, cname = args
    M.GradeTracker.WINDOW = window
    rows = S.run(B.race(key), B.make(CONFIGS[cname], key), trail_ahead=True)
    return key, window, cname, errs(rows)


def activity_job(args):
    path, window = args
    M.GradeTracker.WINDOW = window
    race = BA.as_race(Path(path).name, BA.load(Path(path)))
    rows = S.run(race, P.HowFar(past=None, raceday=True), trail_ahead=True, first_wp=1)
    return Path(path).name, window, "profile only", errs(rows)


def table(title, res, keys):
    print(f"\n{title}")
    for cname in CONFIGS:
        if not any(c == cname for _, _, c in res):
            continue
        print(f"  {cname}")
        for w in WINDOWS:
            per = [res[(k, w, cname)] for k in keys if (k, w, cname) in res and res[(k, w, cname)]]
            avg = sum(sum(e) / len(e) for e in per) / len(per)
            w5 = sum(sum(x <= 5 for x in e) / len(e) for e in per) / len(per)
            w15 = sum(sum(x <= 15 for x in e) / len(e) for e in per) / len(per)
            extra = "  " + " ".join(f"{k} {sum(res[(k, w, cname)]) / len(res[(k, w, cname)]):.1f}" for k in keys) if len(keys) <= 6 else ""
            print(f"    window {w:5.0f} m: {avg:5.2f} min, {w5 * 100:3.0f}% within 5, {w15 * 100:3.0f}% within 15{extra}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--activities")
    args = ap.parse_args()
    with ProcessPoolExecutor(8) as ex:
        todo = [(k, w, c) for k in B.RACES for w in WINDOWS for c in CONFIGS]
        res = {(k, w, c): e for k, w, c, e in ex.map(race_job, todo)}
        table("five races", res, list(B.RACES))
        if args.activities:
            files = [str(f) for f in sorted(Path(args.activities).glob("*.gpx"))
                     if (lambda p: len(p) >= 100 and p[-1].dist >= 25000)(BA.load(f))]
            res = {(k, w, c): e for k, w, c, e in ex.map(activity_job, [(f, w) for f in files for w in WINDOWS], chunksize=4)}
            table(f"{len(files)} activities of 25 km or more", res, [Path(f).name for f in files])
    return 0


if __name__ == "__main__":
    sys.exit(main())

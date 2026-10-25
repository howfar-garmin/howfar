#!/usr/bin/env python3
"""Score the field's ETA algorithm, with each part switched on or off, on recorded runs
against their real courses.

    python tools/research/benchmark.py --out results.json

Each race is predicted with all the other races as "past races", so nothing is tested on the
data it learned from. Edit RACES to add runs.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import predictors as P  # noqa: E402
import scenario as S  # noqa: E402
from wpeta.readers import read_track  # noqa: E402
from wpeta.field import shown_seconds  # noqa: E402

ROOT = HERE.parents[1]
# key: (name, recorded run in samples/, course file in courses/)
# key: (name, recorded run in samples/, course file in courses/ or None for a run whose
# course has no checkpoints (they go where the runner stopped), score only the legs where
# the run follows the course: for a course file of another edition of the race)
RACES = {
    "TOR": ("Tor des Géants 2023", ROOT / "samples/TOR330_2023.gpx", ROOT / "courses/TOR330-CERT-2026.gpx", True),
    "AW": ("Abbots Way 2018", ROOT / "samples/Abbots_Way_2018.gpx", None, False),
    "X100": ("TORX100 2025", ROOT / "samples/TORX100_2025.gpx", ROOT / "courses/TOR100-CERT-20260910.gpx", False),
    "S1": ("TORX 2026 section 1", ROOT / "samples/TORX26_Sezione_1.gpx", ROOT / "courses/TOR330-CERT-2026-T1.gpx", False),
    "AN": ("La Via di Annibale skyrace", ROOT / "samples/La_via_di_Annibale_Skyrace.gpx", ROOT / "courses/La via di annibale - 42 km - 2024.gpx", False),
    "STL": ("STL25", ROOT / "samples/STL25.gpx", ROOT / "courses/STL25 def 2026 2.gpx", False),
}
# each race learns its "past races" from all the others, so nothing is tested on what it learned from
PAST = {k: [o for o in RACES if o != k] for k in RACES}

_cache: dict = {}


def race(key):
    if key not in _cache:
        name, act, course, matching = RACES[key]
        if course is None:
            pts = [p for p in read_track(act) if p.t is not None and p.alt is not None]
            _cache[key] = S.race_from_stops(name, pts)[0]
        else:
            _cache[key] = S.load_race(name, str(act), str(course))
        if matching:
            _cache[key].skip = S.unmatched_legs(_cache[key])
    return _cache[key]


def past_layer(key):
    """Speed-by-grade from all the other races."""
    obs = []
    for k in PAST[key]:
        obs += P.past_observations(race(k).points)
    return P.layer_from_obs(obs)


def make(opts, key):
    if opts.get("average"):
        return P.AveragePace()
    return P.HowFar(past=past_layer(key) if opts["past"] else None, raceday=opts["raceday"])


AVERAGE = dict(average=True, past=False, ahead=False, raceday=False)


def label(o):
    if o.get("average"):
        return "average pace so far"
    parts = [n for n, f in (("past", o["past"]), ("ahead", o["ahead"]), ("raceday", o["raceday"])) if f]
    return "HowFar[" + ("+".join(parts) or "current race only") + "]"


def specs():
    return [dict(past=p, ahead=a, raceday=r) for p, a, r in itertools.product((False, True), repeat=3)] + [AVERAGE]


def job(args):
    opts, key, shown = args
    rows = S.run(race(key), make(opts, key), trail_ahead=opts["ahead"])
    if shown:  # score what the runner sees: the time rounded as on the watch
        rows = [(t, k, dn, shown_seconds(eta), act, am) for t, k, dn, eta, act, am in rows]
    return label(opts), key, S.score(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(HERE / "results.json"))
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--shown", action="store_true", help="score the times rounded as the watch shows them (for the site)")
    args = ap.parse_args()

    todo = [(s, k, args.shown) for s in specs() for k in RACES]
    results = {}
    with ProcessPoolExecutor(args.jobs) as ex:
        for lab, key, sc in ex.map(job, todo):
            results.setdefault(lab, {})[key] = dict(score=sc)
            print(f"{lab:<48} {key:<4} 1h: {sc['mae_hour']:5.1f} min  2km: {sc['mae_2000']:5.1f}  1km: {sc['mae_1000']:5.1f}", flush=True)
    json.dump(results, open(args.out, "w"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

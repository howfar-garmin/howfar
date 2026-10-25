#!/usr/bin/env python3
"""Score the field's algorithm on a folder of recorded activities that have no course files.

    python tools/research/benchmark_activities.py /path/to/activities --out activities.json

Each activity is its own course, with virtual waypoints every 10 km (activities up to 50 km)
or 20 km (longer), and the finish. Its "past races" are the qualifying activities recorded
before it, as the watch would have learned them. Only activities of at least --min-km with
times and elevation are used.

Because the course is the activity itself, the trail ahead is known perfectly and the course
distance matches the watch's, so this measures the pace model, not course-file problems.
"""

from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import predictors as P  # noqa: E402
import replay as R  # noqa: E402
import scenario as S  # noqa: E402
from wpeta import model as M  # noqa: E402
from wpeta.model import Layer  # noqa: E402
from wpeta.profile import Elevation  # noqa: E402
from wpeta.readers import read_track  # noqa: E402


def spacing(total_m: float) -> float:
    return 10000.0 if total_m <= 50000 else 20000.0


def start_time(path: Path) -> str:
    head = path.read_text(errors="ignore")[:200000]
    m = re.search(r"<trkpt[^>]*>.*?<time>([^<]+)</time>", head, re.S)
    return m.group(1) if m else ""


def load(path: Path):
    pts = [p for p in read_track(path) if p.t is not None and p.alt is not None]
    return pts


def as_race(name: str, pts) -> S.Race:
    total = pts[-1].dist
    every = spacing(total)
    wps = [R.Waypoint("Start", pts[0].dist, pts[0].dist)]
    d = every
    while d < total - 1000:
        wps.append(R.Waypoint(f"km {d / 1000:.0f}", d, d))
        d += every
    wps.append(R.Waypoint("Finish", total, total))
    race = S.Race(name, pts, wps, Elevation(pts), R.stop_time_index(pts))
    k = 0
    for i, p in enumerate(pts):
        while k < len(wps) and p.dist >= wps[k].act_dist:
            race.arrival[k] = (p.t, race.stops[i])
            k += 1
    return race


def specs():
    return [dict(past=p, ahead=a, raceday=r) for p, a, r in itertools.product((False, True), repeat=3)]


def label(o):
    parts = [n for n, f in (("past", o["past"]), ("ahead", o["ahead"]), ("raceday", o["raceday"])) if f]
    return "+".join(parts) or "current race only"


def job(args):
    path, past_layer, opts_list = args
    pts = load(Path(path))
    race = as_race(Path(path).name, pts)
    out = {}
    for o in opts_list:
        past = Layer() if o["past"] else None
        if past is not None and past_layer is not None:
            past.paces, past.weights = list(past_layer[0]), list(past_layer[1])
        if past is not None and past.total_weight() == 0:
            past = None  # the first activities have nothing before them
        rows = S.run(race, P.HowFar(past=past, raceday=o["raceday"]), trail_ahead=o["ahead"], first_wp=1)
        out[label(o)] = S.score(rows) if rows else None
    return Path(path).name, pts[-1].dist / 1000, pts[-1].t / 3600, out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--min-km", type=float, default=25)
    ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", type=int, default=8)
    args = ap.parse_args()

    files = sorted(Path(args.folder).glob("*.gpx"))
    print(f"reading {len(files)} activities…", flush=True)
    acts = []
    for f in files:
        pts = load(f)
        if len(pts) < 100 or pts[-1].dist < args.min_km * 1000:
            continue
        layer = P.layer_from_obs(P.past_observations(pts))
        acts.append((start_time(f), f, layer))
    acts.sort(key=lambda a: a[0])
    print(f"{len(acts)} activities of at least {args.min_km:.0f} km", flush=True)

    # past races of each activity: everything recorded before it, merged the way the watch's
    # stored model does (older runs fade by STORED_DECAY at each new one, capped at STORED_CAP)
    todo = []
    running = Layer()
    for when, f, layer in acts:
        todo.append((str(f), (list(running.paces), list(running.weights)) if running.total_weight() else None, specs()))
        running.merge_from(layer, M.STORED_DECAY, M.STORED_CAP)

    results = {}
    with ProcessPoolExecutor(args.jobs) as ex:
        for n, (name, km, hours, scores) in enumerate(ex.map(job, todo, chunksize=2), 1):
            results[name] = dict(km=round(km, 1), hours=round(hours, 2), scores=scores)
            if n % 10 == 0:
                print(f"{n}/{len(todo)}", flush=True)
    json.dump(results, open(args.out, "w"))
    summarize(results)
    return 0


def summarize(results) -> None:
    groups = {"all": lambda r: True, "25-50 km": lambda r: r["km"] <= 50, "over 50 km": lambda r: r["km"] > 50}
    labels = [label(o) for o in specs()]
    for gname, keep in groups.items():
        rs = [r for r in results.values() if keep(r) and all(r["scores"].get(l) for l in labels)]
        print(f"\n{gname}: {len(rs)} activities")
        print(f"{'configuration':<28} {'1h MAE':>7} {'within 5':>9} {'2 km out':>9} {'bias':>6}")
        for l in sorted(labels, key=lambda l: sum(r["scores"][l]["mae_hour"] for r in rs) / len(rs)):
            m = lambda k: sum(r["scores"][l][k] for r in rs) / len(rs)
            m2 = [r["scores"][l]["mae_2000"] for r in rs if r["scores"][l]["mae_2000"] == r["scores"][l]["mae_2000"]]
            print(f"{l:<28} {m('mae_hour'):6.2f}m {m('within5_hour') * 100:8.0f}% {sum(m2) / len(m2):8.2f}m {m('bias_hour'):+6.2f}")


if __name__ == "__main__":
    sys.exit(main())

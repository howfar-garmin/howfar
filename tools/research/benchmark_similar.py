#!/usr/bin/env python3
"""Does it help to train the pace on a few similar, recent runs instead of the whole history?

    python tools/research/benchmark_similar.py /path/to/activities --out similar.json

Same setup as benchmark_activities.py (each activity is its own course, virtual waypoints
every 10 or 20 km, the trail ahead known), with the "past races" chosen four ways, all of
them on other courses (a run on the same trail would make it too easy):

- none:    no past races, only today's run
- all:     every earlier activity on a different course, faded the way the watch's stored
           model fades them
- recent:  the --count most recent earlier activities on a different course, any distance
- similar: the --count most recent earlier activities on a different course, with a distance
           within --tolerance of this one's and recorded at most --days before it

"recent" and "similar" are merged the way the race prep page merges the files you pick.
A different course means less than --overlap of the other activity's track lies within
150 m of this one's. Only activities that have at least one similar run are scored, so all
four are compared on the same activities. "same" is the whole history including runs on the
same course, for reference.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import predictors as P  # noqa: E402
import scenario as S  # noqa: E402
from benchmark_activities import as_race, load, start_time  # noqa: E402
from wpeta import model as M  # noqa: E402
from wpeta.model import Layer  # noqa: E402

CELL = 150.0  # metres; tracks closer than this count as the same trail
SOURCES = ("none", "all", "recent", "similar", "same")


def cells(pts) -> set[tuple[int, int]]:
    """Grid cells the track passes through (about CELL metres square)."""
    out = set()
    for p in pts:
        if p.lat is None:
            continue
        y = p.lat * 111320 / CELL
        x = p.lon * 111320 * math.cos(math.radians(p.lat)) / CELL
        out.add((int(y), int(x)))
    return out


def overlap(a: set, b: set) -> float:
    """Share of track a lying on or next to track b."""
    if not a:
        return 0.0
    near = sum(1 for (y, x) in a if any((y + dy, x + dx) in b for dy in (-1, 0, 1) for dx in (-1, 0, 1)))
    return near / len(a)


def merged(layers, decay=1.0, cap=float("inf")) -> Layer | None:
    out = Layer()
    for layer in layers:
        out.merge_from(layer, decay, cap)
    return out if out.total_weight() else None


def job(args):
    path, pasts = args
    race = as_race(Path(path).name, load(Path(path)))
    out = {}
    for src, layer in pasts.items():
        for raceday in (False, True):
            past = None
            if layer is not None:
                past = Layer()
                past.paces, past.weights = list(layer[0]), list(layer[1])
            rows = S.run(race, P.HowFar(past=past, raceday=raceday), trail_ahead=True, first_wp=1)
            out[src + ("+raceday" if raceday else "")] = S.score(rows) if rows else None
    return Path(path).name, out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--min-km", type=float, default=25)
    ap.add_argument("--count", type=int, default=5, help="past runs to train on")
    ap.add_argument("--tolerance", type=float, default=0.3, help="distance within ±this share")
    ap.add_argument("--days", type=float, default=365)
    ap.add_argument("--overlap", type=float, default=0.3)
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
        when = datetime.fromisoformat(start_time(f).replace("Z", "+00:00"))
        acts.append(dict(when=when, path=f, km=pts[-1].dist / 1000, cells=cells(pts),
                         layer=P.layer_from_obs(P.past_observations(pts))))
    acts.sort(key=lambda a: a["when"])
    print(f"{len(acts)} activities of at least {args.min_km:.0f} km", flush=True)

    todo, picks = [], {}
    running = Layer()
    for i, a in enumerate(acts):
        earlier = [b for b in reversed(acts[:i]) if (a["when"] - b["when"]).total_seconds() > 12 * 3600]
        other = [b for b in earlier if overlap(b["cells"], a["cells"]) < args.overlap]
        recent = other[: args.count]
        same = len(earlier) - len(other)
        history = merged((b["layer"] for b in reversed(other)), M.STORED_DECAY, M.STORED_CAP)
        similar = [b for b in other
                   if abs(b["km"] - a["km"]) <= args.tolerance * a["km"]
                   and (a["when"] - b["when"]).days <= args.days][: args.count]
        snapshot = (list(running.paces), list(running.weights)) if running.total_weight() else None
        running.merge_from(a["layer"], M.STORED_DECAY, M.STORED_CAP)
        if not similar:
            continue
        as_tuple = lambda layer: (list(layer.paces), list(layer.weights)) if layer else None
        pasts = dict(none=None, all=as_tuple(history), same=snapshot,
                     recent=as_tuple(merged(b["layer"] for b in recent)),
                     similar=as_tuple(merged(b["layer"] for b in similar)))
        todo.append((str(a["path"]), pasts))
        picks[a["path"].name] = dict(
            km=round(a["km"], 1), when=a["when"].date().isoformat(), earlier=len(earlier), same_course=same,
            similar=[(b["path"].name, round(b["km"], 1), (a["when"] - b["when"]).days) for b in similar])
    print(f"{len(todo)} have at least one similar earlier run on another course", flush=True)

    results = {}
    with ProcessPoolExecutor(args.jobs) as ex:
        for n, (name, scores) in enumerate(ex.map(job, todo, chunksize=2), 1):
            results[name] = dict(picks[name], scores=scores)
            if n % 10 == 0:
                print(f"{n}/{len(todo)}", flush=True)
    json.dump(results, open(args.out, "w"))
    summarize(results)
    return 0


def summarize(results) -> None:
    labels = [s + r for s in SOURCES for r in ("", "+raceday")]
    groups = {"all": lambda r: True, "25-50 km": lambda r: r["km"] <= 50, "over 50 km": lambda r: r["km"] > 50}
    for gname, keep in groups.items():
        rs = [r for r in results.values() if keep(r) and all(r["scores"].get(l) for l in labels)]
        if not rs:
            continue
        n_sim = sum(len(r["similar"]) for r in rs) / len(rs)
        age = sum(d for r in rs for _, _, d in r["similar"]) / sum(len(r["similar"]) for r in rs)
        same = sum(r["same_course"] for r in rs) / len(rs)
        print(f"\n{gname}: {len(rs)} activities, {n_sim:.1f} similar runs each, {age:.0f} days old on average,"
              f" {same:.1f} earlier runs on the same course left out")
        print(f"{'past races (+ trail ahead)':<28} {'1h MAE':>7} {'within 5':>9} {'2 km out':>9} {'bias':>6}")
        for l in sorted(labels, key=lambda l: sum(r["scores"][l]["mae_hour"] for r in rs) / len(rs)):
            m = lambda k: sum(r["scores"][l][k] for r in rs) / len(rs)
            m2 = [r["scores"][l]["mae_2000"] for r in rs if r["scores"][l]["mae_2000"] == r["scores"][l]["mae_2000"]]
            print(f"{l:<28} {m('mae_hour'):6.2f}m {m('within5_hour') * 100:8.0f}% {sum(m2) / len(m2):8.2f}m {m('bias_hour'):+6.2f}")
        best = lambda r: min(("all+raceday", "similar+raceday"), key=lambda l: r["scores"][l]["mae_hour"])
        wins = sum(best(r) == "similar+raceday" for r in rs)
        print(f"similar+raceday beats all+raceday on {wins} of {len(rs)}")


if __name__ == "__main__":
    sys.exit(main())

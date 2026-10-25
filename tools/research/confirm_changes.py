#!/usr/bin/env python3
"""Do the two small gains of the race tests hold on every run? And what would going without any
past (no pasted pace, nothing remembered from earlier runs) cost?

    python tools/research/confirm_changes.py FOLDER

Versions (all with the trail ahead known and race-day corrections):
- now:            today's field
- shaped:         missing slopes follow Tobler's curve from both neighbours (test_shape.py)
- fading:         the past counts at most 10 per slope bin, halving every 10 km of today's
                  running, with a faster form factor (tune_prior.py)
- shaped+fading
- no past, shaped: nothing from earlier runs at all

Runs: the five races of benchmark.py (past: similar earlier activities, as pasted), the
activities of at least 25 km with virtual checkpoints and the activities of at least 50 km
with checkpoints where the runner stopped (past: everything before them, as the watch
remembers it).
"""

from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import benchmark as B  # noqa: E402
import benchmark_activities as BA  # noqa: E402
import benchmark_similar_pace as SP  # noqa: E402
import benchmark_trend as BT  # noqa: E402
import predictors as P  # noqa: E402
import scenario as S  # noqa: E402
import test_shape as TS  # noqa: E402
import tune_prior as TP  # noqa: E402
from wpeta import model as M  # noqa: E402
from wpeta.field import shown_seconds  # noqa: E402

TOBLER = [M.tobler_factor(M.bin_center(i)) for i in range(M.NUM_BINS)]
VERSIONS = ["now", "shaped", "fading", "shaped+fading", "no past, shaped"]


def predictor(version, past):
    M.SpeedGradeModel.build_curve = TS.shaped_build_curve(TOBLER) if "shaped" in version else TS.ORIGINAL
    M.PRIOR_CAP = 20.0
    M.EtaEstimator.ALPHA = 0.03
    if version == "no past, shaped":
        return P.HowFar(past=None, raceday=True)
    if "fading" in version:
        M.EtaEstimator.ALPHA = 0.06
        return TP.Fading(10.0, 10.0, past=past, raceday=True)
    return P.HowFar(past=past, raceday=True)


def score(race, version, past, first_wp=None):
    rows = S.run(race, predictor(version, past), trail_ahead=True, first_wp=first_wp)
    e = [abs(shown_seconds(eta) - am) / 60 for t, k, dn, eta, act, am in rows if am <= 3600]
    return (sum(e) / len(e), sum(x <= 5 for x in e) / len(e), sum(x <= 15 for x in e) / len(e)) if e else None


def race_job(args):
    key, layer = args
    return "races", key, {v: score(B.race(key), v, layer) for v in VERSIONS}


def activity_job(args):
    group, path, past, stops = args
    pts = BA.load(Path(path))
    race = S.race_from_stops(Path(path).name, pts)[0] if stops else BA.as_race(Path(path).name, pts)
    return group, Path(path).name, {v: score(race, v, BT.layer_of(past), first_wp=1) for v in VERSIONS}


def main() -> int:
    folder = Path(sys.argv[1])
    acts = []
    for f in sorted(folder.glob("*.gpx")):
        pts = BA.load(f)
        if len(pts) < 100 or pts[-1].dist < 10000:
            continue
        acts.append((SP.started(f), pts[-1].dist / 1000, f.name, P.layer_from_obs(P.past_observations(pts))))
    acts.sort(key=lambda a: a[0])
    todo = []
    for key in B.RACES:
        layer = SP.similar_pace(key, acts)[0]
        todo.append(("race", (key, layer if layer.total_weight() else None)))
    for p, past in BT.history(folder, 25):
        todo.append(("act", ("activities of 25 km or more", p, past, False)))
    for p, past in BT.history(folder, 50):
        todo.append(("act", ("activities of 50 km or more, checkpoints at stops", p, past, True)))
    res: dict = {}
    with ProcessPoolExecutor(8) as ex:
        futs = [ex.submit(race_job if kind == "race" else activity_job, a) for kind, a in todo]
        for f in futs:
            group, name, scores = f.result()
            res.setdefault(group, {})[name] = scores
    for group, runs in res.items():
        rs = [r for r in runs.values() if all(r[v] for v in VERSIONS)]
        print(f"\n{group}: {len(rs)}")
        for v in VERSIONS:
            m = lambda i: sum(r[v][i] for r in rs) / len(rs)
            extra = "   " + " ".join(f"{k} {runs[k][v][0]:.1f}" for k in runs) if group == "races" else ""
            print(f"  {v:<18} {m(0):5.2f} min, {m(1) * 100:3.0f}% within 5, {m(2) * 100:3.0f}% within 15{extra}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

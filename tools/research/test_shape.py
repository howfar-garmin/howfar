#!/usr/bin/env python3
"""For slopes not yet run today, how should the field guess the pace?

    python tools/research/test_shape.py FOLDER

Today's running gives the pace on the slopes already met. For the others the field uses a
fixed curve of how speed changes with slope (Tobler's hiking function), anchored to today's
nearest slopes. Here that curve can instead be the runner's own: the typical speed on each
slope relative to the flat, the median over their activities recorded before the race (from
FOLDER). Variants, all without a pasted pace and with the course profile:

- tobler:         today's field (missing slopes between two known ones: straight line in pace)
- tobler, shaped: missing slopes between two known ones also follow the curve's shape
- learned:        the runner's own curve, shaped the same way
"""

from __future__ import annotations

import statistics
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import benchmark as B  # noqa: E402
import benchmark_activities as BA  # noqa: E402
import benchmark_similar_pace as SP  # noqa: E402
import predictors as P  # noqa: E402
import scenario as S  # noqa: E402
from wpeta import model as M  # noqa: E402
from wpeta.field import shown_seconds  # noqa: E402

BUCKETS = [(0, 0.5), (0.5, 1), (1, 2), (2, 4), (4, 999)]
FLAT = (19, 20, 21)  # bins -2, 0, +2 %


def learned_factors(layers) -> list[float]:
    """Speed on each slope relative to the flat: the median over the given activities."""
    ratios: list[list[float]] = [[] for _ in range(M.NUM_BINS)]
    for lay in layers:
        w = sum(lay.weights[i] for i in FLAT)
        if w < 20:
            continue
        flat = sum(lay.speed(i) * lay.weights[i] for i in FLAT) / w
        for i in range(M.NUM_BINS):
            if lay.weights[i] >= 5:
                ratios[i].append(lay.speed(i) / flat)
    out = []
    for i in range(M.NUM_BINS):
        out.append(statistics.median(ratios[i]) if len(ratios[i]) >= 5 else M.tobler_factor(M.bin_center(i)))
    return out


def shaped_build_curve(factor):
    """build_curve whose missing slopes follow `factor` (speed vs flat) from the nearest known
    slopes on both sides, weighted by closeness."""

    def build_curve(self, use_run, form):
        values = [0.0] * M.NUM_BINS
        valid = [False] * M.NUM_BINS
        for i in range(M.NUM_BINS):
            wr = self.run.weights[i] if use_run else 0.0
            ws, wi = self.stored.weights[i], self.imported.weights[i]
            pw = ws + wi
            pp = (self.stored.paces[i] * ws + self.imported.paces[i] * wi) / pw if pw > 0 else 0.0
            pw_eff = min(pw, M.PRIOR_CAP)
            tot = wr + pw_eff
            if tot >= M.MIN_WEIGHT:
                values[i] = (self.run.paces[i] * wr + pp / form * pw_eff) / tot
                valid[i] = True
        known = [i for i in range(M.NUM_BINS) if valid[i]]
        for i in range(M.NUM_BINS):
            if valid[i]:
                continue
            lo = max((j for j in known if j < i), default=None)
            hi = min((j for j in known if j > i), default=None)
            guesses = []
            for j in (lo, hi):
                if j is not None:  # pace scales as 1 / speed factor
                    guesses.append((values[j] * factor[j] / factor[i], 1.0 / abs(i - j)))
            if guesses:
                values[i] = sum(v * w for v, w in guesses) / sum(w for _, w in guesses)
            else:
                values[i] = 1.0 / (M.DEFAULT_FLAT_SPEED * form * factor[i])
        return values

    return build_curve


ORIGINAL = M.SpeedGradeModel.build_curve


def job(args):
    key, name, factor, past = args
    M.SpeedGradeModel.build_curve = ORIGINAL if factor is None else shaped_build_curve(factor)
    race = B.race(key)
    t0 = race.points[0].t
    rows = S.run(race, P.HowFar(past=past, raceday=True), trail_ahead=True)
    return key, name, [((t - t0) / 3600, abs(shown_seconds(eta) - am) / 60) for t, k, dn, eta, act, am in rows if am <= 3600]


def main() -> int:
    folder = Path(sys.argv[1])
    acts = []
    for f in sorted(folder.glob("*.gpx")):
        pts = BA.load(f)
        if len(pts) < 100 or pts[-1].dist < 10000:
            continue
        acts.append((SP.started(f), pts[-1].dist / 1000, f.name, P.layer_from_obs(P.past_observations(pts))))
    acts.sort(key=lambda a: a[0])
    tobler = [M.tobler_factor(M.bin_center(i)) for i in range(M.NUM_BINS)]
    todo = []
    for key in B.RACES:
        when = SP.started(Path(B.RACES[key][1]))
        before = [a[3] for a in acts if (when - a[0]).total_seconds() > 12 * 3600]
        learned = learned_factors(before)
        similar = SP.similar_pace(key, acts)[0]
        similar = similar if similar.total_weight() else None
        print(key, f"{len(before)} earlier activities;", "learned speed vs flat at -30/-10/+10/+30 %:",
              [round(learned[M.bin_index(g)], 2) for g in (-30, -10, 10, 30)],
              "tobler:", [round(tobler[M.bin_index(g)], 2) for g in (-30, -10, 10, 30)])
        todo += [(key, "tobler (now)", None, None), (key, "tobler, shaped", tobler, None), (key, "learned shape", learned, None),
                 (key, "pace pasted (now)", None, similar), (key, "pace pasted + learned shape", learned, similar)]
    with ProcessPoolExecutor(8) as ex:
        res = {}
        for key, name, errs in ex.map(job, todo):
            res.setdefault(name, {})[key] = errs
    print(f"\n{'':<30}{'avg':>6} {'≤5':>5} {'≤15':>5}  " + " ".join(f"{k:>5}" for k in B.RACES) + "  " +
          " ".join(f"{f'{a}-{b}h' if b < 999 else f'>{a}h':>12}" for a, b in BUCKETS))
    for name, r in res.items():
        per = {k: sum(e for _, e in r[k]) / len(r[k]) for k in r}
        w5 = sum(sum(e <= 5 for _, e in r[k]) / len(r[k]) for k in r) / len(r)
        w15 = sum(sum(e <= 15 for _, e in r[k]) / len(r[k]) for k in r) / len(r)
        line = f"{name:<30}{sum(per.values()) / len(per):6.2f} {w5 * 100:4.0f}% {w15 * 100:4.0f}%  " + " ".join(f"{per[k]:5.1f}" for k in B.RACES) + "  "
        for a, b in BUCKETS:
            es = [e for k in r for h, e in r[k] if a <= h < b]
            line += f"{sum(es) / len(es):5.1f} ({sum(e <= 5 for e in es) / len(es) * 100:3.0f}%)"
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())

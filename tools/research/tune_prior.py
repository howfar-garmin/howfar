#!/usr/bin/env python3
"""Can the pasted pace help more reliably? Replays the five races of benchmark.py with full race
prep, the pace made from similar earlier activities (benchmark_similar_pace.py), under
variants of how much the past pace counts against today's running:

- PRIOR_CAP: the most weight the past gets in a slope bin (today's samples each weigh 1)
- ALPHA: how fast the form factor (today vs. the past) follows today
- FORM_RANGE_PRIOR: how far today's form may differ from the past

    python tools/research/tune_prior.py FOLDER
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
import predictors as P  # noqa: E402
import scenario as S  # noqa: E402
from wpeta import model as M  # noqa: E402
from wpeta.field import shown_seconds  # noqa: E402

VARIANTS = {
    "now (cap 20, α 0.03, 0.6–1.6)": dict(),
    "cap 10": dict(cap=10.0),
    "cap 5": dict(cap=5.0),
    "cap 2": dict(cap=2.0),
    "α 0.06": dict(alpha=0.06),
    "α 0.1": dict(alpha=0.1),
    "range 0.4–2.5": dict(lo=0.4, hi=2.5),
    "cap 5, α 0.06": dict(cap=5.0, alpha=0.06),
    "cap 5, α 0.06, 0.4–2.5": dict(cap=5.0, alpha=0.06, lo=0.4, hi=2.5),
    # the past fades as today's kilometres pile up: cap * 0.5 ** (km / half)
    "cap 20 fading, half 5 km": dict(cap=20.0, half=5.0),
    "cap 20 fading, half 10 km": dict(cap=20.0, half=10.0),
    "cap 20 fading, half 20 km": dict(cap=20.0, half=20.0),
    "cap 10 fading, half 10 km, α 0.06": dict(cap=10.0, half=10.0, alpha=0.06),
}


class Fading(P.HowFar):
    """The past's cap in each slope bin halves every `half` km of today's running."""

    def __init__(self, cap: float, half: float | None, **kw) -> None:
        super().__init__(**kw)
        self.cap, self.half = cap, half

    def observe(self, t, dist, alt):
        if self.half:
            M.PRIOR_CAP = max(0.5, self.cap * 0.5 ** (dist / 1000 / self.half))
            self.model.invalidate()
        super().observe(t, dist, alt)
BUCKETS = [(0, 1), (1, 4), (4, 999)]


def job(args):
    key, layer, name, v = args
    M.PRIOR_CAP = v.get("cap", 20.0)
    M.EtaEstimator.ALPHA = v.get("alpha", 0.03)
    M.EtaEstimator.FORM_RANGE_PRIOR = (v.get("lo", 0.6), v.get("hi", 1.6))
    race = B.race(key)
    t0 = race.points[0].t
    rows = S.run(race, Fading(v.get("cap", 20.0), v.get("half"), past=layer, raceday=True), trail_ahead=True)
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
    layers = {k: SP.similar_pace(k, acts)[0] for k in B.RACES}
    todo = [(k, layers[k] if layers[k].total_weight() else None, n, v) for n, v in VARIANTS.items() for k in B.RACES]
    todo += [(k, None, "profile only", {}) for k in B.RACES]
    with ProcessPoolExecutor(8) as ex:
        res = {}
        for key, name, errs in ex.map(job, todo):
            res.setdefault(name, {})[key] = errs
    print(f"{'':<28}{'avg':>6} {'≤5':>5} {'≤15':>5}  " + " ".join(f"{k:>5}" for k in B.RACES) + "   " +
          " ".join(f"{f'{a}-{b}h' if b < 999 else f'>{a}h':>12}" for a, b in BUCKETS))
    for name in ["profile only"] + list(VARIANTS):
        r = res[name]
        per = {k: sum(e for _, e in r[k]) / len(r[k]) for k in r}
        w5 = sum(sum(e <= 5 for _, e in r[k]) / len(r[k]) for k in r) / len(r)
        w15 = sum(sum(e <= 15 for _, e in r[k]) / len(r[k]) for k in r) / len(r)
        line = f"{name:<28}{sum(per.values()) / len(per):6.2f} {w5 * 100:4.0f}% {w15 * 100:4.0f}%  " + " ".join(f"{per[k]:5.1f}" for k in B.RACES) + "   "
        for a, b in BUCKETS:
            es = [e for k in r for h, e in r[k] if a <= h < b]
            line += f"{sum(es) / len(es):5.1f} ({sum(e <= 5 for e in es) / len(es) * 100:3.0f}%)"
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())

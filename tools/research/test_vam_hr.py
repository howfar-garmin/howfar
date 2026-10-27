#!/usr/bin/env python3
"""Two ideas for steep climbs and effort, replayed on the races and the activity archive.

    python tools/research/test_vam_hr.py ACTIVITIES_FOLDER HR_FOLDER [--out results.json]

HR_FOLDER has <activity>.json: the heart rate of each track point of <activity>.gpx (the
archive keeps it as .hr.npy; the races' GPX files carry it themselves).

1. D+/h on steep climbs. Above G% the speed-by-grade curve is replaced, for bins with too little
   data or for all of them, by a constant vertical speed (metres climbed per hour):
   - fill G:    bins above G% with too little data take the vertical speed of the nearest known
                bin of 8% or more, instead of Tobler's shape
   - pool G:    every bin above G% gets one vertical speed, pooled over all of them
   - hybrid G:  bins above G% with 20 or more observations keep their own pace, the others the pool
2. Heart rate. Every prediction is logged with the heart rate of the last 10 minutes against
   the race so far (as is, and against what that grade usually costs today) and the fatigue
   factor; the analysis asks whether the prediction's error follows them, and what a correction
   fitted on one set of runs does on the other.

Scores: average error of every prediction made while the point was at most an hour away, stops
left out (as benchmark.py); "steep" counts only the predictions whose stretch ahead is at least
half above 15%.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import benchmark as B  # noqa: E402
import benchmark_activities as BA  # noqa: E402
import benchmark_trend as BT  # noqa: E402
import predictors as P  # noqa: E402
import scenario as S  # noqa: E402
from wpeta import model as M  # noqa: E402

STEEP = 15.0  # % for the "steep" score
VARIANT_SETS = {
    "first": ["now"] + [f"{m} {g}" for m in ("fill", "pool", "hybrid") for g in (12, 15, 18, 22)],
    # lower thresholds, how much data a bin needs to keep its own pace, steep descents
    "followup": ["now", "pool 12", "hybrid 12", "hybrid 8", "pool 10", "hybrid 10",
                 "hybrid 12 m5", "hybrid 12 m10", "hybrid 12 m40", "hybrid 12 m80",
                 "hybrid 12 d12", "hybrid 12 d18", "hybrid 12 d25", "pool 12 d18"],
}
VARIANTS = VARIANT_SETS["first"]
HYBRID_MIN = 20.0
HR_WINDOW = 600.0  # s


class VamModel(M.SpeedGradeModel):
    """mode G [mN] [dD]: D+/h above G% (mode fill, pool or hybrid); a hybrid bin keeps its own pace
    with N or more observations (default HYBRID_MIN); dD also pools the descents below -D% (D- per
    hour), the same way as the climbs."""

    def __init__(self, spec: str) -> None:
        super().__init__()
        words = spec.split()
        self.mode, self.g = words[0], float(words[1])
        self.min = HYBRID_MIN
        self.down = None
        for w in words[2:]:
            if w[0] == "m":
                self.min = float(w[1:])
            elif w[0] == "d":
                self.down = float(w[1:])

    def build_curve(self, use_run, form):
        values = super().build_curve(use_run, form)
        tot = []
        for i in range(M.NUM_BINS):
            wr = self.run.weights[i] if use_run else 0.0
            pw = self.stored.weights[i]
            tot.append(wr + (min(pw, self.prior_cap) if use_run else pw))
        c = [M.bin_center(i) for i in range(M.NUM_BINS)]
        valid = [t >= M.MIN_WEIGHT for t in tot]
        self._side(values, tot, c, valid, [i for i in range(M.NUM_BINS) if c[i] >= self.g])
        if self.down is not None:
            self._side(values, tot, c, valid, [i for i in range(M.NUM_BINS) if c[i] <= -self.down])
        return values

    def _side(self, values, tot, c, valid, steep):
        # vertical pace (s per metre climbed or descended) pooled over the steep bins with data
        known = [i for i in steep if valid[i]]
        pool = None
        if known:
            w = sum(tot[i] for i in known)
            pool = sum(values[i] * 100.0 / abs(c[i]) * tot[i] for i in known) / w
        for i in steep:
            if self.mode == "fill":
                if valid[i]:
                    continue
                total = weight = 0.0
                for j in _nearest(valid, c, i):
                    wj = 1.0 / abs(i - j)
                    total += values[j] * c[i] / c[j] * wj  # same metres climbed per second
                    weight += wj
                if weight:
                    values[i] = total / weight
            elif pool is not None:
                if self.mode == "hybrid" and tot[i] >= self.min:
                    continue
                values[i] = pool * abs(c[i]) / 100.0
            elif c[i] > 0:  # nothing steep yet: as "fill"
                srcs = _nearest(valid, c, i)
                if srcs:
                    j = srcs[0]
                    values[i] = values[j] * c[i] / c[j]


def _nearest(valid, c, i):
    """The nearest known bins of 8% or more on each side of i."""
    out = []
    lo = i - 1
    while lo >= 0 and not valid[lo]:
        lo -= 1
    if lo >= 0 and c[lo] >= 8.0:
        out.append(lo)
    hi = i + 1
    while hi < M.NUM_BINS and not valid[hi]:
        hi += 1
    if hi < M.NUM_BINS:
        out.append(hi)
    return out


class Logged(P.HowFar):
    """The field, optionally with a D+/h model, logging heart rate and steepness at each prediction."""

    def __init__(self, past, variant: str, hr: list) -> None:
        super().__init__(past=past, raceday=True)
        if variant != "now":
            stored = self.model.stored
            self.model = VamModel(variant)
            self.model.stored = stored
            self.est = M.EtaEstimator(self.model)
        self.hr = hr
        self._i = -1
        self.log = {}
        self._hist = []  # (t, hr) moving samples
        self._seg = []  # heart rate since the last observation
        self._obs = []  # (t, grade, mean hr) per observation
        self._bins = {}  # grade bin (5%) -> [sum hr, n]

    def observe(self, t, dist, alt):
        self._i += 1
        h = self.hr[self._i] if self._i < len(self.hr) else None
        moving_before = self.tracker.observations
        super().observe(t, dist, alt)
        if h:
            self._hist.append((t, h))
            self._seg.append(h)
        if self.tracker.observations > moving_before and self._seg:
            m = sum(self._seg) / len(self._seg)
            g = self.tracker.last_grade
            self._obs.append((t, g, m))
            b = self._bins.setdefault(round(g / 5.0), [0.0, 0])
            b[0] += m
            b[1] += 1
            self._seg = []

    def predict(self, ctx):
        eta = super().predict(ctx)
        steep = sum(l for l, g in ctx.chunks if g >= STEEP) / max(1.0, sum(l for l, _ in ctx.chunks))
        down = sum(l for l, g in ctx.chunks if g <= -STEEP) / max(1.0, sum(l for l, _ in ctx.chunks))
        rec = dict(steep=steep, down=down, fatigue=self.est.fatigue, form=self.model.form)
        recent = [h for t, h in self._hist if t >= ctx.t - HR_WINDOW]
        race = [h for t, h in self._hist if t >= 600.0]
        if len(recent) > 60 and len(race) > 600:
            rec["hr_rel"] = (sum(recent) / len(recent)) / (sum(race) / len(race))
            dev = []
            for t, g, m in self._obs:
                if t >= ctx.t - HR_WINDOW:
                    b = self._bins.get(round(g / 5.0))
                    if b and b[1] >= 20:
                        dev.append(m / (b[0] / b[1]))
            if len(dev) >= 5:
                rec["hr_dev"] = sum(dev) / len(dev)
        self.log[(ctx.t, ctx.wp_index)] = rec
        return eta


def rows_of(race, variant, past, hr, first_wp=None):
    pred = Logged(past, variant, hr)
    rows = S.run(race, pred, trail_ahead=True, first_wp=first_wp)
    out = []
    for t, k, dn, eta, act, am in rows:
        if am > 3600 or am < 60:
            continue
        rec = pred.log.get((t, k), {})
        out.append([t, k, eta, am, rec.get("steep", 0.0), rec.get("fatigue"), rec.get("form"),
                    rec.get("hr_rel"), rec.get("hr_dev"), rec.get("down", 0.0)])
    return out


# --- heart rate of each track point


def _times(path: Path):
    out = []
    t0 = None
    for m in re.finditer(r"<time>([^<]+)</time>", path.read_text(errors="ignore")):
        dt = datetime.fromisoformat(m.group(1).strip().replace("Z", "+00:00"))
        t0 = t0 or dt
        out.append((dt - t0).total_seconds())
    return out


def hr_of_points(points, gpx: Path, hr_folder: Path | None) -> list:
    """Heart rate per point of the race, by its time (None where there is none)."""
    by_t = {}
    if hr_folder is not None and (hr_folder / (gpx.stem + ".json")).exists():
        hrs = json.loads((hr_folder / (gpx.stem + ".json")).read_text())
        for t, h in zip(_times(gpx), hrs):
            by_t.setdefault(t, h)
    else:
        txt = gpx.read_text(errors="ignore")
        t0 = None
        for pt in re.finditer(r"<trkpt\b.*?</trkpt>", txt, re.S):
            tm = re.search(r"<time>([^<]+)</time>", pt.group(0))
            hm = re.search(r":hr>(\d+)<", pt.group(0))
            if not tm:
                continue
            dt = datetime.fromisoformat(tm.group(1).strip().replace("Z", "+00:00"))
            t0 = t0 or dt
            if hm:
                by_t.setdefault((dt - t0).total_seconds(), int(hm.group(1)))
    return [by_t.get(p.t) for p in points]


def race_job(key, variants):
    race = B.race(key)
    hr = hr_of_points(race.points, Path(B.RACES[key][1]), None)
    past = B.past_layer(key)
    return "races", key, {v: rows_of(race, v, past, hr) for v in variants}


def activity_job(args, variants):
    group, path, past, stops, hr_folder = args
    path = Path(path)
    pts = BA.load(path)
    race = S.race_from_stops(path.name, pts)[0] if stops else BA.as_race(path.name, pts)
    hr = hr_of_points(pts, path, Path(hr_folder))
    return group, path.name, {v: rows_of(race, v, BT.layer_of(past), hr, first_wp=1) for v in variants}


# --- summaries


def mae(rows, steep_only=False, down_only=False):
    e = [abs(r[2] - r[3]) / 60 for r in rows
         if (not steep_only or r[4] >= 0.5) and (not down_only or (len(r) > 9 and r[9] >= 0.5))]
    return (sum(e) / len(e), len(e)) if e else (float("nan"), 0)


def summarize_vam(res):
    variants = list(next(iter(next(iter(res.values())).values())))
    for group, runs in res.items():
        print(f"\n{group}: {len(runs)} runs")
        print(f"  {'variant':<14} {'all':>7} {'steep up':>13} {'steep down':>13}  (minutes, average of runs; up/down: runs with 10+ such predictions)")
        base_all = {k: mae(r['now'])[0] for k, r in runs.items()}
        for v in variants:
            a = [mae(r[v])[0] for r in runs.values() if mae(r[v])[1]]
            st = [mae(r[v], True)[0] for r in runs.values() if mae(r[v], True)[1] >= 10]
            dn = [mae(r[v], down_only=True)[0] for r in runs.values() if mae(r[v], down_only=True)[1] >= 10]
            better = sum(mae(r[v])[0] < base_all[k] - 0.01 for k, r in runs.items() if mae(r[v])[1])
            worse = sum(mae(r[v])[0] > base_all[k] + 0.01 for k, r in runs.items() if mae(r[v])[1])
            extra = "  " + " ".join(f"{k} {mae(r[v])[0]:.2f}" for k, r in runs.items()) if group == "races" else ""
            print(f"  {v:<14} {sum(a) / len(a):6.2f}m {sum(st) / max(1, len(st)):6.2f}m ({len(st):>3})"
                  f" {sum(dn) / max(1, len(dn)):6.2f}m ({len(dn):>3})  better {better:>3} worse {worse:>3}{extra}")


def summarize_hr(res):
    """Does the error follow heart rate? log(actual / predicted) against log(heart rate ratios)."""
    for group, runs in res.items():
        rows = [r for rs in runs.values() for r in rs["now"] if r[7] is not None]
        n_runs = sum(1 for rs in runs.values() if any(r[7] is not None for r in rs["now"]))
        if not rows:
            print(f"\n{group}: no heart rate")
            continue
        print(f"\n{group}: {n_runs} runs with heart rate, {len(rows)} predictions")
        for name, idx in (("hr_rel", 7), ("hr_dev", 8), ("fatigue", 5)):
            pts = [(math.log(r[idx]), math.log(r[3] / r[2])) for r in rows if r[idx]]
            xs, ys = zip(*pts)
            mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
            sxy = sum((x - mx) * (y - my) for x, y in pts)
            sxx = sum((x - mx) ** 2 for x in xs)
            syy = sum((y - my) ** 2 for y in ys)
            print(f"  {name:<8} corr {sxy / math.sqrt(sxx * syy):+.3f}  slope {sxy / sxx:+.2f}  ({len(pts)})")
        # residual by quintile of hr_dev
        pts = sorted((r[8], r[3] / r[2]) for r in rows if r[8])
        q = len(pts) // 5
        if q:
            print("  actual / predicted by heart rate against today's usual for that grade (quintiles):")
            for i in range(5):
                part = pts[i * q:(i + 1) * q]
                print(f"    hr x{part[0][0]:.3f}-{part[-1][0]:.3f}: {sum(p[1] for p in part) / len(part):.3f}")


HR_MODELS = {
    # name: features of log(actual / predicted); every model also has a constant, so "constant"
    # (a plain bias correction) is the control the heart rate models must beat
    "constant": [],
    "hr vs race": [7],
    "hr vs grade": [8],
    "fatigue": [5],
    "hr vs grade + fatigue": [8, 5],
}


def _fit(rows, idx):
    """Least squares of log(actual / predicted) on 1 and log(features)."""
    X = [[1.0] + [math.log(r[i]) for i in idx] for r in rows]
    y = [math.log(r[3] / r[2]) for r in rows]
    n = len(idx) + 1
    a = [[sum(x[i] * x[j] for x in X) for j in range(n)] + [sum(x[i] * v for x, v in zip(X, y))] for i in range(n)]
    for c in range(n):  # Gauss-Jordan
        p = max(range(c, n), key=lambda r: abs(a[r][c]))
        a[c], a[p] = a[p], a[c]
        for r in range(n):
            if r != c:
                f = a[r][c] / a[c][c]
                a[r] = [u - f * v for u, v in zip(a[r], a[c])]
    return [a[i][n] / a[i][i] for i in range(n)]


def _apply(coef, idx, r):
    return r[2] * math.exp(coef[0] + sum(c * math.log(r[i]) for c, i in zip(coef[1:], idx)))


def summarize_hr_fit(res):
    """Fit each correction on one group of runs and score it on the others (runs with heart rate only)."""
    groups = {g: [r for rs in runs.values() for r in rs["now"] if r[7] and r[8] and r[5]] for g, runs in res.items()}
    print("\nheart rate corrections, fitted on one group and scored on another (min, runs with heart rate):")
    for fit_g, fit_rows in groups.items():
        if not fit_rows:
            continue
        for test_g, test_rows in groups.items():
            if test_g == fit_g or not test_rows:
                continue
            base = sum(abs(r[2] - r[3]) for r in test_rows) / len(test_rows) / 60
            line = []
            for name, idx in HR_MODELS.items():
                coef = _fit(fit_rows, idx)
                m = sum(abs(_apply(coef, idx, r) - r[3]) for r in test_rows) / len(test_rows) / 60
                line.append(f"{name} {m:.2f} ({' '.join(f'{c:+.2f}' for c in coef)})")
            print(f"  fit on {fit_g[:22]:<22} -> {test_g[:22]:<22} now {base:.2f} | " + " | ".join(line))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("hr_folder")
    ap.add_argument("--out")
    ap.add_argument("--load", help="summarize a saved --out instead of running")
    ap.add_argument("--set", default="first", choices=VARIANT_SETS, help="which variants to run")
    args = ap.parse_args()
    global VARIANTS
    VARIANTS = VARIANT_SETS[args.set]
    if args.load:
        res = json.loads(Path(args.load).read_text())
    else:
        todo = [(race_job, k) for k in B.RACES]
        for p, past in BT.history(args.folder, 25):
            todo.append((activity_job, ("activities of 25 km or more", p, past, False, args.hr_folder)))
        for p, past in BT.history(args.folder, 50):
            todo.append((activity_job, ("activities of 50 km or more, checkpoints at stops", p, past, True, args.hr_folder)))
        res = {}
        with ProcessPoolExecutor(8) as ex:
            futs = [ex.submit(f, a, VARIANTS) for f, a in todo]
            for f in futs:
                group, name, rows = f.result()
                res.setdefault(group, {})[name] = rows
        if args.out:
            Path(args.out).write_text(json.dumps(res))
    summarize_vam(res)
    summarize_hr(res)
    summarize_hr_fit(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())

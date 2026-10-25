#!/usr/bin/env python3
"""Speed now x slope ratio: predict every slope ahead from how fast you've been going over the
last stretch, times how much faster or slower you usually are on that slope compared with the
slopes you've just run.

    python tools/research/test_anchor.py FOLDER

The level is measured over the last WINDOW metres of moving: the time those metres would have
taken at the curve's speeds, over the time they really took. Variants:

- now:              today's field (its own slower, capped version of this: the fatigue factor)
- A1 textbook, W:   the curve is Tobler's (pure shape, nothing absolute learned); level over W
- A2 learned, W:    the curve is the field's own (today's running and past runs), whose level
                    is replaced by the one measured over W

Runs: the five races of benchmark.py (no pasted pace) and the activities of at least 25 km with
virtual checkpoints (past: everything before them, as the watch remembers it).
"""

from __future__ import annotations

import sys
from collections import deque
from concurrent.futures import ProcessPoolExecutor
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
from wpeta.field import shown_seconds  # noqa: E402

VARIANTS = [("now", None, 0), ("A1 textbook, 500 m", "tobler", 500), ("A1 textbook, 1 km", "tobler", 1000),
            ("A1 textbook, 2 km", "tobler", 2000), ("A2 learned, 500 m", "model", 500),
            ("A2 learned, 1 km", "model", 1000), ("A2 learned, 2 km", "model", 2000)]
LEVEL_RANGE = (0.3, 3.0)


class Anchor(P.HowFar):
    def __init__(self, curve: str, window: float, **kw) -> None:
        super().__init__(**kw)
        self.curve, self.window = curve, window
        self.recent: deque = deque()  # (metres, expected s at level 1, actual s)
        self.metres = self.expected = self.actual = 0.0

    def speed(self, g: float) -> float:
        """The curve's speed on slope g, before the level."""
        if self.curve == "tobler":
            return M.tobler_factor(g)  # level 1 = 1 m/s on the flat
        return self.model.predict(g)

    def observe(self, t, dist, alt):
        if not self.tracker.update(t, dist, alt):
            return
        g, v, w = self.tracker.last_grade, self.tracker.last_speed, self.tracker.last_dist
        exp, act = w / self.speed(g), w / v
        self.recent.append((w, exp, act))
        self.metres += w
        self.expected += exp
        self.actual += act
        while self.recent and self.metres - self.recent[0][0] >= self.window:
            m, e, a = self.recent.popleft()
            self.metres -= m
            self.expected -= e
            self.actual -= a
        self.est.observe(g, v, w)
        self.model.observe(g, v)

    def predict(self, ctx):
        self.scale.update(ctx.dist, ctx.dist_dest)
        s = self.scale.ratio
        if self.actual > 0 and self.metres >= min(self.window, 300):
            level = min(LEVEL_RANGE[1], max(LEVEL_RANGE[0], self.expected / self.actual))
        else:
            level = M.DEFAULT_FLAT_SPEED if self.curve == "tobler" else 1.0
        raw = max(1.0, sum(length * s / (self.speed(g / s) * level) for length, g in ctx.chunks))
        if ctx.wp_index != self._wp or ctx.dist_next > self._last_dn + 50:
            self._smooth = None
        self._wp, self._last_dn = ctx.wp_index, ctx.dist_next
        v = ctx.dist_next / raw
        self._smooth = v if self._smooth is None else self._smooth + (v - self._smooth) * P.SMOOTHING
        return ctx.dist_next / self._smooth


def score(race, past, first_wp=None):
    out = {}
    for name, curve, window in VARIANTS:
        pr = P.HowFar(past=past, raceday=True) if curve is None else Anchor(curve, window, past=past, raceday=True)
        rows = S.run(race, pr, trail_ahead=True, first_wp=first_wp)
        e = [abs(shown_seconds(eta) - am) / 60 for t, k, dn, eta, act, am in rows if am <= 3600]
        out[name] = (sum(e) / len(e), sum(x <= 5 for x in e) / len(e), sum(x <= 15 for x in e) / len(e)) if e else None
    return out


def race_job(key):
    return "five races (no pasted pace)", key, score(B.race(key), None)


def activity_job(args):
    path, past = args
    race = BA.as_race(Path(path).name, BA.load(Path(path)))
    return "activities of 25 km or more", Path(path).name, score(race, BT.layer_of(past), first_wp=1)


def main() -> int:
    folder = Path(sys.argv[1])
    res: dict = {}
    with ProcessPoolExecutor(8) as ex:
        futs = [ex.submit(race_job, k) for k in B.RACES] + [ex.submit(activity_job, a) for a in BT.history(folder, 25)]
        for f in futs:
            group, name, scores = f.result()
            res.setdefault(group, {})[name] = scores
    for group, runs in res.items():
        rs = [r for r in runs.values() if all(r[n] for n, _, _ in VARIANTS)]
        print(f"\n{group}: {len(rs)}")
        for name, _, _ in VARIANTS:
            m = lambda i: sum(r[name][i] for r in rs) / len(rs)
            extra = "   " + " ".join(f"{k} {runs[k][name][0]:.1f}" for k in runs) if len(runs) <= 6 else ""
            print(f"  {name:<22} {m(0):5.2f} min, {m(1) * 100:3.0f}% within 5, {m(2) * 100:3.0f}% within 15{extra}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

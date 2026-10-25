"""Build a speed-by-grade model from recorded activities."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .model import GradeTracker, Layer, bin_index
from .readers import Point, read_track


def observations(points: Iterable[Point]) -> list[tuple[float, float, float]]:
    """(grade %, speed m/s, window m) observations, computed exactly as the watch does."""
    tracker = GradeTracker()
    out = []
    for p in points:
        if p.t is None or p.alt is None:
            continue
        if tracker.update(p.t, p.dist, p.alt):
            out.append((tracker.last_grade, tracker.last_speed, tracker.last_dist))
    return out


def layer_from_files(paths: Iterable[str | Path]) -> Layer:
    layer = Layer()
    for path in paths:
        for grade, speed, _ in observations(read_track(path)):
            layer.add(bin_index(grade), speed, 1.0)
    return layer

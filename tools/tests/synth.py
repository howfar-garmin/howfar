"""Synthetic activities and courses, written as FIT or GPX, for the tests."""

from __future__ import annotations

import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path

FIT_EPOCH = datetime(1989, 12, 31, tzinfo=timezone.utc)
START = datetime(2026, 5, 1, 8, 0, tzinfo=timezone.utc)
M_PER_DEG_LAT = 111194.93  # haversine metres per degree with the reader's earth radius

_CRC_TABLE = [
    0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
    0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400,
]


def _crc(data: bytes, crc: int = 0) -> int:
    for byte in data:
        tmp = _CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ _CRC_TABLE[byte & 0xF]
        tmp = _CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ _CRC_TABLE[(byte >> 4) & 0xF]
    return crc


def samples(segments: list[tuple[float, float, float]], alt0: float = 300.0) -> list[dict]:
    """1 Hz samples for segments of (length m, grade %, speed m/s)."""
    out = []
    t = 0.0
    dist = 0.0
    alt = alt0
    out.append(dict(t=0.0, dist=0.0, alt=alt0, speed=segments[0][2]))
    for length, grade, speed in segments:
        end = dist + length
        while dist < end - 1e-9:
            step = min(speed, end - dist)
            dt = step / speed
            dist += step
            alt += step * grade / 100.0
            t += dt
            out.append(dict(t=t, dist=dist, alt=alt, speed=speed))
    for s in out:
        s["lat"] = 45.0 + s["dist"] / M_PER_DEG_LAT
        s["lon"] = 7.0
    return out


def _semi(deg: float) -> int:
    return int(round(deg / 180.0 * 2**31))


def write_fit(path: Path, recs: list[dict], course_points: list[tuple[str, float]] = (), file_type: int = 4) -> None:
    body = bytearray()

    def define(local: int, glob: int, fields: list[tuple[int, int, int]]) -> None:
        body.extend(struct.pack("<BBBHB", 0x40 | local, 0, 0, glob, len(fields)))
        for num, size, base in fields:
            body.extend(struct.pack("<BBB", num, size, base))

    ts0 = int((START - FIT_EPOCH).total_seconds())
    define(0, 0, [(0, 1, 0x00)])  # file_id.type
    body.extend(struct.pack("<BB", 0, file_type))
    define(1, 20, [(253, 4, 0x86), (5, 4, 0x86), (78, 4, 0x86), (73, 4, 0x86), (0, 4, 0x85), (1, 4, 0x85)])
    for r in recs:
        body.extend(struct.pack(
            "<BIIIIii", 1, ts0 + int(round(r["t"])), int(round(r["dist"] * 100)),
            int(round((r["alt"] + 500) * 5)), int(round(r["speed"] * 1000)), _semi(r["lat"]), _semi(r["lon"]),
        ))
    if course_points:
        define(2, 32, [(1, 4, 0x86), (4, 4, 0x86), (5, 1, 0x00), (6, 16, 0x07)])
        for name, d in course_points:
            raw = name.encode()[:15].ljust(16, b"\0")
            body.extend(struct.pack("<BIIB", 2, ts0, int(round(d * 100)), 0) + raw)

    header = struct.pack("<BBHI4s", 14, 0x20, 2132, len(body), b".FIT")
    header += struct.pack("<H", _crc(header))
    data = header + bytes(body)
    path.write_bytes(data + struct.pack("<H", _crc(data)))


def write_gpx(path: Path, recs: list[dict], waypoints: list[tuple[str, float]] = (), with_time: bool = True) -> None:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">']
    for name, d in waypoints:
        lines.append(f'<wpt lat="{45.0 + d / M_PER_DEG_LAT:.8f}" lon="7.0"><name>{name}</name></wpt>')
    lines.append("<trk><trkseg>")
    for r in recs:
        tm = ""
        if with_time:
            tm = f"<time>{(START + timedelta(seconds=r['t'])).strftime('%Y-%m-%dT%H:%M:%S.%fZ')}</time>"
        lines.append(f'<trkpt lat="{r["lat"]:.8f}" lon="{r["lon"]:.8f}"><ele>{r["alt"]:.2f}</ele>{tm}</trkpt>')
    lines.append("</trkseg></trk></gpx>")
    path.write_text("\n".join(lines))


def write_loop_gpx(path: Path) -> None:
    """A 10 km loop course, as race files come: the track ends a few metres off where it started,
    the start arch is near that end, the finish is at the start, and a hut a quarter of the way."""
    import math

    radius = 10000 / (2 * math.pi)
    m_lon = M_PER_DEG_LAT * math.cos(math.radians(45.0))

    def at(i: int) -> tuple[float, float]:
        a = 2 * math.pi * i / 1000
        return 45.0 + radius * math.sin(a) / M_PER_DEG_LAT, 7.0 + radius * (1 - math.cos(a)) / m_lon

    track = [at(i) for i in range(1000)] + [(45.0 + 3 / M_PER_DEG_LAT, 7.0 - 6 / m_lon)]
    hut = at(250)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">',
             f'<wpt lat="{45.0 + 3 / M_PER_DEG_LAT:.8f}" lon="{7.0 - 5 / m_lon:.8f}"><name>Start</name></wpt>',
             '<wpt lat="45.00000000" lon="7.00000000"><name>Finish</name></wpt>',
             f'<wpt lat="{hut[0]:.8f}" lon="{hut[1]:.8f}"><name>Rifugio</name></wpt>',
             "<trk><trkseg>"]
    for i, (lat, lon) in enumerate(track):
        lines.append(f'<trkpt lat="{lat:.8f}" lon="{lon:.8f}"><ele>{1000 + 100 * math.sin(2 * math.pi * i / 1000):.2f}</ele></trkpt>')
    lines.append("</trkseg></trk></gpx>")
    path.write_text("\n".join(lines))

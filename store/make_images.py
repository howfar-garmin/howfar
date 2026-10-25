#!/usr/bin/env python3
"""Draws the Connect IQ Store cover (500x500) and hero (1440x720) images into store/images/.

    .venv/bin/pip install pillow
    .venv/bin/python store/make_images.py

Uses macOS's Avenir Next fonts; the course silhouette comes from the site's demo data.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "store" / "images"
COND = "/System/Library/Fonts/Supplemental/Avenir Next Condensed.ttc"
SANS = "/System/Library/Fonts/Avenir Next.ttc"
BOLD, DEMI, MEDIUM, REGULAR = 0, 2, 5, 7

BG = (16, 21, 19)
INK = (232, 238, 234)
INK_2 = (178, 189, 183)
ACCENT = (108, 193, 150)
BEZEL = (47, 51, 49)
BEZEL_EDGE = (29, 32, 31)
TICK = (155, 197, 61)
SCREEN = (5, 6, 5)
SS = 3  # supersampling for smooth edges


def font(path: str, index: int, size: float) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, int(size * SS), index=index)


def text_center(d: ImageDraw.ImageDraw, cx: float, cy: float, s: str, f, fill) -> None:
    d.text((cx * SS, cy * SS), s, font=f, fill=fill, anchor="mm")


GREEN, YELLOW, RED = (63, 207, 114), (242, 182, 48), (239, 90, 79)


def line_with_dot(d: ImageDraw.ImageDraw, cx: float, cy: float, text: str, f, fill, dot, dr: float) -> None:
    """A line centred on cx with its coloured dot before it, as the field draws its times."""
    s = lambda v: v * SS
    tw = d.textlength(text, font=f) / SS
    left = cx - (tw + dr * 3) / 2
    d.ellipse([s(left), s(cy - dr), s(left + 2 * dr), s(cy + dr)], fill=dot)
    d.text((s(left + dr * 3), s(cy)), text, font=f, fill=fill, anchor="lm")


def watch(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float, minor: tuple | None, label: str, time: str, unit: str,
          arrive: str, dot, then: tuple | None) -> None:
    """A round watch like the site's: bezel, tick ring, black screen with the field on a screen of
    its own: the minor point on the way (grey), the main checkpoint, the time with its dot, unit
    and arrival, then the next main checkpoint with its leg time."""
    s = lambda v: v * SS
    d.ellipse([s(cx - r - 3), s(cy - r + 6), s(cx + r + 3), s(cy + r + 12)], fill=(0, 0, 0, 90))  # shadow
    d.ellipse([s(cx - r), s(cy - r), s(cx + r), s(cy + r)], fill=BEZEL_EDGE)
    d.ellipse([s(cx - r * 0.97), s(cy - r * 0.97), s(cx + r * 0.97), s(cy + r * 0.97)], fill=BEZEL)
    for k in range(12):
        a = math.radians(k * 30)
        r1, r2 = r * 0.93, r * 0.86
        d.line([s(cx + r1 * math.sin(a)), s(cy - r1 * math.cos(a)), s(cx + r2 * math.sin(a)), s(cy - r2 * math.cos(a))],
               fill=TICK, width=int(s(max(2, r * 0.018))))
    rs = r * 0.84
    d.ellipse([s(cx - rs), s(cy - rs), s(cx + rs), s(cy + rs)], fill=SCREEN)
    small = font(SANS, MEDIUM, rs * 0.12)
    if minor:
        line_with_dot(d, cx, cy - rs * 0.58, minor[0], small, INK_2, minor[1], rs * 0.03)
    text_center(d, cx, cy - rs * 0.36, label, font(SANS, DEMI, rs * 0.14), INK)
    # the digits big after their dot, the unit and the arrival small and stacked after them
    big, side = font(COND, BOLD, rs * 0.46), font(SANS, DEMI, rs * 0.12)
    gap, dr = rs * 0.04, rs * 0.055
    dw = d.textlength(time, font=big) / SS
    sw = max(d.textlength(unit, font=side), d.textlength(arrive, font=side)) / SS
    left = cx - (dr * 3 + dw + gap + sw) / 2
    ty = cy + rs * 0.04
    d.ellipse([s(left), s(ty - dr), s(left + 2 * dr), s(ty + dr)], fill=dot)
    left += dr * 3
    d.text((s(left), s(ty)), time, font=big, fill=INK, anchor="lm")
    d.text((s(left + dw + gap), s(ty - rs * 0.07)), unit, font=side, fill=INK, anchor="lm")
    d.text((s(left + dw + gap), s(ty + rs * 0.09)), arrive, font=side, fill=INK, anchor="lm")
    if then:
        line_with_dot(d, cx, cy + rs * 0.42, then[0], small, INK, then[1], rs * 0.03)


def course_profile() -> list[tuple[float, float]]:
    text = (ROOT / "docs/demo/torx-s1.js").read_text()
    data = json.loads(text[text.index("{"): text.rindex("}") + 1])
    return [(d, a) for d, a in data["profile"]], [(w["d"], w["alt"]) for w in data["waypoints"][2:]]


def profile_band(d: ImageDraw.ImageDraw, x0, y0, x1, y1, fill, line, dots) -> None:
    prof, wps = course_profile()
    dmax = prof[-1][0]
    amin = min(a for _, a in prof)
    amax = max(a for _, a in prof)
    px = lambda dist: (x0 + (x1 - x0) * dist / dmax) * SS
    py = lambda alt: (y1 - (y1 - y0) * (alt - amin) / (amax - amin)) * SS
    pts = [(px(dd), py(a)) for dd, a in prof]
    d.polygon([(x0 * SS, y1 * SS + 2000), *pts, (x1 * SS, y1 * SS + 2000)], fill=fill)
    d.line(pts, fill=line, width=3 * SS, joint="curve")
    if dots:
        for dd, a in wps:
            cx, cy = px(dd), py(a)
            rr = 5 * SS
            d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=BG, outline=INK, width=2 * SS)


def save(img: Image.Image, size: tuple[int, int], name: str, limit_kb: int) -> None:
    out = img.resize(size, Image.LANCZOS).convert("RGB")
    path = OUT / name
    out.save(path, optimize=True)
    kb = path.stat().st_size / 1024
    if kb > limit_kb:  # fall back to JPEG to stay under the store's limit
        path.unlink()
        path = path.with_suffix(".jpg")
        out.save(path, quality=90, optimize=True)
        kb = path.stat().st_size / 1024
    print(f"{path.relative_to(ROOT)}: {size[0]}x{size[1]}, {kb:.0f} KB (limit {limit_kb} KB)")


def cover() -> None:
    W = H = 500
    img = Image.new("RGB", (W * SS, H * SS), BG)  # RGB base so RGBA drawing blends
    d = ImageDraw.Draw(img, "RGBA")
    profile_band(d, -10, 360, W + 10, 500, fill=(108, 193, 150, 26), line=(108, 193, 150, 90), dots=False)
    watch(d, W / 2, 205, 150, ("Col d'Arp in 0:35", GREEN), "P Baite Youlaz", "1:10", "h", "@14:05", YELLOW,
          ("then La Thuile +0:55", YELLOW))
    text_center(d, W / 2, 425, "HowFar?", font(COND, BOLD, 64), INK)
    text_center(d, W / 2, 468, "time to the next checkpoint", font(SANS, MEDIUM, 21), ACCENT)
    save(img, (W, H), "cover-500.png", 300)


def hero() -> None:
    W, H = 1440, 720
    img = Image.new("RGB", (W * SS, H * SS), BG)  # RGB base so RGBA drawing blends
    d = ImageDraw.Draw(img, "RGBA")
    profile_band(d, -10, 520, W + 10, 700, fill=(108, 193, 150, 30), line=(108, 193, 150, 160), dots=True)
    left = 96
    d.text((left * SS, 120 * SS), "HOWFAR · FREE DATA FIELD FOR GARMIN", font=font(SANS, DEMI, 22), fill=ACCENT)
    y = 165
    for line in ("How long to the", "next checkpoint?"):
        d.text((left * SS, y * SS), line, font=font(COND, BOLD, 92), fill=INK)
        y += 100
    d.text((left * SS, 385 * SS), "Learned from how you climb and descend.", font=font(SANS, MEDIUM, 28), fill=INK_2)
    d.text((left * SS, 425 * SS), "#ultratrail  #trailrunning  #skyrunning", font=font(SANS, DEMI, 22), fill=ACCENT)
    watch(d, 1110, 285, 200, ("Lac du Fond in 0:20", GREEN), "P Planaval", "1:20", "h", "@19:10", YELLOW,
          ("then Valgrisenche +1:25", YELLOW))
    save(img, (W, H), "hero-1440x720.png", 2048)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    cover()
    hero()

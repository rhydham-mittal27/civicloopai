"""Draws the app icons: a closed loop with an arrowhead (the CivicLoop idea), orange for residents and navy for crews.

Run: python mobile/scripts/make_icons.py
"""

import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1] / "apps"
SS = 4  # draw big and shrink, for smooth edges


def loop(size: int, colour: tuple[int, int, int, int], scale: float = 1.0) -> Image.Image:
    """A transparent square with a loop glyph centred in it: an open ring, an arrowhead, a dot in the middle."""
    big = size * SS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = big / 2
    r = big * 0.25 * scale
    w = big * 0.08 * scale
    box = [cx - r, cy - r, cx + r, cy + r]
    start, end = 30, 322  # angles run clockwise from 3 o'clock; the gap sits at the upper right
    d.arc(box, start, end, fill=colour, width=int(w))
    a0 = math.radians(start)
    x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
    d.ellipse([x0 - w / 2, y0 - w / 2, x0 + w / 2, y0 + w / 2], fill=colour)  # rounded start
    # arrowhead: its base sits on the ring's end, its tip points on round the loop
    a1 = math.radians(end)
    px, py = cx + r * math.cos(a1), cy + r * math.sin(a1)
    radial = (math.cos(a1), math.sin(a1))
    forward = (-math.sin(a1), math.cos(a1))
    half, length = w * 1.45, w * 2.0
    tip = (px + forward[0] * length, py + forward[1] * length)
    left = (px + radial[0] * half, py + radial[1] * half)
    right = (px - radial[0] * half, py - radial[1] * half)
    d.polygon([tip, left, right], fill=colour)
    dot = r * 0.3
    d.ellipse([cx - dot, cy - dot, cx + dot, cy + dot], fill=colour)
    return img.resize((size, size), Image.LANCZOS)


def solid(size: int, rgb: tuple[int, int, int]) -> Image.Image:
    """A glossy vertical gradient: the given colour at the bottom, lifted and brighter at the top, with a soft shine."""
    top = tuple(min(255, int(c + (255 - c) * 0.38)) for c in rgb)
    column = Image.new("RGBA", (1, size))
    for y in range(size):
        t = y / (size - 1)
        column.putpixel((0, y), tuple(int(top[i] + (rgb[i] - top[i]) * t) for i in range(3)) + (255,))
    img = column.resize((size, size))
    shine = Image.new("RGBA", (1, size // 2))
    for y in range(size // 2):
        shine.putpixel((0, y), (255, 255, 255, int(70 * (1 - y / (size // 2)))))
    img.alpha_composite(shine.resize((size, size // 2)))
    return img


def build(app: str, background: tuple[int, int, int]) -> None:
    out = ROOT / app / "assets"
    out.mkdir(parents=True, exist_ok=True)
    white = (255, 255, 255, 255)
    # the store icon: glyph on a solid background, no transparency
    icon = solid(1024, background)
    icon.alpha_composite(loop(1024, white))
    icon.convert("RGB").save(out / "icon.png")
    # Android adaptive icon: foreground keeps the glyph inside the safe area
    loop(1024, white, 0.85).save(out / "android-icon-foreground.png")
    solid(1024, background).convert("RGB").save(out / "android-icon-background.png")
    loop(1024, (0, 0, 0, 255), 0.85).save(out / "android-icon-monochrome.png")
    # splash and web
    loop(1024, tuple(background) + (255,), 1.0).save(out / "splash-icon.png")
    favicon = solid(48, background)
    favicon.alpha_composite(loop(48, white))
    favicon.convert("RGB").save(out / "favicon.png")
    print("icons ->", out)


if __name__ == "__main__":
    build("resident", (212, 80, 26))
    build("crew", (20, 33, 61))

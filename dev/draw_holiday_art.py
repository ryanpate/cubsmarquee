#!/usr/bin/env python3
"""Draw the first-draft pixel art for the holiday facts screen.

Writes holidays/<slug>_card.png (96x48) and holidays/<slug>_band.png
(96x30) for every holiday in holiday_display.HOLIDAYS. No lettering is
drawn: the display code adds the greeting on top.

WARNING: re-running this overwrites every PNG, including any that were
touched up by hand in a pixel editor. The PNGs are the source of truth
once edited; pass slugs to redraw only those:

    python3 dev/draw_holiday_art.py christmas easter

Usage (from repo root): python3 dev/draw_holiday_art.py
"""
from __future__ import annotations

import math
import os
import random
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

from PIL import Image, ImageChops, ImageDraw  # noqa: E402

import holiday_display as hd  # noqa: E402

WIDTH = 96
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (225, 35, 45)
GOLD = (255, 205, 50)
BLUE = (50, 120, 235)
SNOW = (225, 232, 245)


class Art:
    """A 96-wide canvas with a square drawing area inside the art box.

    Shapes take unit coordinates: (0, 0) is the top-left of the square,
    (1, 1) the bottom-right. The square is as large as the art box
    (everything left of the lettering) allows and sits on its floor, so
    one drawing serves both the 48-row card and the 30-row band.
    """

    def __init__(self, height: int, left: int, center: bool = False) -> None:
        self.h = height
        self.left = left
        self.im = Image.new('RGB', (WIDTH, height), BLACK)
        self.d = ImageDraw.Draw(self.im)
        self.s = min(left - 2, height - 2)
        self.ox = 1 + (left - 2 - self.s) // 2
        self.oy = (height - self.s) // 2 if center else height - 1 - self.s

    # -- mapping --------------------------------------------------------
    def pt(self, u: float, v: float) -> tuple[int, int]:
        return (self.ox + round(u * (self.s - 1)),
                self.oy + round(v * (self.s - 1)))

    def px_len(self, f: float) -> int:
        return max(1, round(f * self.s))

    # -- backgrounds (full canvas) ---------------------------------------
    def sky(self, top: tuple, bottom: tuple) -> None:
        for y in range(self.h):
            t = y / (self.h - 1)
            color = tuple(round(a + (b - a) * t) for a, b in zip(top, bottom))
            self.d.line([(0, y), (WIDTH - 1, y)], fill=color)

    def ground(self, color: tuple, rows: int = 3, bumps: float = 0.0) -> None:
        for x in range(WIDTH):
            bump = round(bumps * (1 + math.sin(x / 7.0)) / 2)
            self.d.line([(x, self.h - rows - bump), (x, self.h - 1)],
                        fill=color)

    def skyline(self, seed: int, color: tuple, window: tuple) -> None:
        """Low row of buildings across the bottom, short under the text"""
        rng = random.Random(seed)
        x = 0
        tall = 6 if self.h > 30 else 4
        while x < WIDTH:
            w = rng.randint(3, 7)
            limit = tall if x < self.left else 3
            top = self.h - rng.randint(2, limit)
            self.d.rectangle([x, top, x + w - 1, self.h - 1], fill=color)
            for wx in range(x + 1, min(x + w - 1, WIDTH), 2):
                for wy in range(top + 1, self.h - 1, 2):
                    if rng.random() < 0.3:
                        self.im.putpixel((wx, wy), window)
            x += w

    # -- shapes (unit coordinates) ---------------------------------------
    def circle(self, u: float, v: float, r: float, fill: tuple) -> None:
        x, y = self.pt(u, v)
        rr = max(1, round(r * self.s))
        self.d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=fill)

    def ellipse(self, u0: float, v0: float, u1: float, v1: float,
                fill: tuple) -> None:
        self.d.ellipse([self.pt(u0, v0), self.pt(u1, v1)], fill=fill)

    def rect(self, u0: float, v0: float, u1: float, v1: float,
             fill: tuple) -> None:
        self.d.rectangle([self.pt(u0, v0), self.pt(u1, v1)], fill=fill)

    def poly(self, points: list, fill: tuple) -> None:
        self.d.polygon([self.pt(u, v) for u, v in points], fill=fill)

    def line(self, points: list, fill: tuple, width: int = 1) -> None:
        self.d.line([self.pt(u, v) for u, v in points], fill=fill,
                    width=width)

    def dot(self, u: float, v: float, fill: tuple,
            dx: int = 0, dy: int = 0) -> None:
        x, y = self.pt(u, v)
        if 0 <= x + dx < WIDTH and 0 <= y + dy < self.h:
            self.im.putpixel((x + dx, y + dy), fill)

    def heart(self, u: float, v: float, size: float, fill: tuple,
              turn: float = 0.0) -> None:
        """Heart centered at (u, v); turn rotates it clockwise in degrees
        (0 = point down)"""
        cos_t, sin_t = math.cos(math.radians(turn)), math.sin(math.radians(turn))
        points = []
        for k in range(48):
            t = 2 * math.pi * k / 48
            hx = 16 * math.sin(t) ** 3 / 34
            hy = -(13 * math.cos(t) - 5 * math.cos(2 * t)
                   - 2 * math.cos(3 * t) - math.cos(4 * t)) / 34 - 0.06
            points.append((u + size * (hx * cos_t - hy * sin_t),
                           v + size * (hx * sin_t + hy * cos_t)))
        self.poly(points, fill)

    def blob(self, u: float, v: float, fill: tuple) -> None:
        """A light: one pixel on the band, 2x2 on the larger card"""
        x, y = self.pt(u, v)
        size = 1 if self.s < 34 else 2
        self.d.rectangle([x, y, x + size - 1, y + size - 1], fill=fill)

    # -- clipping ----------------------------------------------------------
    def layer(self) -> 'Art':
        """A transparent copy of this canvas's geometry to draw on, then
        stamp() back through a mask"""
        other = Art.__new__(Art)
        other.__dict__.update(self.__dict__)
        other.im = Image.new('RGBA', (WIDTH, self.h), (0, 0, 0, 0))
        other.d = ImageDraw.Draw(other.im)
        return other

    def stamp(self, layer: 'Art', mask_shape) -> None:
        """Paste a layer, keeping only what falls inside mask_shape(art)"""
        mask_art = Art.__new__(Art)
        mask_art.__dict__.update(self.__dict__)
        mask_art.im = Image.new('L', (WIDTH, self.h), 0)
        mask_art.d = ImageDraw.Draw(mask_art.im)
        mask_shape(mask_art)
        alpha = ImageChops.multiply(layer.im.getchannel('A'), mask_art.im)
        self.im.paste(layer.im.convert('RGB'), (0, 0), alpha)
        self.d = ImageDraw.Draw(self.im)


# ---------------------------------------------------------------------------
# Scenes. Each returns a finished Art for the given canvas height.
# ---------------------------------------------------------------------------

def new_years_day(h: int, left: int) -> Art:
    a = Art(h, left, center=True)
    a.sky((8, 10, 36), (18, 14, 54))
    balloons = [(0.24, 0.30, RED), (0.52, 0.20, GOLD), (0.78, 0.34, BLUE)]
    for u, v, _ in balloons:
        a.line([(u, v + 0.17), (0.46, 0.99)], (190, 190, 205))
    for u, v, color in balloons:
        a.ellipse(u - 0.17, v - 0.19, u + 0.17, v + 0.17, color)
        a.dot(u, v + 0.17, color, dy=1)
        a.dot(u - 0.07, v - 0.09, WHITE)
        a.dot(u - 0.07, v - 0.09, WHITE, dx=-1, dy=1)
    # party hat
    a.poly([(0.66, 0.99), (0.99, 0.99), (0.83, 0.58)], (170, 70, 220))
    a.line([(0.72, 0.86), (0.93, 0.86)], GOLD)
    a.line([(0.77, 0.74), (0.89, 0.74)], GOLD)
    a.circle(0.83, 0.57, 0.04, WHITE)
    return a


def groundhog_day(h: int, left: int) -> Art:
    a = Art(h, left)
    brown, belly, dark = (150, 100, 55), (205, 165, 110), (70, 45, 25)
    a.sky((16, 34, 70), (60, 100, 150))
    a.ground(SNOW, 3)
    a.ellipse(0.02, 0.70, 0.98, 1.25, SNOW)          # snow mound
    a.ellipse(0.72, 0.86, 1.25, 0.97, (150, 168, 205))  # his shadow
    a.ellipse(0.26, 0.72, 0.74, 0.94, (45, 30, 22))   # burrow
    a.ellipse(0.33, 0.34, 0.67, 0.92, brown)          # body
    a.ellipse(0.41, 0.52, 0.59, 0.90, belly)
    a.circle(0.38, 0.16, 0.035, dark)                 # ears
    a.circle(0.62, 0.16, 0.035, dark)
    a.circle(0.50, 0.28, 0.17, brown)                 # head
    a.ellipse(0.42, 0.30, 0.58, 0.42, belly)          # muzzle
    a.dot(0.43, 0.24, BLACK)
    a.dot(0.57, 0.24, BLACK)
    a.dot(0.50, 0.32, (40, 25, 20))
    a.dot(0.50, 0.38, WHITE)
    a.circle(0.37, 0.60, 0.04, dark)                  # paws
    a.circle(0.63, 0.60, 0.04, dark)
    a.ellipse(0.22, 0.87, 0.78, 1.05, SNOW)           # snow in front
    return a


def valentines_day(h: int, left: int) -> Art:
    a = Art(h, left, center=True)
    shaft, red = (255, 215, 90), (228, 30, 60)
    a.sky((40, 6, 24), (66, 10, 38))
    thick = 1 if a.s < 34 else 2
    a.heart(0.50, 0.50, 0.92, red)
    a.circle(0.32, 0.32, 0.05, (255, 150, 170))       # shine
    a.line([(0.00, 0.94), (0.24, 0.74)], shaft, thick)  # arrow tail
    a.line([(0.74, 0.32), (0.96, 0.14)], shaft, thick)  # arrow head end
    a.poly([(1.00, 0.08), (0.80, 0.14), (0.94, 0.30)], WHITE)
    a.line([(0.00, 0.94), (0.00, 0.80)], WHITE)       # fletching
    a.line([(0.00, 0.94), (0.14, 0.94)], WHITE)
    return a


def st_patricks_day(h: int, left: int) -> Art:
    a = Art(h, left)
    leaf, dark = (50, 190, 80), (22, 120, 48)
    a.sky((4, 28, 14), (10, 50, 24))
    bands = [(235, 50, 50), (250, 150, 40), (250, 225, 60),
             (60, 190, 90), (70, 130, 240)]
    thick = 1 if a.s < 34 else 2
    lay = a.layer()                                   # rainbow
    cx, cy = a.pt(0.22, 0.98)
    for i, color in enumerate(bands):
        for t in range(thick):
            r = round(0.62 * a.s) - i * thick - t
            lay.d.arc([cx - r, cy - r, cx + r, cy + r], 180, 360, fill=color)
    a.stamp(lay, lambda m: m.d.rectangle([0, 0, left - 1, h - 1], fill=255))
    # pot of gold at the rainbow's foot
    a.ellipse(0.66, 0.66, 1.0, 0.84, GOLD)
    a.ellipse(0.62, 0.76, 1.0, 1.0, (34, 34, 40))
    a.rect(0.60, 0.76, 1.0, 0.82, (70, 70, 80))
    a.dot(0.76, 0.68, WHITE)
    a.dot(0.90, 0.70, WHITE)
    # shamrock: three hearts with their points together
    u, v, size = 0.68, 0.26, 0.30
    a.line([(u, v + 0.04), (u + 0.02, v + 0.22), (u - 0.06, v + 0.34)], dark)
    a.heart(u, v - 0.15, size, leaf)
    a.heart(u - 0.15, v + 0.06, size, leaf, turn=-115)
    a.heart(u + 0.15, v + 0.06, size, leaf, turn=115)
    a.dot(u, v, dark)
    return a


def _palm_branch(a: Art, base: tuple, ctrl: tuple, tip: tuple) -> None:
    spine, greens = (70, 120, 40), ((60, 175, 70), (95, 215, 95))
    steps = a.s
    points = []
    for i in range(steps + 1):
        t = i / steps
        points.append((
            (1 - t) ** 2 * base[0] + 2 * (1 - t) * t * ctrl[0] + t * t * tip[0],
            (1 - t) ** 2 * base[1] + 2 * (1 - t) * t * ctrl[1] + t * t * tip[1]))
    for i in range(3, steps + 1, 2):
        t = i / steps
        (u0, v0), (u1, v1) = points[i - 1], points[i]
        norm = math.hypot(u1 - u0, v1 - v0) or 1
        tu, tv = (u1 - u0) / norm, (v1 - v0) / norm
        reach = 0.15 * math.sin(math.pi * min(1.0, 0.12 + t * 0.88)) ** 0.6
        for side in (-1, 1):                          # leaflets lean to the tip
            a.line([(u1, v1),
                    (u1 + side * -tv * reach + tu * reach * 0.8,
                     v1 + side * tu * reach + tv * reach * 0.8)],
                   greens[(i // 2) % 2])
    a.line(points, spine)


def palm_sunday(h: int, left: int) -> Art:
    a = Art(h, left)
    wall = (58, 36, 36)
    a.sky((44, 22, 60), (205, 125, 60))
    # city wall, low under the lettering
    rows = 5 if h > 30 else 3
    top = h - rows
    a.d.rectangle([0, top, WIDTH - 1, h - 1], fill=wall)
    for x in range(0, WIDTH, 4):
        a.d.rectangle([x, top - 1, x + 1, top - 1], fill=wall)
    _palm_branch(a, (0.40, 1.0), (0.36, 0.45), (0.06, 0.12))
    _palm_branch(a, (0.60, 1.0), (0.64, 0.45), (0.94, 0.12))
    _palm_branch(a, (0.50, 1.0), (0.50, 0.50), (0.50, 0.00))
    return a


def good_friday(h: int, left: int) -> Art:
    a = Art(h, left)
    wood, hill = (10, 6, 12), (16, 9, 20)
    a.sky((34, 14, 54), (170, 70, 60))
    a.circle(0.50, 0.66, 0.26, (240, 160, 90))        # low sun
    a.circle(0.50, 0.66, 0.19, (255, 200, 120))
    # hill: high under the crosses, low under the lettering
    x0, _ = a.pt(-0.5, 0)
    x1, _ = a.pt(1.5, 0)
    _, crest = a.pt(0, 0.74)
    a.d.ellipse([x0, crest, x1, h + a.s], fill=hill)
    a.d.rectangle([0, h - 3, WIDTH - 1, h - 1], fill=hill)
    for u, top, beam, half in ((0.50, 0.10, 0.26, 0.17),
                               (0.17, 0.36, 0.48, 0.11),
                               (0.83, 0.36, 0.48, 0.11)):
        x, y0 = a.pt(u, top)
        _, y1 = a.pt(u, 0.86)
        _, yb = a.pt(u, beam)
        hw = a.px_len(half)
        thick = 1 if a.s < 34 else 2
        a.d.rectangle([x, y0, x + thick - 1, y1], fill=wood)
        a.d.rectangle([x - hw, yb, x + hw + thick - 1, yb + thick - 1],
                      fill=wood)
    return a


def easter(h: int, left: int) -> Art:
    a = Art(h, left)
    fur, pink, grass = (250, 250, 250), (255, 150, 185), (50, 165, 60)
    a.sky((14, 46, 96), (60, 130, 170))
    a.ground(grass, 3)
    a.ellipse(0.19, 0.02, 0.29, 0.36, fur)            # ears
    a.ellipse(0.35, 0.02, 0.45, 0.36, fur)
    a.line([(0.24, 0.10), (0.24, 0.30)], pink)
    a.line([(0.40, 0.10), (0.40, 0.30)], pink)
    a.ellipse(0.06, 0.50, 0.52, 0.97, fur)            # body
    a.circle(0.32, 0.42, 0.15, fur)                   # head
    a.circle(0.06, 0.84, 0.06, fur)                   # tail
    a.dot(0.37, 0.39, BLACK)
    a.dot(0.45, 0.45, pink)
    # eggs
    a.ellipse(0.55, 0.46, 0.79, 0.95, (255, 120, 170))
    a.line([(0.57, 0.64), (0.77, 0.64)], WHITE)
    a.line([(0.56, 0.78), (0.78, 0.78)], (255, 230, 90))
    a.ellipse(0.78, 0.56, 1.0, 0.97, (250, 220, 70))
    for eu, ev in ((0.84, 0.70), (0.94, 0.72), (0.89, 0.84), (0.89, 0.62)):
        a.blob(eu, ev, (170, 90, 230))
    a.ellipse(0.66, 0.72, 0.88, 1.0, (80, 170, 250))
    a.line([(0.68, 0.88), (0.73, 0.82), (0.78, 0.88), (0.83, 0.82),
            (0.86, 0.88)], WHITE)
    for u in (0.02, 0.30, 0.54, 0.86):               # grass tufts
        a.line([(u, 0.99), (u + 0.02, 0.88)], grass)
    return a


def april_fools(h: int, left: int) -> Art:
    a = Art(h, left, center=True)
    purple = (150, 60, 210)
    a.sky((28, 8, 50), (50, 16, 80))
    a.poly([(0.16, 0.74), (0.52, 0.74), (0.04, 0.22)], RED)
    a.poly([(0.48, 0.74), (0.84, 0.74), (0.96, 0.22)], (40, 170, 90))
    a.poly([(0.28, 0.74), (0.72, 0.74), (0.50, 0.08)], GOLD)
    for u, v in ((0.04, 0.20), (0.96, 0.20), (0.50, 0.06)):
        a.circle(u, v, 0.055, (255, 235, 140))
        a.dot(u, v, (120, 80, 0), dy=1)
    a.rect(0.12, 0.72, 0.88, 0.90, purple)
    for u in (0.22, 0.36, 0.50, 0.64, 0.78):
        a.dot(u, 0.81, GOLD)
    return a


def earth_day(h: int, left: int) -> Art:
    a = Art(h, left, center=True)
    ocean, land, cloud = (30, 105, 225), (60, 180, 80), (235, 240, 250)
    a.sky((2, 4, 16), (8, 10, 34))
    a.circle(0.5, 0.5, 0.47, ocean)
    lay = a.layer()
    lay.poly([(0.16, 0.14), (0.50, 0.10), (0.56, 0.28), (0.44, 0.40),
              (0.36, 0.52), (0.26, 0.42), (0.12, 0.34)], land)   # N America
    lay.poly([(0.40, 0.56), (0.56, 0.60), (0.52, 0.80), (0.44, 0.94),
              (0.38, 0.74)], land)                                # S America
    lay.poly([(0.76, 0.22), (1.00, 0.20), (1.00, 0.70), (0.84, 0.66),
              (0.74, 0.44)], land)                                # Africa
    lay.line([(0.10, 0.60), (0.30, 0.60)], cloud)
    lay.line([(0.56, 0.44), (0.74, 0.44)], cloud)
    lay.line([(0.60, 0.86), (0.76, 0.86)], cloud)
    a.stamp(lay, lambda m: m.circle(0.5, 0.5, 0.47, 255))
    return a


def cinco_de_mayo(h: int, left: int) -> Art:
    a = Art(h, left)
    cactus, shade, straw = (45, 160, 70), (25, 110, 45), (225, 185, 95)
    a.sky((46, 14, 8), (84, 34, 12))
    a.ground((195, 150, 85), 3)
    # paper banners: across the whole card, only over the art on the band
    flags = [RED, WHITE, (50, 180, 80), GOLD, (240, 110, 180), BLUE]
    span = WIDTH if h > 30 else left
    a.d.line([(0, 0), (span - 1, 0)], fill=(230, 230, 230))
    for i, x in enumerate(range(1, span - 3, 6)):
        a.d.rectangle([x, 1, x + 3, 4], fill=flags[i % len(flags)])
        a.im.putpixel((x + 1, 3), (20, 8, 4))
    # cactus
    a.rect(0.12, 0.44, 0.24, 0.94, cactus)
    a.circle(0.18, 0.44, 0.06, cactus)
    a.line([(0.12, 0.70), (0.03, 0.70), (0.03, 0.56)], cactus, 2)
    a.line([(0.24, 0.64), (0.33, 0.64), (0.33, 0.50)], cactus, 2)
    a.line([(0.18, 0.44), (0.18, 0.92)], shade)
    # maracas
    for u, v, du in ((0.50, 0.26, -0.14), (0.86, 0.26, 0.14)):
        a.line([(u, v), (u - du, v + 0.24)], (235, 200, 140))
        a.circle(u + du * 0.3, v - 0.04, 0.09, RED)
        a.line([(u + du * 0.3 - 0.07, v - 0.04), (u + du * 0.3 + 0.07, v - 0.04)],
               GOLD)
    # sombrero
    a.ellipse(0.36, 0.72, 1.0, 0.94, straw)
    a.ellipse(0.52, 0.44, 0.84, 0.86, straw)
    a.line([(0.53, 0.72), (0.83, 0.72)], RED, 2)
    a.line([(0.40, 0.88), (0.96, 0.88)], (50, 170, 80))
    return a


def mothers_day(h: int, left: int) -> Art:
    a = Art(h, left, center=True)
    stem, paper = (50, 165, 70), (245, 230, 205)
    a.sky((36, 10, 44), (64, 20, 68))
    heads = [(0.14, 0.34, (255, 120, 170)), (0.32, 0.20, RED),
             (0.50, 0.30, (250, 215, 70)), (0.68, 0.18, (255, 120, 170)),
             (0.86, 0.34, (190, 110, 240))]
    for u, v, _ in heads:
        a.line([(u, v), (0.50, 0.70)], stem)
    a.poly([(0.20, 0.52), (0.36, 0.62), (0.30, 0.44)], stem)   # leaves
    a.poly([(0.80, 0.52), (0.64, 0.62), (0.70, 0.44)], stem)
    for u, v, color in heads:
        a.ellipse(u - 0.09, v - 0.10, u + 0.09, v + 0.10, color)
        a.poly([(u - 0.09, v), (u - 0.09, v - 0.16), (u - 0.03, v - 0.08),
                (u, v - 0.17), (u + 0.03, v - 0.08), (u + 0.09, v - 0.16),
                (u + 0.09, v)], color)
    a.poly([(0.28, 0.60), (0.72, 0.60), (0.50, 1.0)], paper)   # wrap
    a.poly([(0.50, 0.60), (0.72, 0.60), (0.50, 1.0)], (215, 195, 165))
    a.line([(0.36, 0.74), (0.64, 0.74)], (255, 120, 170), 2)   # ribbon
    return a


def fathers_day(h: int, left: int) -> Art:
    a = Art(h, left, center=True)
    tie, stripe = (40, 100, 225), (150, 195, 255)
    leather, dark = (165, 100, 50), (105, 60, 28)
    a.sky((8, 18, 46), (16, 32, 74))
    shape = [(0.17, 0.16), (0.33, 0.16), (0.44, 0.80), (0.25, 0.98),
             (0.06, 0.80)]
    a.poly(shape, tie)
    lay = a.layer()
    for k in range(-4, 10):
        lay.line([(0.0, 0.16 + k * 0.14), (0.5, 0.36 + k * 0.14)], stripe)
    a.stamp(lay, lambda m: m.poly(shape, 255))
    a.poly([(0.14, 0.02), (0.36, 0.02), (0.32, 0.17), (0.18, 0.17)],
           (25, 70, 180))                              # knot
    # glove and ball
    for u in (0.58, 0.69, 0.80, 0.91):                # fingers
        a.ellipse(u - 0.06, 0.24, u + 0.06, 0.60, leather)
    for u in (0.635, 0.745, 0.855):                   # gaps
        a.line([(u, 0.30), (u, 0.50)], dark)
    a.ellipse(0.46, 0.50, 0.62, 0.78, leather)        # thumb
    a.ellipse(0.50, 0.42, 1.0, 0.98, leather)
    a.ellipse(0.60, 0.54, 0.92, 0.90, dark)           # pocket
    a.circle(0.76, 0.72, 0.13, WHITE)
    a.dot(0.70, 0.66, RED)
    a.dot(0.72, 0.72, RED)
    a.dot(0.70, 0.78, RED)
    a.dot(0.82, 0.66, RED)
    a.dot(0.80, 0.72, RED)
    a.dot(0.82, 0.78, RED)
    return a


def independence_day(h: int, left: int) -> Art:
    a = Art(h, left)
    a.sky((4, 6, 26), (12, 16, 52))
    a.skyline(4, (18, 20, 40), (250, 220, 110))
    px0, py0 = a.pt(0.10, 0.04)
    _, py1 = a.pt(0.10, 1.0)
    a.d.line([(px0, py0), (px0, py1)], fill=(170, 170, 180))
    a.im.putpixel((px0, py0 - 1), GOLD)
    fx0, fy0 = px0 + 1, py0 + 1
    fw = a.pt(0.98, 0)[0] - fx0 + 1
    stripe = 2 if a.s < 34 else 3
    fh = stripe * 7
    canton_w, canton_h = round(fw * 0.44), stripe * 4
    for col in range(fw):
        wave = round(1.2 * math.sin(col / (fw / 6.5)))
        for row in range(fh):
            if col < canton_w and row < canton_h:
                color = (35, 60, 170)
                if (col % 3 == 1 and row % 3 == 1
                        and col < canton_w - 1 and row < canton_h - 1):
                    color = WHITE
            else:
                color = (215, 40, 50) if (row // stripe) % 2 == 0 else WHITE
            y = fy0 + row + wave
            if 0 <= y < h:
                a.im.putpixel((fx0 + col, y), color)
    return a


def halloween(h: int, left: int) -> Art:
    a = Art(h, left)
    orange, rib, glow = (240, 120, 20), (190, 80, 10), (255, 225, 70)
    ghost = (236, 236, 246)
    a.sky((18, 6, 34), (46, 16, 64))
    a.ground((14, 20, 12), 3)
    a.circle(0.28, 0.24, 0.20, (245, 235, 170))       # moon
    a.dot(0.22, 0.20, (215, 200, 140))
    a.dot(0.34, 0.30, (215, 200, 140))
    u, v = 0.66, 0.22                                 # bat
    a.poly([(u - 0.24, v - 0.02), (u - 0.12, v - 0.10), (u - 0.05, v - 0.02),
            (u, v - 0.07), (u + 0.05, v - 0.02), (u + 0.12, v - 0.10),
            (u + 0.24, v - 0.02), (u + 0.12, v + 0.03), (u + 0.06, v + 0.08),
            (u, v + 0.03), (u - 0.06, v + 0.08), (u - 0.12, v + 0.03)],
           (150, 95, 215))
    # ghost
    a.circle(0.17, 0.60, 0.14, ghost)
    a.rect(0.03, 0.60, 0.31, 0.92, ghost)
    for gu in (0.07, 0.17, 0.27):
        a.circle(gu, 0.92, 0.045, ghost)
    a.dot(0.12, 0.58, BLACK)
    a.dot(0.22, 0.58, BLACK)
    a.dot(0.17, 0.68, BLACK)
    # jack-o'-lantern
    a.rect(0.66, 0.46, 0.72, 0.58, (70, 130, 50))
    a.ellipse(0.40, 0.54, 1.0, 0.98, orange)
    for ru in (0.55, 0.85):
        a.line([(ru, 0.58), (ru, 0.94)], rib)
    a.poly([(0.52, 0.72), (0.62, 0.72), (0.57, 0.63)], glow)
    a.poly([(0.78, 0.72), (0.88, 0.72), (0.83, 0.63)], glow)
    a.poly([(0.52, 0.80), (0.60, 0.86), (0.66, 0.80), (0.74, 0.86),
            (0.80, 0.80), (0.88, 0.80), (0.80, 0.92), (0.60, 0.92)], glow)
    return a


def thanksgiving(h: int, left: int) -> Art:
    a = Art(h, left)
    body, head = (125, 75, 38), (185, 125, 70)
    feathers = [(200, 60, 30), (240, 140, 30), (250, 205, 60),
                (165, 90, 35)]
    a.sky((42, 20, 8), (92, 46, 12))
    a.ground((100, 66, 26), 3)
    cu, cv = 0.42, 0.66
    for i in range(7):                                # tail fan
        angle = math.radians(172 - i * 27.33)
        tu = cu + 0.40 * math.cos(angle)
        tv = cv - 0.54 * math.sin(angle)
        color = feathers[i % len(feathers)]
        a.line([(cu, cv), (tu, tv)], color, 3 if a.s > 30 else 2)
        a.circle(tu, tv, 0.065, color)
    a.circle(cu, 0.72, 0.21, body)                    # body
    a.ellipse(cu - 0.10, 0.62, cu + 0.10, 0.90, (95, 55, 28))
    a.circle(cu, 0.40, 0.12, (70, 40, 20))            # outline
    a.rect(cu - 0.035, 0.44, cu + 0.035, 0.62, head)  # neck
    a.circle(cu, 0.40, 0.09, head)
    a.dot(cu - 0.03, 0.38, BLACK)
    a.dot(cu + 0.04, 0.38, BLACK)
    a.poly([(cu - 0.02, 0.42), (cu + 0.04, 0.42), (cu + 0.01, 0.50)],
           (250, 200, 60))                            # beak
    a.line([(cu + 0.04, 0.46), (cu + 0.04, 0.54)], (225, 35, 45))  # wattle
    a.line([(cu - 0.08, 0.92), (cu - 0.08, 0.99)], (240, 150, 40))
    a.line([(cu + 0.08, 0.92), (cu + 0.08, 0.99)], (240, 150, 40))
    # pumpkin
    a.ellipse(0.74, 0.74, 1.0, 0.98, (240, 125, 25))
    a.line([(0.87, 0.76), (0.87, 0.96)], (190, 85, 15))
    a.rect(0.85, 0.68, 0.89, 0.74, (70, 130, 50))
    return a


def christmas_eve(h: int, left: int) -> Art:
    a = Art(h, left)
    ray, wood = (255, 235, 150), (120, 78, 40)
    a.sky((4, 8, 32), (18, 28, 70))
    hill = (6, 8, 18)
    x0, _ = a.pt(-0.6, 0)
    x1, _ = a.pt(1.6, 0)
    _, crest = a.pt(0, 0.86)
    a.d.ellipse([x0, crest, x1, h + a.s], fill=hill)
    a.d.rectangle([0, h - 2, WIDTH - 1, h - 1], fill=hill)
    # star with long rays
    a.line([(0.50, 0.00), (0.50, 0.46)], ray)
    a.line([(0.30, 0.16), (0.70, 0.16)], ray)
    a.line([(0.42, 0.08), (0.58, 0.24)], (190, 170, 110))
    a.line([(0.58, 0.08), (0.42, 0.24)], (190, 170, 110))
    a.circle(0.50, 0.16, 0.045, WHITE)
    for v in (0.52, 0.58):                           # beam toward the stable
        a.dot(0.50, v, (150, 135, 90))
    # stable
    a.rect(0.30, 0.72, 0.70, 0.92, (255, 190, 90))    # lamplight
    a.poly([(0.20, 0.72), (0.50, 0.58), (0.80, 0.72)], wood)
    a.line([(0.28, 0.72), (0.28, 0.93)], wood)
    a.line([(0.72, 0.72), (0.72, 0.93)], wood)
    a.rect(0.36, 0.78, 0.42, 0.92, (40, 70, 160))     # Mary
    a.dot(0.39, 0.76, (240, 200, 160))
    a.rect(0.58, 0.76, 0.64, 0.92, (150, 55, 40))     # Joseph
    a.dot(0.61, 0.74, (240, 200, 160))
    a.line([(0.46, 0.90), (0.54, 0.90)], (90, 55, 25))  # manger
    a.dot(0.50, 0.86, WHITE)
    return a


def christmas(h: int, left: int) -> Art:
    a = Art(h, left)
    light, mid, dark = (30, 160, 60), (20, 125, 46), (12, 92, 36)
    a.sky((8, 14, 40), (16, 26, 66))
    a.ground(SNOW, 3, bumps=1.5)
    tiers = [((0.50, 0.08), 0.20, 0.36), ((0.50, 0.24), 0.32, 0.60),
             ((0.50, 0.44), 0.44, 0.86)]
    for (tu, tv), half, base in tiers:
        a.poly([(tu, tv), (0.5 - half, base), (0.5 + half, base)], mid)
        a.poly([(tu, tv), (0.5 - half, base), (0.5 - half * 0.3, base)],
               light)
        a.poly([(tu, tv), (0.5 + half * 0.45, base), (0.5 + half, base)],
               dark)
    a.rect(0.45, 0.86, 0.55, 0.96, (115, 72, 32))
    for u, v, color in ((0.46, 0.28, RED), (0.56, 0.44, GOLD),
                        (0.38, 0.52, BLUE), (0.62, 0.64, RED),
                        (0.30, 0.74, GOLD), (0.50, 0.70, WHITE),
                        (0.72, 0.80, BLUE), (0.42, 0.80, RED)):
        a.blob(u, v, color)
    for du, dv in ((0, 0), (0, 1), (0, 2), (-1, 1), (1, 1)):   # star
        a.dot(0.50, 0.03, GOLD, dx=du, dy=dv - 1)
    # presents
    a.rect(0.74, 0.80, 0.96, 0.97, RED)
    a.line([(0.85, 0.80), (0.85, 0.97)], GOLD)
    a.line([(0.74, 0.88), (0.96, 0.88)], GOLD)
    a.rect(0.02, 0.84, 0.18, 0.97, BLUE)
    a.line([(0.10, 0.84), (0.10, 0.97)], WHITE)
    return a


def new_years_eve(h: int, left: int) -> Art:
    a = Art(h, left)
    face, hand = (246, 240, 224), (30, 30, 44)
    a.sky((4, 4, 22), (14, 12, 48))
    a.skyline(9, (18, 18, 38), (250, 220, 110))
    cu, cv = 0.50, 0.44
    a.circle(cu, cv, 0.43, GOLD)
    a.circle(cu, cv, 0.38, face)
    for k in range(12):
        angle = math.radians(k * 30)
        a.dot(cu + 0.32 * math.sin(angle), cv - 0.32 * math.cos(angle),
              (120, 110, 100))
    a.line([(cu, cv), (cu, cv - 0.20)], hand, 2 if a.s > 30 else 1)
    a.line([(cu, cv), (cu - 0.11, cv - 0.30)], hand)
    a.dot(cu, cv, (225, 35, 45))
    return a


SCENES = {
    'new_years_day': new_years_day, 'groundhog_day': groundhog_day,
    'valentines_day': valentines_day, 'st_patricks_day': st_patricks_day,
    'palm_sunday': palm_sunday, 'good_friday': good_friday,
    'easter': easter, 'april_fools': april_fools, 'earth_day': earth_day,
    'cinco_de_mayo': cinco_de_mayo, 'mothers_day': mothers_day,
    'fathers_day': fathers_day, 'independence_day': independence_day,
    'halloween': halloween, 'thanksgiving': thanksgiving,
    'christmas_eve': christmas_eve, 'christmas': christmas,
    'new_years_eve': new_years_eve,
}


def main() -> None:
    os.makedirs(hd.ART_DIR, exist_ok=True)
    slugs = sys.argv[1:] or [h.slug for h in hd.HOLIDAYS]
    for slug in slugs:
        holiday = hd.HOLIDAYS_BY_SLUG[slug]
        scene = SCENES[slug]
        scene(48, holiday.card_left).im.save(
            os.path.join(hd.ART_DIR, f'{slug}_card.png'))
        scene(30, holiday.band_left).im.save(
            os.path.join(hd.ART_DIR, f'{slug}_band.png'))
        print(f'  drew {slug}')


if __name__ == '__main__':
    main()

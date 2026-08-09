"""Generate Cardinals marquee and win-celebration assets.

Run from the repo root:  python3 dev/generate_cardinals_assets.py
Pixel art is expected to be iterated on against the real matrix; keep this
script as the source of truth and regenerate rather than hand-editing.
"""

import os

from PIL import Image, ImageDraw, ImageFont

CARDINAL_RED = (196, 30, 58)
CARDINAL_NAVY = (12, 35, 64)
WHITE = (255, 255, 255)
YELLOW = (255, 223, 0)

# Supersample factor for anti-aliased text (matches aa_text.py)
SCALE = 4
TTF_CANDIDATES = (
    './fonts/DejaVuSans-Bold.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
)


def draw_word_aa(img, word, center_x, top, color, size):
    """Paste word rendered at SCALE-times size and LANCZOS-downsampled,
    horizontally centered on center_x - soft edges instead of pixel art"""
    ttf = next(p for p in TTF_CANDIDATES if os.path.exists(p))
    font = ImageFont.truetype(ttf, size * SCALE)
    ascent, descent = font.getmetrics()
    width_4x = max(1, int(font.getlength(word)))
    big = Image.new('L', (width_4x, ascent + descent), 0)
    ImageDraw.Draw(big).text((0, 0), word, font=font, fill=255)
    mask = big.resize(
        (max(1, round(width_4x / SCALE)),
         max(1, round((ascent + descent) / SCALE))),
        Image.LANCZOS)
    fg = Image.new('RGBA', mask.size, color + (255,))
    img.paste(fg, (center_x - mask.width // 2, top), mask)


def make_marquee():
    """96x35 marquee sign: navy field, red sign face, bulb border"""
    img = Image.new('RGBA', (96, 35), CARDINAL_NAVY + (255,))
    d = ImageDraw.Draw(img)
    # Sign face
    d.rectangle([4, 4, 91, 30], fill=CARDINAL_RED)
    d.rectangle([4, 4, 91, 30], outline=WHITE)
    # Bulbs around the border (every 4th pixel)
    for x in range(6, 90, 4):
        d.point((x, 2), fill=YELLOW)
        d.point((x, 32), fill=YELLOW)
    for y in range(6, 30, 4):
        d.point((2, y), fill=YELLOW)
        d.point((93, y), fill=YELLOW)
    # "ST LOUIS" over "CARDINALS", centered on the sign face
    draw_word_aa(img, 'ST LOUIS', 48, 7, WHITE, 8)
    draw_word_aa(img, 'CARDINALS', 48, 15, WHITE, 12)
    img.save('cardinals_marquee.png')


def make_celebration():
    """96x48 fireworks over the Gateway Arch (12 frames, seamless loop)"""
    import math
    import random

    NIGHT_TOP = (4, 6, 20)
    NIGHT_BOTTOM = (16, 20, 44)
    GROUND = (24, 26, 34)
    ARCH_LIT = (226, 233, 246)     # inner face, catching the burst light
    ARCH_STEEL = (170, 178, 196)   # mid stainless
    ARCH_EDGE = (94, 101, 118)     # outer rim, away from the light
    # Kept inside the arch opening, which is only ~22px across at y=19 and
    # ~29px at y=30 -- bursts centred much off 48 disappear behind a leg.
    BURSTS = [
        {'cx': 43, 'cy': 24, 'start': 0, 'color': (235, 60, 85)},   # red
        {'cx': 54, 'cy': 20, 'start': 4, 'color': (255, 205, 90)},  # gold
        {'cx': 48, 'cy': 30, 'start': 8, 'color': (255, 255, 255)},  # white
    ]
    FRAME_COUNT = 12
    LIFE = 12  # phases wrap the full loop so the animation cycles seamlessly

    def sky():
        img = Image.new('RGB', (96, 48))
        px = img.load()
        for y in range(48):
            t = y / 47
            px_row = tuple(
                int(a + (b - a) * t) for a, b in zip(NIGHT_TOP, NIGHT_BOTTOM))
            for x in range(96):
                px[x, y] = px_row
        for y in range(45, 48):
            for x in range(96):
                px[x, y] = GROUND
        star_rng = random.Random(64)  # static stars, same every frame
        for _ in range(18):
            px[star_rng.randrange(96), star_rng.randrange(3, 26)] = (
                140, 145, 165)
        return img

    def scale(color, f):
        return tuple(int(c * f) for c in color)

    def put(px, x, y, color):
        if 0 <= x < 96 and 0 <= y < 45:
            px[x, y] = color

    def draw_burst(px, burst, phase, rng):
        cx, cy, color = burst['cx'], burst['cy'], burst['color']
        if phase <= 2:  # rocket rising from the ground with a dim trail
            ry = 44 - int((44 - cy) * (phase + 1) / 3)
            put(px, cx, ry, (255, 240, 200))
            put(px, cx, ry + 2, scale((255, 240, 200), 0.4))
        elif phase <= 6:  # expanding shell of radial particles
            r = 2 + 2.5 * (phase - 3)
            for j in range(14):
                angle = j * math.tau / 14 + rng.uniform(-0.1, 0.1)
                x = cx + int(round(r * math.cos(angle)))
                y = cy + int(round(r * 0.85 * math.sin(angle)))
                put(px, x, y, color)
                if phase >= 5:  # trailing inner ring as the shell expands
                    x2 = cx + int(round((r - 2.5) * math.cos(angle)))
                    y2 = cy + int(round((r - 2.5) * 0.85 * math.sin(angle)))
                    put(px, x2, y2, scale(color, 0.45))
        elif phase <= 9:  # sparkles drifting down and fading out
            r = 2 + 2.5 * 3
            fade = {7: 0.6, 8: 0.35, 9: 0.18}[phase]
            for j in range(14):
                if rng.random() < 0.65:
                    angle = j * math.tau / 14
                    x = cx + int(round(r * math.cos(angle)))
                    y = cy + int(round(r * 0.85 * math.sin(angle)))
                    put(px, x + rng.choice((-1, 0, 1)),
                        y + (phase - 6), scale(color, fade))
        # phases 10-11: dark, ready to relaunch

    def draw_arch(img):
        """Solid Arch: the region between an outer and an inner weighted
        catenary, which is how the real one is shaped. Filling between two
        curves puts the thickness perpendicular to the curve, so the legs come
        out wide and the crown stays narrow. Stamping a fixed number of pixels
        downward from a single centreline instead adds length rather than width
        wherever the curve is near-vertical, which flattened the legs to a
        hairline and read as two grey lines."""
        px = img.load()
        k = 2.1                      # higher k -> more upright legs
        base_y = 45
        W_OUT, APEX_OUT = 24, 5      # outer edge: 48 wide, 40 tall (~1:1)
        W_IN, APEX_IN = 18, 8        # inner edge -> 6px legs, 3px crown
        cosh_k = math.cosh(k)

        def curve_y(x, half_width, apex_y):
            """Height of the catenary at column x; None outside its span."""
            t = (x - 48) / half_width
            if abs(t) > 1:
                return None
            return base_y - (base_y - apex_y) * (
                cosh_k - math.cosh(k * t)) / (cosh_k - 1)

        def is_steel(x, y):
            outer = curve_y(x, W_OUT, APEX_OUT)
            if outer is None or y < outer or y >= base_y:
                return False
            inner = curve_y(x, W_IN, APEX_IN)
            return inner is None or y < inner

        for x in range(96):
            for y in range(base_y):
                if not is_steel(x, y):
                    continue
                # The real Arch has a triangular cross-section, so each leg
                # shows a lit face and a shadowed one. Step one pixel toward
                # the middle of the opening: leaving the steel there means this
                # is the inner face, which is what the fireworks light up.
                dx, dy = 48 - x, 34 - y
                mag = math.hypot(dx, dy) or 1
                sx, sy = dx / mag, dy / mag
                if not is_steel(round(x + sx), round(y + sy)):
                    color = ARCH_LIT
                elif not is_steel(round(x - sx), round(y - sy)):
                    color = ARCH_EDGE
                else:
                    color = ARCH_STEEL
                px[x, y] = color
        return img

    frames = []
    for frame in range(FRAME_COUNT):
        img = sky()
        px = img.load()
        for index, burst in enumerate(BURSTS):
            phase = (frame - burst['start']) % LIFE
            rng = random.Random((index + 1) * 100 + phase)
            draw_burst(px, burst, phase, rng)
        draw_arch(img)
        frames.append(img)
    frames[0].save('cards_win.gif', save_all=True,
                   append_images=frames[1:], duration=120, loop=0)


if __name__ == '__main__':
    make_marquee()
    make_celebration()
    print('Wrote cardinals_marquee.png and cards_win.gif')

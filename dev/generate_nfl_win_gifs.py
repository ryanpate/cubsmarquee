"""Generate the NFL win celebration GIFs, one per pack in NFL_TEAMS.

Matches the MLB celebration format (96x48, 4 frames, 200ms): sweater
stripes in the pack accent color, the team logo up top, '{TEAM} WIN!'
in a chunky pixel font, and per-frame confetti. Rerunnable; this script
is the source of truth for regenerating the committed GIFs.

Usage (from the repo root): python3 dev/generate_nfl_win_gifs.py
"""

from __future__ import annotations

import random
import sys

from PIL import Image

sys.path.insert(0, '.')

from teams import NFL_TEAMS  # noqa: E402

GLYPHS = {
    'A': ['010', '101', '111', '101', '101'],
    'B': ['110', '101', '110', '101', '110'],
    'C': ['011', '100', '100', '100', '011'],
    'E': ['111', '100', '110', '100', '111'],
    'F': ['111', '100', '110', '100', '100'],
    'H': ['101', '101', '111', '101', '101'],
    'I': ['111', '010', '010', '010', '111'],
    'N': ['101', '111', '111', '111', '101'],
    'O': ['111', '101', '101', '101', '111'],
    'R': ['110', '101', '110', '101', '101'],
    'S': ['011', '100', '010', '001', '110'],
    'W': ['101', '101', '111', '111', '101'],
    'Y': ['101', '101', '010', '010', '010'],
    '!': ['010', '010', '010', '000', '010'],
    ' ': ['000', '000', '000', '000', '000'],
}

WHITE = (255, 255, 255)
SIZE = (96, 48)
FRAMES = 4
DURATION_MS = 200
CONFETTI_PER_FRAME = 40


def draw_text(pixels, text, y, color, scale=2):
    """Center TEXT at row y in the 3x5 glyph font, scaled up"""
    char_w = 4 * scale  # 3px glyph + 1px gap
    x = (SIZE[0] - len(text) * char_w + scale) // 2
    for ch in text:
        rows = GLYPHS[ch]
        for gy, row in enumerate(rows):
            for gx, bit in enumerate(row):
                if bit == '1':
                    for sy in range(scale):
                        for sx in range(scale):
                            px = x + gx * scale + sx
                            py = y + gy * scale + sy
                            if 0 <= px < SIZE[0] and 0 <= py < SIZE[1]:
                                pixels[px, py] = color
        x += char_w


def build_frame(pack, logo, frame_index, rng):
    img = Image.new('RGB', SIZE, pack.primary_color)
    pixels = img.load()

    # Sweater stripes top and bottom
    for y in (0, 1, 46, 47):
        for x in range(SIZE[0]):
            pixels[x, y] = pack.accent_color

    # Confetti in accent/white, repositioned every frame
    for _ in range(CONFETTI_PER_FRAME):
        x = rng.randrange(0, SIZE[0])
        y = rng.randrange(3, 45)
        pixels[x, y] = pack.accent_color if rng.random() < 0.5 else WHITE

    # Team logo centered near the top (source PNGs are 20x20 RGBA)
    logo_x = (SIZE[0] - logo.width) // 2
    img.paste(logo, (logo_x, 4), logo)

    # '{TEAM} WIN!' alternating white/accent for a flash effect
    text_color = WHITE if frame_index % 2 == 0 else pack.accent_color
    draw_text(img.load(), f'{pack.short_name.upper()} WIN!', 30, text_color)
    return img


def main() -> None:
    for slug, pack in NFL_TEAMS.items():
        rng = random.Random(2026)  # deterministic output per run
        logo = Image.open(pack.logo_path).convert('RGBA')
        frames = [build_frame(pack, logo, i, rng) for i in range(FRAMES)]
        out_path = pack.celebration_path
        frames[0].save(
            out_path, save_all=True, append_images=frames[1:],
            duration=DURATION_MS, loop=0)
        print(f'{out_path} written ({FRAMES} frames)')


if __name__ == '__main__':
    main()

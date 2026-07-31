#!/usr/bin/env python3
"""Generate 20x20 pixel-art airline logos into logos/airlines/.

Two source formats:
  - PIXEL_LOGOS: hand-drawn 20x20 pixel maps (palette char -> RGB)
  - LETTER_BADGES: rounded brand-color square + 2-letter IATA code
    rendered with the repo's 5x8 BDF font

Also writes flight_previews/logo_sheet.png, an 8x contact sheet for
visual review. Usage (from repo root): python3 tools/gen_airline_logos.py
"""
from __future__ import annotations

import os

from PIL import BdfFontFile, Image, ImageDraw, ImageFont

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO_ROOT)
OUT_DIR = os.path.join(REPO_ROOT, 'logos', 'airlines')
SHEET_DIR = os.path.join(REPO_ROOT, 'flight_previews')
PIL_FONT_DIR = '/var/tmp/pil_fonts'

# --- Hand-drawn pixel maps (20 rows x 20 chars, '.' = black) -------------

PIXEL_LOGOS = {
    # Delta: two-tone red widget
    'dal': ({'r': (224, 30, 55), 'd': (150, 12, 35)}, [
        "....................",
        "....................",
        ".........rd.........",
        ".........rd.........",
        "........rrdd........",
        "........rrdd........",
        ".......rrrddd.......",
        ".......rrrddd.......",
        "......rrrrdddd......",
        "......rrrrdddd......",
        ".....rrrrrddddd.....",
        ".....rrrrrddddd.....",
        "....rrrrrrdddddd....",
        "....rrrrrrdddddd....",
        "...rrrrrrrddddddd...",
        "...rrrrrrrddddddd...",
        "..rrrrrrrrdddddddd..",
        "..rrrrrrrrdddddddd..",
        "....................",
        "....................",
    ]),
    # Southwest: tricolor striped heart on navy
    'swa': ({'n': (23, 26, 74), 'r': (224, 36, 48),
             'o': (255, 140, 40), 'y': (255, 191, 32)}, [
        "nnnnnnnnnnnnnnnnnnnn",
        "nnnnnnnnnnnnnnnnnnnn",
        "nnnnrrrrnnnnrrrrnnnn",
        "nnnrrrrrrnnrrrrrrnnn",
        "nnrrrrrrrrrrrrrrrrnn",
        "nnrrrrrrrrrrrrrrrrnn",
        "nnrrrrrrrrrrrrrrrrnn",
        "nnoooooooooooooooonn",
        "nnnooooooooooooooonn",
        "nnnoooooooooooooonnn",
        "nnnnoooooooooooonnnn",
        "nnnnyyyyyyyyyyyynnnn",
        "nnnnnyyyyyyyyyynnnnn",
        "nnnnnnyyyyyyyynnnnnn",
        "nnnnnnnyyyyyynnnnnnn",
        "nnnnnnnnyyyynnnnnnnn",
        "nnnnnnnnnyynnnnnnnnn",
        "nnnnnnnnnnnnnnnnnnnn",
        "nnnnnnnnnnnnnnnnnnnn",
        "nnnnnnnnnnnnnnnnnnnn",
    ]),
    # UPS: brown shield with gold chevron
    'ups': ({'b': (53, 28, 16), 'g': (255, 183, 27)}, [
        "....................",
        "..bbbbbbbbbbbbbbbb..",
        ".bbggggggggggggggbb.",
        ".bbggggggggggggggbb.",
        ".bbbbbbbbbbbbbbbbbb.",
        ".bbbbbbbbbbbbbbbbbb.",
        ".bbbbbbbbbbbbbbbbbb.",
        ".bbbbbbbbbbbbbbbbbb.",
        "..bbbbbbbbbbbbbbbb..",
        "..bbbbbbbbbbbbbbbb..",
        "...bbbbbbbbbbbbbb...",
        "...bbbbbbbbbbbbbb...",
        "....bbbbbbbbbbbb....",
        ".....bbbbbbbbbb.....",
        "......bbbbbbbb......",
        ".......bbbbbb.......",
        "........bbbb........",
        ".........bb.........",
        "....................",
        "....................",
    ]),
}

# --- Letter badges: (text, bg, per-char fg colors) -----------------------

# Curated assets not regenerated here (edit the PNG directly):
#   aal.png — AA flight-symbol mark, downscaled from a 48px icon
#   ual.png — United globe mark, downscaled from a 48px icon
#   asa.png — Alaska Eskimo mark, from a pre-sized 20px vector export

LETTER_BADGES = {
    'jbu': ('jB', (0, 32, 91), [(255, 255, 255), (255, 255, 255)]),
    'nks': ('NK', (255, 236, 0), [(20, 20, 20), (20, 20, 20)]),
    'fft': ('F9', (0, 105, 62), [(255, 255, 255), (255, 255, 255)]),
    'skw': ('OO', (0, 59, 113), [(255, 255, 255), (255, 255, 255)]),
    'rpa': ('YX', (65, 75, 90), [(255, 255, 255), (255, 255, 255)]),
    'eny': ('MQ', (16, 24, 48), [(224, 36, 48), (54, 116, 222)]),
    'fdx': ('Fx', (77, 20, 140), [(255, 255, 255), (255, 102, 0)]),
}


def _pil_font(bdf_path: str):
    os.makedirs(PIL_FONT_DIR, exist_ok=True)
    base = os.path.join(
        PIL_FONT_DIR, os.path.splitext(os.path.basename(bdf_path))[0])
    if not os.path.exists(base + '.pil'):
        with open(bdf_path, 'rb') as fp:
            BdfFontFile.BdfFontFile(fp).save(base)
    return ImageFont.load(base + '.pil')


def from_pixel_map(palette: dict, rows: list[str]) -> Image.Image:
    img = Image.new('RGB', (20, 20), (0, 0, 0))
    px = img.load()
    assert len(rows) == 20, f'need 20 rows, got {len(rows)}'
    for y, row in enumerate(rows):
        assert len(row) == 20, f'row {y} is {len(row)} chars, need 20'
        for x, ch in enumerate(row):
            if ch != '.':
                px[x, y] = palette[ch]
    return img


def letter_badge(text: str, bg, fgs) -> Image.Image:
    img = Image.new('RGB', (20, 20), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        draw.rounded_rectangle((0, 0, 19, 19), radius=5, fill=bg)
    except AttributeError:  # Pillow < 8.2
        draw.rectangle((0, 0, 19, 19), fill=bg)
    font = _pil_font('./fonts/5x8.bdf')
    x = (20 - 5 * len(text)) // 2
    for ch, fg in zip(text, fgs):
        draw.text((x, 6), ch, font=font, fill=fg)
        x += 5
    return img


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    logos: dict[str, Image.Image] = {}
    for name, (palette, rows) in PIXEL_LOGOS.items():
        logos[name] = from_pixel_map(palette, rows)
    for name, (text, bg, fgs) in LETTER_BADGES.items():
        logos[name] = letter_badge(text, bg, fgs)

    for name, img in sorted(logos.items()):
        img.save(os.path.join(OUT_DIR, f'{name}.png'))
        print(f'  wrote {name}.png')

    # 8x contact sheet for visual review
    os.makedirs(SHEET_DIR, exist_ok=True)
    names = sorted(logos)
    sheet = Image.new('RGB', (len(names) * 24 * 8, 24 * 8), (30, 30, 30))
    for i, name in enumerate(names):
        big = logos[name].resize((160, 160), Image.NEAREST)
        sheet.paste(big, (i * 24 * 8 + 16, 16))
    sheet.save(os.path.join(SHEET_DIR, 'logo_sheet.png'))
    print(f'Done: {len(logos)} logos + logo_sheet.png')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Render every holiday facts screen to PNG for review.

Runs headless: rgbmatrix is mocked exactly like tests/conftest.py, and
frames are captured from ScoreboardManager's PIL preview mirror.

Usage (from repo root): python3 tools/render_holiday_previews.py
Output: holiday_previews/<slug>_card.png and <slug>_band.png, 8x
nearest-neighbor upscales of each, and contact_sheet.png of all 36.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)  # code uses relative ./fonts and ./holidays paths

sys.modules['rgbmatrix'] = MagicMock()
sys.modules['rgbmatrix.graphics'] = MagicMock()

from PIL import Image, ImageDraw  # noqa: E402

OUT_DIR = os.path.join(REPO_ROOT, 'holiday_previews')
TICK = 3.3  # a moment with every effect mid-flight
SHEET_SCALE = 4
SHEET_GAP = 8


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    import holiday_display as hd
    from scoreboard_manager import ScoreboardManager

    manager = ScoreboardManager()
    display = hd.HolidayDisplay(manager)
    frames: list[tuple[str, Image.Image, Image.Image]] = []
    for holiday in hd.HOLIDAYS:
        display.draw_card(holiday, TICK)
        card = manager.get_frame_copy()
        display.draw_band(holiday, TICK, display.facts[holiday.slug][0], 6)
        band = manager.get_frame_copy()
        for name, frame in (('card', card), ('band', band)):
            frame.save(os.path.join(OUT_DIR, f'{holiday.slug}_{name}.png'))
            frame.resize((96 * 8, 48 * 8), Image.NEAREST).save(
                os.path.join(OUT_DIR, f'{holiday.slug}_{name}@8x.png'))
        frames.append((holiday.slug, card, band))
        print(f'  wrote {holiday.slug}')

    # Contact sheet: one row per holiday, card on the left, band on the right
    cell_w, cell_h = 96 * SHEET_SCALE, 48 * SHEET_SCALE
    label_w = 110
    sheet = Image.new(
        'RGB',
        (label_w + 2 * (cell_w + SHEET_GAP) + SHEET_GAP,
         len(frames) * (cell_h + SHEET_GAP) + SHEET_GAP), (40, 40, 46))
    pen = ImageDraw.Draw(sheet)
    for row, (slug, card, band) in enumerate(frames):
        y = SHEET_GAP + row * (cell_h + SHEET_GAP)
        pen.text((SHEET_GAP, y + cell_h // 2 - 5), slug, fill=(235, 235, 235))
        for col, frame in enumerate((card, band)):
            sheet.paste(frame.resize((cell_w, cell_h), Image.NEAREST),
                        (label_w + SHEET_GAP + col * (cell_w + SHEET_GAP), y))
    sheet.save(os.path.join(OUT_DIR, 'contact_sheet.png'))
    print(f'Done. Previews in {OUT_DIR}')


if __name__ == '__main__':
    main()

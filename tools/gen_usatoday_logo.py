"""Generate usatoday.png: blue circle + USA TODAY wordmark, 14px tall.

Supersample 8x then LANCZOS-downscale, same pipeline as the airline
logos. Run from the repo root: python3 tools/gen_usatoday_logo.py
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

SS = 8                      # supersample factor
HEIGHT = 14                 # final logo height on the matrix
BLUE = (0, 155, 255, 255)   # USA Today brand circle
NAVY = (20, 40, 80, 255)    # wordmark
FONT_PATH = 'fonts/DejaVuSans-Bold.ttf'


def main() -> None:
    h = HEIGHT * SS
    font = ImageFont.truetype(FONT_PATH, int(h * 0.86))
    text = 'USA TODAY'
    text_w = int(font.getlength(text))
    gap = 3 * SS
    w = h + gap + text_w  # circle diameter == full height

    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((0, 0, h - 1, h - 1), fill=BLUE)
    ascent, descent = font.getmetrics()
    draw.text((h + gap, (h - ascent - descent) // 2), text, font=font, fill=NAVY)

    final_w = round(w * HEIGHT / h)
    small = img.resize((final_w, HEIGHT), Image.LANCZOS)
    if small.width > 88:
        small = small.resize((88, HEIGHT), Image.LANCZOS)
    small.save('usatoday.png')
    print(f'wrote usatoday.png ({small.width}x{small.height})')


if __name__ == '__main__':
    main()

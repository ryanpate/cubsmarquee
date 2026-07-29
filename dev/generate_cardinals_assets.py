"""Generate Cardinals marquee and win-celebration assets.

Run from the repo root:  python3 dev/generate_cardinals_assets.py
Pixel art is expected to be iterated on against the real matrix; keep this
script as the source of truth and regenerate rather than hand-editing.
"""

from PIL import Image, ImageDraw

CARDINAL_RED = (196, 30, 58)
CARDINAL_NAVY = (12, 35, 64)
WHITE = (255, 255, 255)
YELLOW = (255, 223, 0)

# 3x5 pixel font for the letters we need (1 = lit pixel)
GLYPHS = {
    'A': ['010', '101', '111', '101', '101'],
    'C': ['011', '100', '100', '100', '011'],
    'D': ['110', '101', '101', '101', '110'],
    'I': ['111', '010', '010', '010', '111'],
    'L': ['100', '100', '100', '100', '111'],
    'N': ['101', '111', '111', '111', '101'],
    'O': ['010', '101', '101', '101', '010'],
    'R': ['110', '101', '110', '101', '101'],
    'S': ['011', '100', '010', '001', '110'],
    'T': ['111', '010', '010', '010', '010'],
    'U': ['101', '101', '101', '101', '111'],
    'W': ['101', '101', '111', '111', '101'],
    '!': ['010', '010', '010', '000', '010'],
    ' ': ['000', '000', '000', '000', '000'],
}


def draw_word(draw, word, x, y, color, scale=1):
    for ch in word:
        glyph = GLYPHS[ch]
        for row, bits in enumerate(glyph):
            for col, bit in enumerate(bits):
                if bit == '1':
                    x0 = x + col * scale
                    y0 = y + row * scale
                    draw.rectangle(
                        [x0, y0, x0 + scale - 1, y0 + scale - 1], fill=color)
        x += (3 + 1) * scale
    return x


def word_width(word, scale=1):
    return (len(word) * 4 - 1) * scale


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
    top = 'ST LOUIS'
    bottom = 'CARDINALS'
    d_top_x = (96 - word_width(top)) // 2
    d_bot_x = (96 - word_width(bottom, 2)) // 2
    draw_word(d, top, d_top_x, 8, WHITE)
    draw_word(d, bottom, d_bot_x, 16, WHITE, scale=2)
    img.save('cardinals_marquee.png')


def make_celebration():
    """96x48 animated 'CARDS WIN!' with chasing border bulbs"""
    frames = []
    for phase in range(4):
        img = Image.new('RGB', (96, 48), CARDINAL_RED)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, 95, 47], outline=CARDINAL_NAVY)
        # Chasing bulbs: lit position rotates with the frame phase
        idx = 0
        for x in range(2, 94, 4):
            for y in (2, 45):
                d.point((x, y),
                        fill=YELLOW if idx % 4 == phase else CARDINAL_NAVY)
                idx += 1
        for y in range(6, 42, 4):
            for x in (2, 93):
                d.point((x, y),
                        fill=YELLOW if idx % 4 == phase else CARDINAL_NAVY)
                idx += 1
        cards = 'CARDS'
        win = 'WIN!'
        draw_word(d, cards, (96 - word_width(cards, 3)) // 2, 6, WHITE, 3)
        color = YELLOW if phase % 2 else WHITE
        draw_word(d, win, (96 - word_width(win, 3)) // 2, 26, color, 3)
        frames.append(img)
    frames[0].save('cards_win.gif', save_all=True,
                   append_images=frames[1:], duration=200, loop=0)


if __name__ == '__main__':
    make_marquee()
    make_celebration()
    print('Wrote cardinals_marquee.png and cards_win.gif')

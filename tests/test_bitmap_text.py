"""Text headed for a bitmap font must survive PIL's latin-1 encoder.

RSS headlines (and anything typed into the admin custom message) arrive with
smart quotes and en/em dashes. PIL's bitmap fonts encode to latin-1, so
drawing one raised UnicodeEncodeError every frame, which stalled the USA
Today ticker on a single frame and flooded the error log (2026-08-16).
"""

from __future__ import annotations

import os
import tempfile

import pytest
from PIL import BdfFontFile, ImageDraw, ImageFont, Image

from scoreboard_config import Fonts


def _pil_font():
    """The same PIL bitmap font draw_text mirrors the canvas with."""
    with tempfile.TemporaryDirectory() as tmp:
        base = os.path.join(tmp, 'large_bold')
        with open(Fonts.LARGE_BOLD, 'rb') as fp:
            BdfFontFile.BdfFontFile(fp).save(base)
        return ImageFont.load(base + '.pil')


def _draw(text: str) -> None:
    img = Image.new('RGB', (96, 48))
    ImageDraw.Draw(img).text((0, 0), text, font=_pil_font(), fill=(255, 255, 255))


class TestToBitmapText:
    def test_curly_quotes_become_straight(self) -> None:
        from scoreboard_manager import to_bitmap_text

        assert to_bitmap_text('IT’S THE “BEST”') == 'IT\'S THE "BEST"'

    def test_dashes_and_ellipsis_become_ascii(self) -> None:
        from scoreboard_manager import to_bitmap_text

        assert to_bitmap_text('A–B—C…') == 'A-B-C.'

    def test_unknown_high_codepoints_become_a_placeholder(self) -> None:
        from scoreboard_manager import to_bitmap_text

        assert to_bitmap_text('WIN \U0001f600') == 'WIN ?'

    def test_ascii_and_latin1_pass_through(self) -> None:
        from scoreboard_manager import to_bitmap_text

        assert to_bitmap_text('CUBS 5, CARDS 3 \xb0F') == 'CUBS 5, CARDS 3 \xb0F'

    def test_length_is_preserved(self) -> None:
        """Tickers position each character at index * char_width, so a
        substitution that changed length would shift the scroll mid-string."""
        from scoreboard_manager import to_bitmap_text

        headline = 'TRUMP’S “PLAN” — SOURCES SAY…'
        assert len(to_bitmap_text(headline)) == len(headline)


class TestPilCanRenderTheResult:
    def test_raw_smart_quote_is_what_broke(self) -> None:
        with pytest.raises(UnicodeEncodeError):
            _draw('TRUMP’S PLAN')

    def test_converted_text_renders(self) -> None:
        from scoreboard_manager import to_bitmap_text

        _draw(to_bitmap_text('TRUMP’S “PLAN” — SAY…'))

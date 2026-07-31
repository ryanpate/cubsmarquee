"""Anti-aliased TTF text rendering for the flight screens"""

from __future__ import annotations

import os
from unittest.mock import Mock


class TestConfig:
    def test_bundled_ttf_and_constants(self) -> None:
        from scoreboard_config import Fonts

        assert Fonts.AA_TEXT_SIZE == 9
        assert Fonts.AA_TTF_CANDIDATES[0] == './fonts/DejaVuSans-Bold.ttf'
        assert os.path.exists(Fonts.AA_TTF_CANDIDATES[0])


class TestAATextRenderer:
    def _renderer(self, size: int = 9):
        from aa_text import AATextRenderer, find_ttf
        from scoreboard_config import Fonts

        path = find_ttf(Fonts.AA_TTF_CANDIDATES)
        assert path is not None  # Task 1 bundled the font
        return AATextRenderer(path, size)

    def test_find_ttf_returns_none_when_nothing_exists(self) -> None:
        from aa_text import find_ttf

        assert find_ttf(['/nope/a.ttf', '/nope/b.ttf']) is None

    def test_render_is_grayscale_at_1x_scale(self) -> None:
        r = self._renderer(size=9)
        img = r.render('United')

        assert img.mode == 'L'
        # 1x scale: a 9pt string is around 9-12px tall, nowhere near 4x
        assert 6 <= img.height <= 14
        assert img.width >= 20
        assert 0 < r.ascent <= img.height

    def test_render_is_antialiased(self) -> None:
        img = self._renderer().render('United')

        levels = set(img.getdata())
        # Hard bitmap text has 2 levels; AA produces many intermediates
        assert len(levels) > 10

    def test_render_caches_per_string(self) -> None:
        r = self._renderer()

        assert r.render('ORD-LAX') is r.render('ORD-LAX')

    def test_measure_matches_render_width(self) -> None:
        r = self._renderer()

        assert r.measure('A321neo') == r.render('A321neo').width
        assert r.measure('Los Angeles') > r.measure('LA')

    def test_fit_trims_to_width(self) -> None:
        r = self._renderer()
        fitted = r.fit('International Heavy Cargo', 68)

        assert r.measure(fitted) <= 68
        assert 0 < len(fitted) < len('International Heavy Cargo')
        assert 'International Heavy Cargo'.startswith(fitted.rstrip())

    def test_fit_keeps_short_text_unchanged(self) -> None:
        r = self._renderer()

        assert r.fit('United', 68) == 'United'

    def test_fit_zero_width_returns_empty(self) -> None:
        assert self._renderer().fit('United', 0) == ''

    def test_cache_is_bounded(self) -> None:
        from aa_text import CACHE_MAX

        r = self._renderer()
        for i in range(CACHE_MAX + 10):
            r.render(str(i))

        assert len(r._cache) <= CACHE_MAX


def _manager(ttf: str | None):
    """ScoreboardManager with only the AA-path attributes populated"""
    from scoreboard_manager import ScoreboardManager

    m = ScoreboardManager.__new__(ScoreboardManager)
    m._aa_ttf = ttf
    m._aa_renderers = {}
    m._aa_warned = False
    m.draw_text = Mock()
    m.draw_pixel = Mock()
    return m


def _real_ttf() -> str:
    from aa_text import find_ttf
    from scoreboard_config import Fonts

    path = find_ttf(Fonts.AA_TTF_CANDIDATES)
    assert path is not None
    return path


class TestManagerAAText:
    def test_draw_falls_back_to_bitmap_without_ttf(self) -> None:
        m = _manager(ttf=None)
        m.draw_text_aa(26, 9, (255, 255, 255), 'United')

        m.draw_text.assert_called_once_with(
            'small', 26, 9, (255, 255, 255), 'United')
        m.draw_pixel.assert_not_called()

    def test_measure_and_fit_fall_back_without_ttf(self) -> None:
        m = _manager(ttf=None)

        assert m.measure_text_aa('United') == 6 * 6  # CHAR_WIDTH_SMALL
        assert m.fit_text_aa('United Airlines', 68) == 'United Airl'  # 68//6

    def test_draw_writes_alpha_scaled_pixels_in_bounds(self) -> None:
        m = _manager(ttf=_real_ttf())
        m.draw_text_aa(80, 9, (200, 100, 50), 'United')  # spills past x=95

        m.draw_text.assert_not_called()
        assert m.draw_pixel.called
        for call in m.draw_pixel.call_args_list:
            x, y, r, g, b = call.args
            assert 0 <= x < 96 and 0 <= y < 48   # clipped to canvas
            assert 0 < r <= 200 and g <= 100 and b <= 50  # alpha-scaled

    def test_measure_uses_renderer_and_caches_it(self) -> None:
        from aa_text import AATextRenderer

        m = _manager(ttf=_real_ttf())
        w = m.measure_text_aa('ORD-LAX')

        assert w > 0
        assert isinstance(m._aa_renderers[9], AATextRenderer)
        assert m.fit_text_aa('United', 500) == 'United'

"""Anti-aliased TTF text rendering for the flight screens"""

from __future__ import annotations

import os


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

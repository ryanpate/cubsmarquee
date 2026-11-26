"""Holiday facts screen: calendar, facts, art, display and rotation"""

from __future__ import annotations

from datetime import date

import pytest

import holiday_display as hd


class TestCalendar:
    def test_easter_dates(self) -> None:
        assert hd.easter_date(2026) == date(2026, 4, 5)
        assert hd.easter_date(2027) == date(2027, 3, 28)
        assert hd.easter_date(2028) == date(2028, 4, 16)

    @pytest.mark.parametrize('day, slug', [
        (date(2026, 11, 26), 'thanksgiving'),
        (date(2027, 11, 25), 'thanksgiving'),
        (date(2027, 5, 9), 'mothers_day'),
        (date(2027, 6, 20), 'fathers_day'),
        (date(2027, 3, 21), 'palm_sunday'),
        (date(2027, 3, 26), 'good_friday'),
        (date(2026, 12, 24), 'christmas_eve'),
        (date(2026, 12, 25), 'christmas'),
        (date(2026, 12, 31), 'new_years_eve'),
        (date(2027, 1, 1), 'new_years_day'),
    ])
    def test_holiday_on(self, day: date, slug: str) -> None:
        assert hd.holiday_on(day).slug == slug

    def test_ordinary_day_is_none(self) -> None:
        assert hd.holiday_on(date(2026, 11, 27)) is None

    def test_christian_day_wins_a_clash(self) -> None:
        # Easter fell on April Fools' Day, Good Friday on Earth Day
        assert hd.holiday_on(date(2029, 4, 1)).slug == 'easter'
        assert hd.holiday_on(date(2011, 4, 22)).slug == 'good_friday'

    def test_table_is_complete(self) -> None:
        assert len(hd.HOLIDAYS) == 18
        assert len(hd.HOLIDAYS_BY_SLUG) == 18
        for holiday in hd.HOLIDAYS:
            assert holiday.effect in hd.EFFECTS
            assert holiday.card_text and holiday.band_text
        assert hd.HOLIDAYS_BY_SLUG['good_friday'].effect == 'none'
        assert hd.HOLIDAYS_BY_SLUG['palm_sunday'].effect == 'none'


class TestFacts:
    def test_every_holiday_has_facts(self) -> None:
        facts = hd.load_holiday_facts()
        assert set(facts) == {h.slug for h in hd.HOLIDAYS}
        for holiday in hd.HOLIDAYS:
            deck = facts[holiday.slug]
            assert len(deck) >= 15, holiday.slug
            assert len(set(deck)) == len(deck), holiday.slug
            for fact in deck:
                assert fact == fact.upper() and fact.isascii(), fact
                assert 0 < len(fact) <= 100, f'{len(fact)}: {fact}'

    def test_good_friday_facts_are_plain_statements(self) -> None:
        assert not any('!' in f for f in hd.load_holiday_facts()['good_friday'])

    def test_no_facts_file_gives_empty_decks(self, monkeypatch, tmp_path) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(hd, 'data_path_candidates',
                            lambda name: [str(tmp_path / name)])
        assert hd.load_holiday_facts() == {}


class TestArt:
    @pytest.mark.parametrize('slug', [h.slug for h in hd.HOLIDAYS])
    def test_art_exists_at_exact_size(self, slug: str) -> None:
        from PIL import Image
        for suffix, size in (('card', (96, 48)), ('band', (96, 30))):
            with Image.open(f'{hd.ART_DIR}/{slug}_{suffix}.png') as im:
                assert im.size == size and im.mode == 'RGB'

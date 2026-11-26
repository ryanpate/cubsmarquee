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


def _pixels(manager) -> list[tuple]:
    return [call.args for call in manager.draw_pixel.call_args_list]


class TestEffects:
    @pytest.mark.parametrize('effect', hd.EFFECTS)
    @pytest.mark.parametrize('tick', [0.0, 3.7, 61.2])
    def test_effects_stay_inside_the_band(self, effect: str, tick: float) -> None:
        from unittest.mock import MagicMock
        manager = MagicMock()
        hd.draw_effect(manager, effect, tick, 30)
        for x, y, r, g, b in _pixels(manager):
            assert 0 <= x < 96 and 0 <= y < 30, (effect, x, y)
            assert all(isinstance(v, int) and 0 <= v <= 255 for v in (r, g, b))

    @pytest.mark.parametrize('effect', [e for e in hd.EFFECTS if e != 'none'])
    def test_effects_draw_something(self, effect: str) -> None:
        from unittest.mock import MagicMock
        drawn = 0
        for tick in (0.5, 1.3, 2.9):
            manager = MagicMock()
            hd.draw_effect(manager, effect, tick, 48)
            drawn += len(_pixels(manager))
        assert drawn > 0

    def test_none_effect_draws_nothing(self) -> None:
        from unittest.mock import MagicMock
        manager = MagicMock()
        hd.draw_effect(manager, 'none', 5.0, 48)
        manager.draw_pixel.assert_not_called()

    @pytest.mark.parametrize('effect', ['twinkle', 'fireworks'])
    def test_sky_effects_stay_behind_the_art(self, effect: str) -> None:
        from unittest.mock import MagicMock
        from PIL import Image
        no_sky = Image.new('L', (96, 48), 0)
        for tick in (0.5, 1.3, 2.9):
            manager = MagicMock()
            hd.draw_effect(manager, effect, tick, 48, sky=no_sky)
            manager.draw_pixel.assert_not_called()


@pytest.fixture
def display(monkeypatch):
    from unittest.mock import MagicMock
    monkeypatch.setattr(hd, 'load_user_config', lambda: {})
    monkeypatch.setattr(hd.time, 'sleep', lambda seconds: None)
    return hd.HolidayDisplay(MagicMock())


class TestDisplay:
    def test_preview_key_forces_a_holiday(self, display, monkeypatch) -> None:
        monkeypatch.setattr(hd, 'load_user_config',
                            lambda: {'holiday_preview': 'halloween'})
        assert display.current_holiday(date(2026, 3, 3)).slug == 'halloween'

    def test_bad_preview_slug_falls_back_to_the_date(
            self, display, monkeypatch) -> None:
        monkeypatch.setattr(hd, 'load_user_config',
                            lambda: {'holiday_preview': 'haloween'})
        assert display.current_holiday(date(2026, 3, 3)) is None
        assert display.current_holiday(date(2026, 12, 25)).slug == 'christmas'

    def test_today_defaults_to_chicago(self, display, monkeypatch) -> None:
        import pendulum
        monkeypatch.setattr(
            hd.pendulum, 'now',
            lambda tz: pendulum.datetime(2026, 12, 25, 23, 30, tz=tz))
        assert display.current_holiday().slug == 'christmas'

    def test_not_a_holiday_returns_false_without_drawing(
            self, display, monkeypatch) -> None:
        monkeypatch.setattr(display, 'current_holiday', lambda: None)
        assert display.display_holiday(1) is False
        display.manager.swap_canvas.assert_not_called()

    def test_missing_facts_returns_false(self, display, monkeypatch) -> None:
        monkeypatch.setattr(display, 'current_holiday',
                            lambda: hd.HOLIDAYS_BY_SLUG['christmas'])
        display.facts = {}
        assert display.display_holiday(1) is False
        display.manager.swap_canvas.assert_not_called()

    def test_missing_art_returns_false(
            self, display, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(hd, 'ART_DIR', str(tmp_path))
        monkeypatch.setattr(display, 'current_holiday',
                            lambda: hd.HOLIDAYS_BY_SLUG['christmas'])
        assert display.display_holiday(1) is False

    def test_shows_card_then_facts(self, display, monkeypatch) -> None:
        monkeypatch.setattr(display, 'current_holiday',
                            lambda: hd.HOLIDAYS_BY_SLUG['christmas'])
        order: list[str] = []
        monkeypatch.setattr(display, 'draw_card',
                            lambda holiday, tick: order.append('card'))
        monkeypatch.setattr(
            display, 'draw_band',
            lambda holiday, tick, fact, scroll_x: order.append('band'))
        monkeypatch.setattr(hd.GameConfig, 'HOLIDAY_CARD_SECONDS', 0.05)
        assert display.display_holiday(0.15) is True
        assert order[0] == 'card' and order[-1] == 'band'
        assert order == sorted(order, key=lambda name: name != 'card')

    def test_deck_follows_the_holiday(self, display, monkeypatch) -> None:
        monkeypatch.setattr(hd.GameConfig, 'HOLIDAY_CARD_SECONDS', 0)
        shown: list[str] = []
        monkeypatch.setattr(
            display, 'draw_band',
            lambda holiday, tick, fact, scroll_x: shown.append(fact))
        for slug in ('new_years_eve', 'new_years_day'):
            shown.clear()
            monkeypatch.setattr(display, 'current_holiday',
                                lambda slug=slug: hd.HOLIDAYS_BY_SLUG[slug])
            assert display.display_holiday(0.05) is True
            assert shown and set(shown) <= set(display.facts[slug]), slug

    def test_pass_ends_after_its_facts(self, display, monkeypatch) -> None:
        import time as real_time
        monkeypatch.setattr(hd.GameConfig, 'HOLIDAY_CARD_SECONDS', 0)
        monkeypatch.setattr(display, 'current_holiday',
                            lambda: hd.HOLIDAYS_BY_SLUG['christmas'])
        shown: list[tuple[str, int]] = []
        monkeypatch.setattr(
            display, 'draw_band',
            lambda holiday, tick, fact, scroll_x: shown.append(
                (fact, scroll_x)))
        started = real_time.time()
        assert display.display_holiday(duration=60, facts=1) is True
        assert real_time.time() - started < 10  # not the full minute
        facts = {fact for fact, _ in shown}
        assert len(facts) == 1
        fact = facts.pop()
        # the one fact scrolled all the way off the left edge
        assert shown[0][1] == 96
        assert shown[-1][1] + len(fact) * 9 <= 0

    def test_deck_wraps_without_repeating_back_to_back(self, display) -> None:
        holiday = hd.HOLIDAYS_BY_SLUG['easter']
        count = len(display.facts['easter'])
        facts = [display._next_fact(holiday) for _ in range(count * 2)]
        assert sorted(facts[:count]) == sorted(display.facts['easter'])
        assert facts[:count] == facts[count:]

    def test_band_draws_fact_at_baseline_45(self, display) -> None:
        holiday = hd.HOLIDAYS_BY_SLUG['christmas']
        display.draw_band(holiday, 2.0, 'A FACT', 40)
        display.manager.draw_text.assert_any_call(
            'medium_bold', 40, 45, hd.CREAM, 'A FACT')
        for line in holiday.band_text:
            display.manager.draw_text.assert_any_call(
                line.font, line.x, line.baseline, line.color, line.text)

    def test_card_draws_the_greeting(self, display) -> None:
        holiday = hd.HOLIDAYS_BY_SLUG['christmas']
        display.draw_card(holiday, 2.0)
        for line in holiday.card_text:
            display.manager.draw_text.assert_any_call(
                line.font, line.x, line.baseline, line.color, line.text)

    @pytest.mark.parametrize('holiday', hd.HOLIDAYS, ids=lambda h: h.slug)
    def test_lettering_fits_the_panel(self, holiday) -> None:
        widths = {'medium_bold': 9, 'small_bold': 6, 'tiny_bold': 5}
        for lines, left, rows in ((holiday.card_text, holiday.card_left, 48),
                                  (holiday.band_text, holiday.band_left, 30)):
            for line in lines:
                assert line.x >= left, line
                assert line.x + len(line.text) * widths[line.font] <= 96, line
                assert line.baseline < rows, line


class TestRotationSlot:
    """On a holiday a short holiday pass follows every screen in
    OffSeasonHandler._display_rotation_cycle"""

    def _handler(self, **config):
        from tests.test_bugfixes import TestRotationInterludeOnlyAfterContent
        helper = TestRotationInterludeOnlyAfterContent()
        return helper._make_handler({**helper._all_off(), **config})

    def test_holiday_pass_follows_every_screen(self) -> None:
        # weather shows twice per pass and the Bible verse once
        handler = self._handler(enable_holiday_facts=True,
                                enable_weather=True, enable_bible=True)
        handler.holiday_display.display_holiday.return_value = True
        handler._display_rotation_cycle()
        assert handler.holiday_display.display_holiday.call_count == 3

    def test_pass_is_a_card_and_one_fact(self) -> None:
        handler = self._handler(enable_holiday_facts=True,
                                enable_weather=True)
        handler.rotation_schedule['holiday_facts'] = 2
        handler._display_rotation_cycle()
        handler.holiday_display.display_holiday.assert_called_with(
            duration=120, facts=1)
        assert hd.GameConfig.HOLIDAY_FACTS_PER_PASS == 1

    def test_holiday_pass_comes_before_the_interlude(self) -> None:
        handler = self._handler(enable_holiday_facts=True,
                                enable_weather=True)
        order: list[str] = []
        handler.holiday_display.display_holiday.side_effect = (
            lambda **kwargs: order.append('holiday') or True)
        handler._display_rotation_cycle(
            between_callback=lambda: order.append('interlude') or True)
        assert order == ['holiday', 'interlude']

    def test_no_pass_of_its_own_between_screens(self) -> None:
        # nothing else showed, so there is nothing to follow
        handler = self._handler(enable_holiday_facts=True)
        ticks: list[int] = []
        handler._display_rotation_cycle(
            between_callback=lambda: ticks.append(1) or False)
        handler.holiday_display.display_holiday.assert_not_called()
        assert ticks == []

    def test_skipped_when_toggle_off(self) -> None:
        handler = self._handler(enable_holiday_facts=False,
                                enable_weather=True)
        handler._display_rotation_cycle()
        handler.holiday_display.display_holiday.assert_not_called()

    def test_toggle_defaults_on(self) -> None:
        handler = self._handler(enable_weather=True)
        del handler.config['enable_holiday_facts']
        handler._display_rotation_cycle()
        assert handler.holiday_display.display_holiday.called

    def test_display_holiday_facts_swallows_errors(self) -> None:
        handler = self._handler(enable_holiday_facts=True)
        handler.holiday_display.display_holiday.side_effect = RuntimeError('x')
        assert handler.display_holiday_facts() is False

    def test_durations(self) -> None:
        assert hd.GameConfig.HOLIDAY_FACTS_DURATION == 2
        assert hd.GameConfig.HOLIDAY_CARD_SECONDS == 8


class TestPreGameLoop:
    """On an in-season holiday the screen joins the next-game loop"""

    def _run(self, monkeypatch, game_type: str, cycle_content: bool):
        from unittest.mock import MagicMock
        from PIL import Image
        import game_state_handler as gsh
        from game_state_handler import GameStateHandler

        monkeypatch.setattr(gsh.time, 'sleep', lambda seconds: None)
        monkeypatch.setattr(gsh, 'retry_api_call', lambda *a, **k: {
            'gameData': {'teams': {
                'home': {'abbreviation': 'CHC', 'name': 'Chicago Cubs'},
                'away': {'abbreviation': 'STL', 'name': 'St. Louis Cardinals'},
            }}})
        handler = GameStateHandler.__new__(GameStateHandler)
        handler.manager = MagicMock()
        handler.manager.split_squad_indicator = None
        handler.manager.format_game_time.return_value = '1:20 PM'
        handler.manager.get_pitchers.return_value = 'PITCHERS'
        handler.manager.game_images = {
            'marquee': Image.new('RGB', (96, 30))}
        handler.manager.get_schedule.return_value = [{'status': 'Warmup'}]
        handler.team = MagicMock(abbrev='CHC', primary_color=(0, 51, 102),
                                 marquee_scroll_baseline=45)
        handler.scroll_position = -100000  # the scroll pass is already over
        handler._display_standings = MagicMock()
        handler._maybe_display_playoff_race = MagicMock()
        handler._display_playoff_info = MagicMock()
        handler.off_season_handler = MagicMock()
        game = [{'game_id': 1, 'game_date': '2027-07-04',
                 'game_type': game_type, 'status': 'Scheduled'}]
        handler.display_no_game(game, 0, cycle_content=cycle_content)
        return handler

    def test_shows_holiday_after_standings(self, monkeypatch) -> None:
        handler = self._run(monkeypatch, 'R', cycle_content=False)
        handler._display_standings.assert_called_once()
        handler.off_season_handler.display_holiday_facts.assert_called_once()

    def test_shows_holiday_in_the_postseason_loop(self, monkeypatch) -> None:
        handler = self._run(monkeypatch, 'D', cycle_content=False)
        handler.off_season_handler.display_holiday_facts.assert_called_once()

    def test_skipped_when_the_rotation_follows(self, monkeypatch) -> None:
        handler = self._run(monkeypatch, 'R', cycle_content=True)
        handler.off_season_handler.display_holiday_facts.assert_not_called()

    def test_skipped_in_spring_training(self, monkeypatch) -> None:
        handler = self._run(monkeypatch, 'S', cycle_content=False)
        handler.off_season_handler.display_holiday_facts.assert_not_called()

    def test_loop_survives_without_an_off_season_handler(
            self, monkeypatch) -> None:
        from game_state_handler import GameStateHandler
        original = GameStateHandler.display_no_game

        def without_handler(self, *args, **kwargs):
            del self.off_season_handler
            return original(self, *args, **kwargs)

        monkeypatch.setattr(GameStateHandler, 'display_no_game',
                            without_handler)
        handler = self._run(monkeypatch, 'R', cycle_content=False)
        handler._display_standings.assert_called_once()


class TestReviewFixes:
    """Findings from the whole-branch review"""

    def test_admin_toggle_applies_without_a_reboot(self, monkeypatch) -> None:
        # The handler's own config copy is only refreshed while the
        # rotation runs, so in season it is as old as the last boot
        import off_season_handler as osh
        handler = TestRotationSlot()._handler(enable_holiday_facts=True)
        monkeypatch.setattr(osh, 'load_user_config',
                            lambda: {'enable_holiday_facts': False})
        assert handler.display_holiday_facts() is False
        handler.holiday_display.display_holiday.assert_not_called()

    @pytest.mark.parametrize('preview', [['christmas'], {'a': 1}, 7])
    def test_non_string_preview_falls_back_to_the_date(
            self, display, monkeypatch, preview) -> None:
        monkeypatch.setattr(hd, 'load_user_config',
                            lambda: {'holiday_preview': preview})
        assert display.current_holiday(date(2026, 12, 25)).slug == 'christmas'

    def test_reviewed_fact_wording(self) -> None:
        facts = hd.load_holiday_facts()
        text = ' '.join(fact for deck in facts.values() for fact in deck)
        # King James wording, not a modern translation
        assert 'BLESSED IS HE THAT COMETH IN THE NAME OF THE LORD' in text
        # Scotland moved to January 1 in 1600; this was England's change
        assert 'ENGLAND AND ITS AMERICAN COLONIES' in text
        assert 'BRITAIN AND ITS AMERICAN COLONIES' not in text
        # looser claims the review flagged
        assert "JULIUS CAESAR'S CALENDAR MADE" not in text
        assert 'NICAEA SET THE RULE' not in text
        assert "A MOTHERS' DAY FOR PEACE BACK IN 1870" not in text

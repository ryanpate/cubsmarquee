"""Tests for auto-dim scheduling and the scoreboard status heartbeat"""

from __future__ import annotations

import json
import time
from unittest.mock import Mock, patch

import pendulum
import pytest


# ============================================================================
# Auto-dim: time window logic
# ============================================================================

class TestDimWindow:
    def _manager(self):
        from scoreboard_manager import ScoreboardManager

        manager = ScoreboardManager.__new__(ScoreboardManager)
        manager.matrix = Mock()
        manager._last_brightness_check = 0.0
        manager._applied_brightness = None
        return manager

    def test_overnight_window_wraps_midnight(self) -> None:
        from scoreboard_manager import ScoreboardManager

        is_dim = ScoreboardManager._is_dim_time
        start, end = 22 * 60, 7 * 60  # 22:00 -> 07:00

        assert is_dim(23 * 60, start, end) is True
        assert is_dim(3 * 60, start, end) is True
        assert is_dim(12 * 60, start, end) is False
        assert is_dim(22 * 60, start, end) is True   # boundary: starts dim
        assert is_dim(7 * 60, start, end) is False   # boundary: ends dim

    def test_same_day_window(self) -> None:
        from scoreboard_manager import ScoreboardManager

        is_dim = ScoreboardManager._is_dim_time
        start, end = 13 * 60, 15 * 60

        assert is_dim(14 * 60, start, end) is True
        assert is_dim(16 * 60, start, end) is False

    def test_equal_start_end_never_dims(self) -> None:
        from scoreboard_manager import ScoreboardManager

        assert ScoreboardManager._is_dim_time(600, 600, 600) is False

    def test_parse_hhmm(self) -> None:
        from scoreboard_manager import ScoreboardManager

        assert ScoreboardManager._parse_hhmm('22:00') == 22 * 60
        assert ScoreboardManager._parse_hhmm('7:30') == 7 * 60 + 30
        with pytest.raises(ValueError):
            ScoreboardManager._parse_hhmm('bedtime')


class TestEffectiveBrightness:
    def _manager(self, config, base=100, now_hour=23):
        import scoreboard_manager as sm

        manager = sm.ScoreboardManager.__new__(sm.ScoreboardManager)
        manager.matrix = Mock()
        manager._last_brightness_check = 0.0
        manager._applied_brightness = None
        manager._load_brightness = Mock(return_value=base)
        self._patches = [
            patch.object(sm, 'load_user_config', return_value=config),
            patch.object(
                sm.pendulum, 'now',
                lambda tz=None: pendulum.datetime(
                    2026, 7, 8, now_hour, 0, tz='America/Chicago'),
            ),
        ]
        for p in self._patches:
            p.start()
        return manager

    def teardown_method(self):
        for p in getattr(self, '_patches', []):
            p.stop()

    DIM_CONFIG = {
        'dim_enabled': True, 'dim_start': '22:00',
        'dim_end': '07:00', 'dim_brightness': 30,
    }

    def test_dim_disabled_returns_base(self) -> None:
        manager = self._manager({}, base=100, now_hour=23)
        assert manager.get_effective_brightness() == 100

    def test_inside_window_returns_dim_value(self) -> None:
        manager = self._manager(self.DIM_CONFIG, base=100, now_hour=23)
        assert manager.get_effective_brightness() == 30

    def test_outside_window_returns_base(self) -> None:
        manager = self._manager(self.DIM_CONFIG, base=100, now_hour=12)
        assert manager.get_effective_brightness() == 100

    def test_dim_never_raises_above_base(self) -> None:
        # Base 20 with dim 30: night must not be brighter than day
        manager = self._manager(self.DIM_CONFIG, base=20, now_hour=23)
        assert manager.get_effective_brightness() == 20

    def test_invalid_dim_time_falls_back_to_base(self) -> None:
        config = dict(self.DIM_CONFIG, dim_start='bedtime')
        manager = self._manager(config, base=100, now_hour=23)
        assert manager.get_effective_brightness() == 100


class TestRuntimeBrightnessApplication:
    def _manager(self):
        from scoreboard_manager import ScoreboardManager

        manager = ScoreboardManager.__new__(ScoreboardManager)
        manager.matrix = Mock()
        manager.canvas = Mock()
        manager._last_brightness_check = 0.0
        manager._applied_brightness = None
        manager._save_preview = Mock()
        manager._refresh_heartbeat = Mock()
        return manager

    def test_update_brightness_sets_matrix(self) -> None:
        manager = self._manager()
        manager.get_effective_brightness = Mock(return_value=40)

        manager.update_brightness()

        assert manager.matrix.brightness == 40

    def test_update_brightness_is_throttled(self) -> None:
        manager = self._manager()
        manager.get_effective_brightness = Mock(return_value=40)

        manager.update_brightness()
        manager.update_brightness()  # immediately again

        assert manager.get_effective_brightness.call_count == 1

    def test_swap_canvas_applies_brightness(self) -> None:
        manager = self._manager()
        manager.update_brightness = Mock()

        manager.swap_canvas()

        manager.update_brightness.assert_called_once()


# ============================================================================
# Auto-dim: admin panel persistence
# ============================================================================

class TestAutoDimAdminConfig:
    def _post_config(self, tmp_path, monkeypatch, payload):
        import wifi_config_server as wcs

        monkeypatch.setattr(wcs, 'CONFIG_PATH', str(tmp_path / 'config.json'))
        client = wcs.app.test_client()
        resp = client.post('/save_config', json=payload)
        assert resp.get_json()['success'] is True
        return json.loads((tmp_path / 'config.json').read_text())

    def test_save_config_persists_dim_settings(
        self, tmp_path, monkeypatch
    ) -> None:
        saved = self._post_config(tmp_path, monkeypatch, {
            'dim_enabled': True, 'dim_start': '21:30',
            'dim_end': '06:00', 'dim_brightness': 25,
        })

        assert saved['dim_enabled'] is True
        assert saved['dim_start'] == '21:30'
        assert saved['dim_end'] == '06:00'
        assert saved['dim_brightness'] == 25

    def test_save_config_sanitizes_bad_dim_values(
        self, tmp_path, monkeypatch
    ) -> None:
        saved = self._post_config(tmp_path, monkeypatch, {
            'dim_enabled': True, 'dim_start': 'bedtime',
            'dim_end': '25:99', 'dim_brightness': 500,
        })

        assert saved['dim_start'] == '22:00'   # default
        assert saved['dim_end'] == '07:00'     # default
        assert saved['dim_brightness'] == 100  # clamped


# ============================================================================
# Countdown milestones: Spring Training then Opening Day
# ============================================================================

class TestCountdownMilestones:
    def _display(self, monkeypatch, frozen, opening='unset'):
        import spring_training_display as std

        monkeypatch.setattr(std.pendulum, 'now', lambda tz=None: frozen)
        display = std.SpringTrainingDisplay.__new__(std.SpringTrainingDisplay)
        display._opening_day_cache = None
        display._opening_day_cached_on = None
        if opening != 'unset':
            display._get_opening_day = Mock(return_value=opening)
        return display

    def test_january_targets_spring_training(self, monkeypatch) -> None:
        frozen = pendulum.datetime(2026, 1, 15, tz='America/Chicago')
        display = self._display(monkeypatch, frozen, opening=None)

        label, target = display._get_countdown_target()

        assert label == 'Spring Training'
        assert (target.year, target.month, target.day) == (2026, 2, 21)

    def test_during_spring_training_targets_opening_day(
        self, monkeypatch
    ) -> None:
        frozen = pendulum.datetime(2026, 3, 1, tz='America/Chicago')
        opening = pendulum.datetime(2026, 3, 26, 13, 20, tz='America/Chicago')
        display = self._display(monkeypatch, frozen, opening=opening)

        label, target = display._get_countdown_target()

        assert label == 'Opening Day'
        assert target == opening

    def test_after_opening_day_targets_next_spring_training(
        self, monkeypatch
    ) -> None:
        frozen = pendulum.datetime(2026, 7, 8, tz='America/Chicago')
        opening = pendulum.datetime(2026, 3, 26, 13, 20, tz='America/Chicago')
        display = self._display(monkeypatch, frozen, opening=opening)

        label, target = display._get_countdown_target()

        assert label == 'Spring Training'
        assert (target.year, target.month, target.day) == (2027, 2, 21)

    def test_api_failure_in_march_estimates_late_march(
        self, monkeypatch
    ) -> None:
        frozen = pendulum.datetime(2026, 3, 1, tz='America/Chicago')
        display = self._display(monkeypatch, frozen, opening=None)

        label, target = display._get_countdown_target()

        assert label == 'Opening Day'
        assert (target.month, target.day) == (3, 26)  # typical opening day

    def test_countdown_message_names_opening_day(self, monkeypatch) -> None:
        frozen = pendulum.datetime(2026, 3, 1, tz='America/Chicago')
        opening = pendulum.datetime(2026, 3, 26, 13, 20, tz='America/Chicago')
        display = self._display(monkeypatch, frozen, opening=opening)

        countdown = display._calculate_countdown()
        message = display._get_countdown_message(countdown)

        assert message == '25 Days till Opening Day'

    def test_get_opening_day_parses_first_regular_game(
        self, monkeypatch
    ) -> None:
        import spring_training_display as std

        frozen = pendulum.datetime(2026, 3, 1, tz='America/Chicago')
        monkeypatch.setattr(std.pendulum, 'now', lambda tz=None: frozen)
        schedule = Mock(return_value=[
            {'game_type': 'S', 'game_datetime': '2026-03-24T20:05:00Z'},
            {'game_type': 'R', 'game_datetime': '2026-03-26T18:20:00Z'},
            {'game_type': 'R', 'game_datetime': '2026-03-28T18:20:00Z'},
        ])
        monkeypatch.setattr(std.statsapi, 'schedule', schedule)

        display = std.SpringTrainingDisplay.__new__(std.SpringTrainingDisplay)
        display._opening_day_cache = None
        display._opening_day_cached_on = None

        opening = display._get_opening_day()

        assert (opening.year, opening.month, opening.day) == (2026, 3, 26)
        # Second call is served from the daily cache
        display._get_opening_day()
        assert schedule.call_count == 1


# ============================================================================
# Playoff race display
# ============================================================================

STANDINGS_FIXTURE = {
    'records': [{
        'teamRecords': [
            {'team': {'id': 158, 'name': 'Milwaukee Brewers'},
             'divisionRank': '1', 'gamesBack': '-',
             'wildCardRank': None, 'wildCardGamesBack': '-',
             'magicNumber': '65', 'wins': 58, 'losses': 34},
            {'team': {'id': 112, 'name': 'Chicago Cubs'},
             'divisionRank': '2', 'gamesBack': '6.0',
             'wildCardRank': '1', 'wildCardGamesBack': '+1.5',
             'magicNumber': None, 'wins': 52, 'losses': 40},
        ],
    }],
}


class TestPlayoffRace:
    def _display(self):
        from playoff_race_display import PlayoffRaceDisplay

        display = PlayoffRaceDisplay.__new__(PlayoffRaceDisplay)
        display.manager = Mock()
        display._race_cache = None
        display._race_cached_at = 0.0
        return display

    def test_parse_extracts_cubs_race(self) -> None:
        display = self._display()

        race = display._parse_race_data(STANDINGS_FIXTURE)

        assert race == {
            'div_rank': 2, 'gb': '6.0', 'wc_rank': 1, 'wc_gb': '+1.5',
            'magic': None, 'wins': 52, 'losses': 40,
            'leader_id': 158,
        }

    def test_parse_returns_none_without_cubs(self) -> None:
        display = self._display()

        assert display._parse_race_data({'records': []}) is None

    def test_format_rows_wildcard_leader(self) -> None:
        display = self._display()
        race = display._parse_race_data(STANDINGS_FIXTURE)

        assert display._format_race_rows(race) == [
            ('NL CENT', '2ND', '6.0'),
            ('WILDCARD', '1ST', '+1.5'),
            ('RECORD', '52-40', ''),
        ]

    def test_format_rows_division_leader_shows_magic_number(self) -> None:
        display = self._display()
        race = {'div_rank': 1, 'gb': '-', 'wc_rank': None, 'wc_gb': '-',
                'magic': '12', 'wins': 90, 'losses': 60, 'leader_id': 112}

        assert display._format_race_rows(race) == [
            ('NL CENT', '1ST', ''),
            ('MAGIC #', '12', ''),
            ('RECORD', '90-60', ''),
        ]

    def test_format_rows_leader_without_magic_number(self) -> None:
        display = self._display()
        race = {'div_rank': 1, 'gb': '-', 'wc_rank': None, 'wc_gb': '-',
                'magic': None, 'wins': 50, 'losses': 40, 'leader_id': 112}

        assert display._format_race_rows(race)[1] == ('MAGIC #', '--', '')

    def test_format_rows_trailing_wildcard(self) -> None:
        display = self._display()
        race = {'div_rank': 3, 'gb': '9.5', 'wc_rank': 4, 'wc_gb': '2.0',
                'magic': None, 'wins': 48, 'losses': 43, 'leader_id': 158}

        rows = display._format_race_rows(race)
        assert rows[1] == ('WILDCARD', '4TH', '2.0')

    def test_format_rows_out_of_wildcard(self) -> None:
        display = self._display()
        race = {'div_rank': 4, 'gb': '12.5', 'wc_rank': None, 'wc_gb': '-',
                'magic': None, 'wins': 44, 'losses': 48, 'leader_id': 158}

        rows = display._format_race_rows(race)
        assert rows[1] == ('WILDCARD', 'OUT', '')

    def test_format_rows_hopeless_wildcard_shows_out(self) -> None:
        display = self._display()
        base = {'div_rank': 4, 'gb': '15.0', 'magic': None,
                'wins': 40, 'losses': 55, 'leader_id': 158}

        # Double-digit deficit reads as OUT (also keeps the row on screen)
        race = dict(base, wc_rank=5, wc_gb='11.0')
        assert display._format_race_rows(race)[1] == ('WILDCARD', 'OUT', '')

        # Double-digit rank reads as OUT
        race = dict(base, wc_rank=10, wc_gb='8.0')
        assert display._format_race_rows(race)[1] == ('WILDCARD', 'OUT', '')

    def test_in_playoff_position(self) -> None:
        display = self._display()

        in_position = display._in_playoff_position
        assert in_position({'div_rank': 1, 'wc_rank': None}) is True
        assert in_position({'div_rank': 2, 'wc_rank': 1}) is True
        assert in_position({'div_rank': 2, 'wc_rank': 3}) is True
        assert in_position({'div_rank': 3, 'wc_rank': 4}) is False
        assert in_position({'div_rank': 4, 'wc_rank': None}) is False

    def test_leader_abbreviation_fetched_once(self, monkeypatch) -> None:
        import playoff_race_display as prd

        display = self._display()
        display._abbr_cache = {}
        get = Mock(return_value={'teams': [{'abbreviation': 'MIL'}]})
        monkeypatch.setattr(prd.statsapi, 'get', get)

        assert display._leader_abbr(158) == 'MIL'
        assert display._leader_abbr(158) == 'MIL'
        assert get.call_count == 1

    def test_leader_abbreviation_none_on_api_failure(self, monkeypatch) -> None:
        import playoff_race_display as prd

        display = self._display()
        display._abbr_cache = {}
        monkeypatch.setattr(
            prd, 'retry_api_call', Mock(side_effect=Exception('down')))

        assert display._leader_abbr(158) is None

    def test_chase_strip_alternates_only_when_chasing(self) -> None:
        display = self._display()

        chasing = {'div_rank': 2, 'wc_rank': 1, 'leader_id': 158}
        leading = {'div_rank': 1, 'wc_rank': None, 'leader_id': 112}

        # Chaser: status strip first, chase strip on the alternate beat
        assert display._chase_strip_visible(chasing, tick=0) is False
        assert display._chase_strip_visible(chasing, tick=5) is True
        assert display._chase_strip_visible(chasing, tick=10) is False

        # Division leader chases no one
        assert display._chase_strip_visible(leading, tick=5) is False

    def test_race_screen_is_short_like_standings(self) -> None:
        import inspect
        from playoff_race_display import PlayoffRaceDisplay
        from scoreboard_config import GameConfig

        default = inspect.signature(
            PlayoffRaceDisplay.display_playoff_race
        ).parameters['duration'].default
        assert default == GameConfig.PLAYOFF_RACE_DISPLAY_TIME
        assert GameConfig.PLAYOFF_RACE_DISPLAY_TIME <= 20

    def test_race_season_gating(self, monkeypatch) -> None:
        import playoff_race_display as prd

        for month, expected in [(5, False), (7, True), (9, True), (11, False)]:
            monkeypatch.setattr(
                prd.pendulum, 'now',
                lambda tz=None, m=month: pendulum.datetime(
                    2026, m, 15, tz='America/Chicago'))
            assert prd.PlayoffRaceDisplay.is_race_season() is expected

    def test_display_skips_when_no_data(self) -> None:
        display = self._display()
        display._get_race_data = Mock(return_value=None)

        display.display_playoff_race(duration=1)

        display.manager.swap_canvas.assert_not_called()


class TestPlayoffRaceInNoGameRotation:
    """The race screen rides along with the next-game/standings cycle"""

    def _handler(self):
        from game_state_handler import GameStateHandler

        handler = GameStateHandler.__new__(GameStateHandler)
        handler.manager = Mock()
        handler.playoff_race = Mock()
        return handler

    def test_shows_race_during_race_season(self, monkeypatch) -> None:
        import game_state_handler as gsh

        monkeypatch.setattr(
            gsh.PlayoffRaceDisplay, 'is_race_season', staticmethod(lambda: True))
        monkeypatch.setattr(gsh, 'load_user_config', lambda: {})
        handler = self._handler()

        handler._maybe_display_playoff_race()

        handler.playoff_race.display_playoff_race.assert_called_once_with()

    def test_skipped_outside_race_season(self, monkeypatch) -> None:
        import game_state_handler as gsh

        monkeypatch.setattr(
            gsh.PlayoffRaceDisplay, 'is_race_season', staticmethod(lambda: False))
        monkeypatch.setattr(gsh, 'load_user_config', lambda: {})
        handler = self._handler()

        handler._maybe_display_playoff_race()

        handler.playoff_race.display_playoff_race.assert_not_called()

    def test_skipped_when_disabled_in_config(self, monkeypatch) -> None:
        import game_state_handler as gsh

        monkeypatch.setattr(
            gsh.PlayoffRaceDisplay, 'is_race_season', staticmethod(lambda: True))
        monkeypatch.setattr(
            gsh, 'load_user_config', lambda: {'enable_playoff_race': False})
        handler = self._handler()

        handler._maybe_display_playoff_race()

        handler.playoff_race.display_playoff_race.assert_not_called()

    def test_race_errors_do_not_break_rotation(self, monkeypatch) -> None:
        import game_state_handler as gsh

        monkeypatch.setattr(
            gsh.PlayoffRaceDisplay, 'is_race_season', staticmethod(lambda: True))
        monkeypatch.setattr(gsh, 'load_user_config', lambda: {})
        handler = self._handler()
        handler.playoff_race.display_playoff_race.side_effect = Exception('api down')

        handler._maybe_display_playoff_race()  # must not raise

    def test_handler_owns_a_playoff_race_display(self) -> None:
        from game_state_handler import GameStateHandler
        from playoff_race_display import PlayoffRaceDisplay

        handler = GameStateHandler(Mock())

        assert isinstance(handler.playoff_race, PlayoffRaceDisplay)

    def test_offseason_rotation_no_longer_owns_the_race_segment(self) -> None:
        import inspect
        import off_season_handler

        source = inspect.getsource(off_season_handler)
        assert 'display_playoff_race' not in source


# ============================================================================
# Last-play scrolling description on the live game screen
# ============================================================================

def _play(description=None, complete=True):
    play = {'about': {'isComplete': complete}}
    if complete:
        play['result'] = {'event': 'Single'}
        if description is not None:
            play['result']['description'] = description
    else:
        play['result'] = {}
    return play


class TestLastPlayDescription:
    def _handler(self):
        from live_game_handler import LiveGameHandler

        handler = LiveGameHandler.__new__(LiveGameHandler)
        handler.manager = Mock()
        return handler

    def test_returns_full_description_unprefixed(self) -> None:
        handler = self._handler()
        description = ('Nico Hoerner singles on a line drive to left fielder '
                       'Ian Happ.   Dansby Swanson scores.')
        play_data = {'allPlays': [_play(description)]}

        assert handler._get_last_play_description(play_data) == description

    def test_skips_in_progress_at_bat(self) -> None:
        handler = self._handler()
        play_data = {'allPlays': [
            _play('Nico Hoerner doubles to deep center field.'),
            _play(complete=False),  # at bat now
        ]}

        assert handler._get_last_play_description(play_data) == \
            'Nico Hoerner doubles to deep center field.'

    def test_no_plays_yet_returns_none(self) -> None:
        handler = self._handler()

        assert handler._get_last_play_description({'allPlays': []}) is None
        assert handler._get_last_play_description({}) is None

    def test_completed_play_without_description_returns_none(self) -> None:
        handler = self._handler()
        play_data = {'allPlays': [_play()]}

        assert handler._get_last_play_description(play_data) is None


class TestGetFrameCopy:
    def test_returns_independent_copy_of_current_frame(self) -> None:
        from PIL import Image
        from scoreboard_manager import ScoreboardManager

        manager = ScoreboardManager.__new__(ScoreboardManager)
        manager._frame = Image.new('RGB', (96, 48), (10, 20, 30))

        copy = manager.get_frame_copy()

        assert copy is not manager._frame
        assert copy.tobytes() == manager._frame.tobytes()

        copy.putpixel((0, 0), (255, 0, 0))
        assert manager._frame.getpixel((0, 0)) == (10, 20, 30)


class TestLastPlayScroll:
    def _handler(self):
        from PIL import Image
        from live_game_handler import LiveGameHandler

        handler = LiveGameHandler.__new__(LiveGameHandler)
        handler.manager = Mock()
        handler.manager.get_frame_copy.return_value = Image.new(
            'RGB', (96, 48))
        handler.manager.split_squad_indicator = False
        handler._last_scrolled_description = None
        return handler

    def test_batter_line_erased_from_scroll_background(
            self, monkeypatch) -> None:
        import live_game_handler as lgh
        from PIL import Image

        monkeypatch.setattr(lgh.time, 'sleep', lambda seconds: None)
        handler = self._handler()
        # Frame with "batter text" (red pixels) on the bottom strip
        frame = Image.new('RGB', (96, 48), (200, 200, 200))
        for x in range(96):
            frame.putpixel((x, 43), (255, 0, 0))
        handler.manager.get_frame_copy.return_value = frame

        handler._scroll_last_play('LAST: Test play.')

        background = handler.manager.set_image.call_args_list[0].args[0]
        # Strip repainted with the batter-area gradient, not the old text
        assert background.getpixel((48, 39)) == (255, 255, 255)
        assert background.getpixel((48, 43)) == (175, 175, 175)
        assert background.getpixel((48, 46)) == (115, 115, 115)
        # Rest of the frame untouched
        assert background.getpixel((48, 20)) == (200, 200, 200)

    def test_batter_line_restored_after_scroll(self, monkeypatch) -> None:
        import live_game_handler as lgh
        from PIL import Image

        monkeypatch.setattr(lgh.time, 'sleep', lambda seconds: None)
        handler = self._handler()
        frame = Image.new('RGB', (96, 48), (200, 200, 200))
        for x in range(96):
            frame.putpixel((x, 43), (255, 0, 0))
        handler.manager.get_frame_copy.return_value = frame

        handler._scroll_last_play('LAST: Test play.')

        # The final frame put up is the original, batter line intact
        final = handler.manager.set_image.call_args_list[-1].args[0]
        assert final.getpixel((48, 43)) == (255, 0, 0)
        # And it was swapped to the display
        assert (handler.manager.swap_canvas.call_count
                == handler.manager.set_image.call_count)

    def test_each_play_scrolls_exactly_once(self, monkeypatch) -> None:
        import live_game_handler as lgh

        monkeypatch.setattr(lgh.time, 'sleep', lambda seconds: None)
        handler = self._handler()
        play_data = {'allPlays': [_play('Ian Happ walks.')]}

        assert handler._maybe_scroll_last_play(
            play_data, banner_active=False) is True
        first_pass_frames = handler.manager.swap_canvas.call_count
        assert first_pass_frames > 0

        # Same play again: no new scroll
        assert handler._maybe_scroll_last_play(
            play_data, banner_active=False) is False
        assert handler.manager.swap_canvas.call_count == first_pass_frames

        # A new play scrolls again
        play_data['allPlays'].append(_play('Seiya Suzuki homers.'))
        assert handler._maybe_scroll_last_play(
            play_data, banner_active=False) is True
        assert handler.manager.swap_canvas.call_count > first_pass_frames

    def test_no_scroll_while_review_banner_active(self, monkeypatch) -> None:
        import live_game_handler as lgh

        monkeypatch.setattr(lgh.time, 'sleep', lambda seconds: None)
        handler = self._handler()
        play_data = {'allPlays': [_play('Ian Happ walks.')]}

        handler._maybe_scroll_last_play(play_data, banner_active=True)
        assert handler.manager.swap_canvas.call_count == 0

        # Once the banner clears, the play still gets its scroll
        handler._maybe_scroll_last_play(play_data, banner_active=False)
        assert handler.manager.swap_canvas.call_count > 0

    def test_scrolls_text_across_and_off_screen(self, monkeypatch) -> None:
        import live_game_handler as lgh
        from scoreboard_config import Fonts

        monkeypatch.setattr(lgh.time, 'sleep', lambda seconds: None)
        handler = self._handler()

        text = 'LAST: Test play.'
        handler._scroll_last_play(text)

        xs = [call.args[1]
              for call in handler.manager.draw_text.call_args_list]
        text_width = len(text) * Fonts.CHAR_WIDTH_MICRO

        # Starts off-screen right, moves 1px left per frame, exits left
        assert xs[0] == 96
        assert xs == list(range(96, xs[-1] - 1, -1))
        assert xs[-1] + text_width <= 0

        # Background painted and canvas swapped every frame, plus one
        # final frame restoring the static display
        assert handler.manager.set_image.call_count == len(xs) + 1
        assert handler.manager.swap_canvas.call_count == len(xs) + 1

    def test_stops_immediately_on_shutdown(self, monkeypatch) -> None:
        import live_game_handler as lgh

        monkeypatch.setattr(lgh.time, 'sleep', lambda seconds: None)
        monkeypatch.setattr(lgh, '_is_shutdown_requested', lambda: True)
        handler = self._handler()

        handler._scroll_last_play('LAST: Test play.')

        assert handler.manager.swap_canvas.call_count == 0

    def test_aborts_when_split_squad_switch_is_due(self, monkeypatch) -> None:
        import live_game_handler as lgh

        monkeypatch.setattr(lgh.time, 'sleep', lambda seconds: None)
        handler = self._handler()
        handler.manager.split_squad_indicator = True
        handler.manager.split_squad_switch_time = 0  # already in the past

        handler._scroll_last_play('LAST: Test play.')

        # No scroll frames drawn — just the single restored static frame
        assert handler.manager.draw_text.call_count == 0
        assert handler.manager.swap_canvas.call_count == 1


# ============================================================================
# Scoreboard status heartbeat
# ============================================================================

class TestStatusHeartbeat:
    def test_write_status_heartbeat(self, tmp_path, monkeypatch) -> None:
        import status_heartbeat

        status_file = tmp_path / 'status.json'
        monkeypatch.setattr(status_heartbeat, 'STATUS_FILE', str(status_file))

        status_heartbeat.write_status_heartbeat(
            'In Progress', 'Cubs vs Brewers')

        data = json.loads(status_file.read_text())
        assert data['state'] == 'In Progress'
        assert data['detail'] == 'Cubs vs Brewers'
        assert data['timestamp'] > 0

    def test_heartbeat_write_never_raises(self, monkeypatch) -> None:
        import status_heartbeat

        monkeypatch.setattr(
            status_heartbeat, 'STATUS_FILE', '/nonexistent/dir/status.json')
        status_heartbeat.write_status_heartbeat('In Progress')  # no raise

    def test_route_by_status_sets_manager_status(self) -> None:
        from tests.test_bugfixes import _make_scoreboard

        sb = _make_scoreboard()
        with patch('main.time.sleep'):
            sb.route_by_status(
                [{'game_type': 'R', 'game_date': '2026-07-09'}],
                12345, 'In Progress')

        sb.manager.set_status.assert_called_once_with(
            'In Progress', '2026-07-09')

    def test_swap_canvas_refreshes_heartbeat_with_current_state(
        self, tmp_path, monkeypatch
    ) -> None:
        # The heartbeat must stay fresh as long as frames are rendering,
        # even when the router hasn't run for many minutes
        import status_heartbeat
        from scoreboard_manager import ScoreboardManager

        status_file = tmp_path / 'status.json'
        monkeypatch.setattr(status_heartbeat, 'STATUS_FILE', str(status_file))

        manager = ScoreboardManager.__new__(ScoreboardManager)
        manager.matrix = Mock()
        manager.canvas = Mock()
        manager._last_brightness_check = 1e12
        manager._applied_brightness = 100
        manager._save_preview = Mock()
        manager._last_heartbeat = 0.0
        manager.current_status = ('Starting up', '')

        manager.set_status('In Progress', '2026-07-09')
        manager.swap_canvas()

        data = json.loads(status_file.read_text())
        assert data['state'] == 'In Progress'
        assert data['detail'] == '2026-07-09'

    def test_heartbeat_is_throttled_per_swap(
        self, tmp_path, monkeypatch
    ) -> None:
        import os
        import status_heartbeat
        from scoreboard_manager import ScoreboardManager

        status_file = tmp_path / 'status.json'
        monkeypatch.setattr(status_heartbeat, 'STATUS_FILE', str(status_file))

        manager = ScoreboardManager.__new__(ScoreboardManager)
        manager.matrix = Mock()
        manager.canvas = Mock()
        manager._last_brightness_check = 1e12
        manager._applied_brightness = 100
        manager._save_preview = Mock()
        manager._last_heartbeat = 0.0
        manager.current_status = ('Weather', '')

        manager.swap_canvas()
        first_mtime = os.path.getmtime(status_file)
        manager.swap_canvas()  # immediately again - must skip the write

        assert os.path.getmtime(status_file) == first_mtime


# ============================================================================
# Live matrix preview
# ============================================================================

class TestPreviewMirror:
    def _manager(self):
        from unittest.mock import Mock
        from scoreboard_manager import ScoreboardManager

        manager = ScoreboardManager.__new__(ScoreboardManager)
        manager.canvas = Mock()
        manager.matrix = Mock()
        manager.fonts = {'tiny_bold': Mock()}
        manager._last_brightness_check = 0.0
        manager._applied_brightness = None
        manager.update_brightness = Mock()
        manager._refresh_heartbeat = Mock()
        manager._init_preview_mirror()
        return manager

    def test_draw_pixel_mirrors_to_frame(self) -> None:
        manager = self._manager()

        manager.draw_pixel(5, 6, 255, 0, 0)

        assert manager._frame.getpixel((5, 6)) == (255, 0, 0)
        manager.canvas.SetPixel.assert_called_once_with(5, 6, 255, 0, 0)

    def test_out_of_bounds_pixel_does_not_crash_mirror(self) -> None:
        manager = self._manager()
        manager.draw_pixel(200, 200, 255, 0, 0)  # off the 96x48 panel

    def test_clear_canvas_blanks_mirror(self) -> None:
        manager = self._manager()
        manager.draw_pixel(5, 6, 255, 0, 0)

        manager.clear_canvas()

        assert manager._frame.getpixel((5, 6)) == (0, 0, 0)
        manager.canvas.Clear.assert_called_once()

    def test_set_image_pastes_into_mirror(self) -> None:
        from PIL import Image

        manager = self._manager()
        img = Image.new('RGB', (10, 10), (0, 128, 0))

        manager.set_image(img, 3, 4)

        assert manager._frame.getpixel((3, 4)) == (0, 128, 0)
        assert manager._frame.getpixel((12, 13)) == (0, 128, 0)
        manager.canvas.SetImage.assert_called_once()

    def test_draw_text_mirrors_glyphs(self) -> None:
        manager = self._manager()

        # Baseline y=10: glyph pixels land in rows above the baseline
        manager.draw_text('tiny_bold', 2, 10, (255, 255, 255), 'W')

        region = manager._frame.crop((0, 0, 12, 11))
        lit = [p for p in region.getdata() if p != (0, 0, 0)]
        assert lit, 'expected the mirrored W glyph to light pixels'

    def test_swap_canvas_saves_preview_png(
        self, tmp_path, monkeypatch
    ) -> None:
        from PIL import Image
        import scoreboard_manager as sm

        preview = tmp_path / 'preview.png'
        monkeypatch.setattr(sm, 'PREVIEW_FILE_PATH', str(preview))

        manager = self._manager()
        manager.draw_pixel(0, 0, 255, 0, 0)
        manager.swap_canvas()

        saved = Image.open(preview)
        assert saved.size == (96, 48)
        assert saved.convert('RGB').getpixel((0, 0)) == (255, 0, 0)

    def test_preview_save_is_throttled(self, tmp_path, monkeypatch) -> None:
        import os
        import scoreboard_manager as sm

        preview = tmp_path / 'preview.png'
        monkeypatch.setattr(sm, 'PREVIEW_FILE_PATH', str(preview))

        manager = self._manager()
        manager.swap_canvas()
        first_mtime = os.path.getmtime(preview)
        manager.swap_canvas()  # immediately again - must skip the save

        assert os.path.getmtime(preview) == first_mtime

    def test_no_direct_canvas_setimage_outside_manager(self) -> None:
        from pathlib import Path

        root = Path(__file__).parent.parent
        offenders = []
        for py in root.glob('*.py'):
            if py.name == 'scoreboard_manager.py':
                continue
            if '.canvas.SetImage(' in py.read_text():
                offenders.append(py.name)

        assert offenders == [], (
            f'{offenders} draw around the preview mirror; '
            'use manager.set_image() instead'
        )


class TestPreviewRoute:
    def test_serves_png_when_available(self, tmp_path, monkeypatch) -> None:
        from PIL import Image
        import wifi_config_server as wcs

        preview = tmp_path / 'preview.png'
        Image.new('RGB', (96, 48), (10, 20, 30)).save(preview)
        monkeypatch.setattr(wcs, 'PREVIEW_FILE_PATH', str(preview))

        resp = wcs.app.test_client().get('/preview.png')

        assert resp.status_code == 200
        assert resp.mimetype == 'image/png'
        assert 'no-store' in resp.headers.get('Cache-Control', '')

    def test_404_when_preview_missing(self, tmp_path, monkeypatch) -> None:
        import wifi_config_server as wcs

        monkeypatch.setattr(
            wcs, 'PREVIEW_FILE_PATH', str(tmp_path / 'nope.png'))

        resp = wcs.app.test_client().get('/preview.png')

        assert resp.status_code == 404


class TestScoreboardStatusRoute:
    def _get_status(self, tmp_path, monkeypatch, heartbeat=None):
        import wifi_config_server as wcs

        status_file = tmp_path / 'status.json'
        if heartbeat is not None:
            status_file.write_text(json.dumps(heartbeat))
        monkeypatch.setattr(wcs, 'STATUS_FILE', str(status_file))
        client = wcs.app.test_client()
        resp = client.get('/scoreboard_status')
        assert resp.status_code == 200
        return resp.get_json()

    def test_returns_fresh_heartbeat(self, tmp_path, monkeypatch) -> None:
        data = self._get_status(tmp_path, monkeypatch, {
            'timestamp': time.time(), 'state': 'In Progress',
            'detail': 'Cubs vs Brewers',
        })

        assert data['available'] is True
        assert data['state'] == 'In Progress'
        assert data['stale'] is False

    def test_flags_stale_heartbeat(self, tmp_path, monkeypatch) -> None:
        data = self._get_status(tmp_path, monkeypatch, {
            'timestamp': time.time() - 600, 'state': 'In Progress',
            'detail': '',
        })

        assert data['available'] is True
        assert data['stale'] is True

    def test_handles_missing_heartbeat_file(
        self, tmp_path, monkeypatch
    ) -> None:
        data = self._get_status(tmp_path, monkeypatch, heartbeat=None)

        assert data['available'] is False


# ============================================================================
# Flight tracker visual upgrade: icons, compass, radar sweep
# ============================================================================

class TestFlightVisualHelpers:
    def _display(self):
        from flight_display import FlightDisplay

        return FlightDisplay.__new__(FlightDisplay)

    def test_airline_name_from_callsign(self) -> None:
        display = self._display()

        assert display._airline_name('UAL1837') == 'UNITED'
        assert display._airline_name('SWA452') == 'SOUTHWEST'
        assert display._airline_name('FDX9821') == 'FEDEX'
        assert display._airline_name('N425PC') is None   # GA registration
        assert display._airline_name('XXX123') is None   # unknown prefix
        assert display._airline_name('') is None

    def test_aircraft_category_from_type_code(self) -> None:
        display = self._display()

        category = display._aircraft_category
        assert category('B738') == 'jet'
        assert category('A321') == 'jet'
        assert category('B77W') == 'jet'
        assert category('E75L') == 'regional'
        assert category('CRJ9') == 'regional'
        assert category('C172') == 'prop'
        assert category('PA28') == 'prop'
        assert category('SR22') == 'prop'
        assert category('R44') == 'heli'
        assert category('') == ''
        assert category(None) == ''

    def test_heading_vector_points_the_right_way(self) -> None:
        display = self._display()

        vector = display._heading_vector
        assert vector(0, 3) == (0, -3)     # north: straight up
        assert vector(90, 3) == (3, 0)     # east: right
        assert vector(180, 3) == (0, 3)    # south: down
        assert vector(270, 3) == (-3, 0)   # west: left
        dx, dy = vector(45, 3)             # northeast: up-right
        assert dx > 0 and dy < 0

    def test_radar_sweep_rotates_once_every_four_seconds(self) -> None:
        display = self._display()

        sweep = display._sweep_angle
        assert sweep(0.0) == 0
        assert sweep(1.0) == 90
        assert sweep(2.5) == 225
        assert sweep(4.0) == 0    # wraps
        assert sweep(5.0) == 90

    def test_vertical_rate_indicator_reports_direction(self) -> None:
        display = self._display()

        indicator = display._get_vertical_rate_indicator
        text, color, direction = indicator(1856)
        assert text == '1856' and direction == 'up'
        text, color, direction = indicator(-1200)
        assert text == '1200' and direction == 'down'
        text, color, direction = indicator(50)
        assert text == 'LVL' and direction == 'level'
        text, color, direction = indicator(None)
        assert text == '' and direction == 'level'


# ============================================================================
# Game-over screen interleaved with the post-game rotation
# ============================================================================

class _FakeTime:
    """time.time/time.sleep stand-in so display loops finish instantly"""

    def __init__(self) -> None:
        self.now = 1000.0

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class _FakePendulum:
    """pendulum.now() stand-in with a mutable date for loop-exit control"""

    def __init__(self, date: str = '2026-07-09', hhmm: str = '20:00') -> None:
        self.date = date
        self.hhmm = hhmm

    def now(self, *args, **kwargs):
        return self

    def format(self, fmt: str) -> str:
        return self.date if 'YYYY' in fmt else self.hhmm


class TestGameOverInterleave:
    """The FINAL screen reappears between every post-game rotation segment"""

    def _game_info(self):
        # Cubs away, lost 2-3 (loss avoids the W-flag path)
        return {
            'liveData': {
                'boxscore': {'teams': {
                    'home': {'teamStats': {
                        'batting': {'runs': 3, 'hits': 8},
                        'fielding': {'errors': 0}}},
                    'away': {'teamStats': {
                        'batting': {'runs': 2, 'hits': 5},
                        'fielding': {'errors': 1}}},
                }},
                'linescore': {'currentInning': 9},
            },
            'gameData': {'teams': {'home': {'id': 110}}},
        }

    def _handler(self, monkeypatch, fake_pendulum):
        from PIL import Image
        import live_game_handler as lgh
        from live_game_handler import LiveGameHandler

        monkeypatch.setattr(lgh, 'time', _FakeTime())
        monkeypatch.setattr(lgh, 'pendulum', fake_pendulum)
        monkeypatch.setattr(
            lgh, 'retry_api_call', lambda *a, **k: self._game_info())

        handler = LiveGameHandler.__new__(LiveGameHandler)
        handler.manager = Mock()
        handler.manager.game_images = {
            'cubs': Image.new('RGBA', (26, 26)),
            'opponent': Image.new('RGBA', (26, 26)),
        }
        handler.off_season_handler = Mock()
        return handler

    def _run_one_cycle(self, monkeypatch):
        """Run display_game_over through one rotation, capturing the
        callback it hands to the rotation cycle."""
        fake_pendulum = _FakePendulum()
        handler = self._handler(monkeypatch, fake_pendulum)
        captured = {}

        def fake_rotation(between_callback=None):
            captured['callback'] = between_callback
            captured['final_drawn_before_rotation'] = any(
                'FINAL' in str(c)
                for c in handler.manager.draw_text.call_args_list)
            fake_pendulum.date = '2026-07-10'  # exit the game-over loop

        handler.off_season_handler._display_rotation_cycle = fake_rotation
        handler.display_game_over([{'doubleheader': 'N'}], 0, 12345)
        return handler, captured, fake_pendulum

    def test_interlude_duration_configured(self) -> None:
        from scoreboard_config import GameConfig

        assert 30 <= GameConfig.GAME_OVER_INTERLUDE_TIME <= 120

    def test_rotation_receives_game_over_callback(self, monkeypatch) -> None:
        _, captured, _ = self._run_one_cycle(monkeypatch)

        assert callable(captured['callback'])

    def test_final_screen_shown_before_first_rotation(self, monkeypatch) -> None:
        _, captured, _ = self._run_one_cycle(monkeypatch)

        assert captured['final_drawn_before_rotation'] is True

    def test_callback_redraws_final_between_segments(self, monkeypatch) -> None:
        handler, captured, fake_pendulum = self._run_one_cycle(monkeypatch)

        fake_pendulum.date = '2026-07-09'  # back to game day
        handler.manager.draw_text.reset_mock()
        assert captured['callback']() is False
        assert any('FINAL' in str(c)
                   for c in handler.manager.draw_text.call_args_list)

    def test_callback_signals_exit_when_day_rolls_over(self, monkeypatch) -> None:
        handler, captured, fake_pendulum = self._run_one_cycle(monkeypatch)

        fake_pendulum.date = '2026-07-10'
        assert captured['callback']() is True


class TestRadarSweepFlare:
    """Dots flare up as the radar sweep passes over them"""

    def _display(self):
        from flight_display import FlightDisplay

        return FlightDisplay.__new__(FlightDisplay)

    def test_dot_bearing_cardinal_directions(self) -> None:
        display = self._display()

        bearing = display._dot_bearing
        assert bearing(48, 20, 48, 10) == 0     # due north of center
        assert bearing(48, 20, 58, 20) == 90    # due east
        assert bearing(48, 20, 48, 30) == 180   # due south
        assert bearing(48, 20, 38, 20) == 270   # due west

    def test_flare_full_at_sweep_and_decays_behind(self) -> None:
        display = self._display()

        flare = display._sweep_flare
        assert flare(90, 90) == pytest.approx(1.0)
        assert 0.5 < flare(100, 90) < 1.0       # 10 degrees behind the beam
        assert flare(90, 100) == 0.0            # ahead of the beam: no flare
        assert flare(90, 200) == 0.0            # long since passed: faded out

    def test_flare_wraps_past_north(self) -> None:
        display = self._display()

        flare = display._sweep_flare
        assert 0.5 < flare(5, 350) < 1.0        # beam at 5, dot at 350
        assert flare(350, 5) == 0.0             # dot ahead of the beam


class TestRadarOneDotPerPlane:
    """Every aircraft on the radar scope renders exactly one marker: no
    detached heading-tail or sweep-halo pixels that read as phantom planes"""

    def _flight(self, callsign, dlat, dlon, distance, heading):
        return {
            'callsign': callsign,
            'altitude_ft': 35000,
            'distance': distance,
            'latitude': 41.9 + dlat,
            'longitude': -87.6 + dlon,
            'heading': heading,
            'destination': 'UNKNOWN',
        }

    def _aircraft_pixels(self, monkeypatch):
        """Render one radar frame, return aircraft-attributed draw_pixel
        calls (all planes are high-altitude gold, red >= 127; every other
        scope element - rings, sweep, crosshair, separator - has red < 127)"""
        import flight_display as fd
        from flight_display import FlightDisplay
        from scoreboard_config import Colors

        monkeypatch.setattr(fd, 'time', _FakeTime())

        display = FlightDisplay.__new__(FlightDisplay)
        display.manager = Mock()
        display.latitude = 41.9
        display.longitude = -87.6
        display.flight_max_range_nm = 30
        display.ALTITUDE_HIGH = Colors.FLIGHT_ALTITUDE_HIGH
        display.flight_data = [
            self._flight('UAL1', 0.0, 0.04, 2.0, 0),       # highlighted, east
            self._flight('SWA2', -0.02, 0.03, 4.0, 90),    # southeast
            self._flight('AAL3', 0.02, -0.005, 3.0, 180),  # north, in sweep flare
        ]

        display._display_radar_view(0, 0.05)  # exactly one frame

        return [c.args for c in display.manager.draw_pixel.call_args_list
                if c.args[2] >= 127]

    def test_one_marker_per_plane_and_nothing_else(self, monkeypatch) -> None:
        pixels = self._aircraft_pixels(monkeypatch)

        whites = {(x, y) for x, y, r, g, b in pixels if (r, g, b) == (255, 255, 255)}
        golds = [(x, y) for x, y, r, g, b in pixels if (r, g, b) != (255, 255, 255)]

        # Highlighted plane: one contiguous 3x3 blinking marker
        assert len(whites) == 9
        xs = {x for x, y in whites}
        ys = {y for x, y in whites}
        assert max(xs) - min(xs) == 2 and max(ys) - min(ys) == 2

        # Each other plane: exactly one pixel, nothing detached around it
        assert len(golds) == 2
        assert len(set(golds)) == 2


# ============================================================================
# Stock screen redesign: dashboard, market hours, sparkline
# ============================================================================

class TestStockDashboard:
    def _display(self):
        from stock_display import StockDisplay

        return StockDisplay.__new__(StockDisplay)

    def test_market_open_during_trading_hours(self) -> None:
        display = self._display()

        open_check = display._is_market_open
        # Thursday 2026-07-09
        assert open_check(pendulum.datetime(
            2026, 7, 9, 13, 0, tz='America/New_York')) is True
        assert open_check(pendulum.datetime(
            2026, 7, 9, 9, 30, tz='America/New_York')) is True
        assert open_check(pendulum.datetime(
            2026, 7, 9, 8, 0, tz='America/New_York')) is False
        assert open_check(pendulum.datetime(
            2026, 7, 9, 16, 0, tz='America/New_York')) is False
        # Saturday
        assert open_check(pendulum.datetime(
            2026, 7, 11, 13, 0, tz='America/New_York')) is False

    def test_view_schedule_dashboard_then_sparklines(self) -> None:
        display = self._display()

        view = display._view_for_tick
        assert view(0.0, 4) == ('dashboard', None)
        assert view(14.9, 4) == ('dashboard', None)
        assert view(15.0, 4) == ('sparkline', 0)
        assert view(23.5, 4) == ('sparkline', 1)
        assert view(46.9, 4) == ('sparkline', 3)
        assert view(47.0, 4) == ('dashboard', None)  # cycle wraps

    def test_view_schedule_without_indices_stays_on_dashboard(self) -> None:
        display = self._display()

        assert display._view_for_tick(99.0, 0) == ('dashboard', None)

    def test_parse_chart_points_filters_gaps(self) -> None:
        display = self._display()

        data = {'chart': {'result': [{'indicators': {'quote': [
            {'close': [100.0, None, 101.5, 102.0, None]}]}}]}}
        assert display._parse_chart_points(data) == [100.0, 101.5, 102.0]
        assert display._parse_chart_points({}) == []

    def test_scale_points_maps_to_pixel_box(self) -> None:
        display = self._display()

        pts = display._scale_points([1.0, 2.0, 3.0], 0, 0, 3, 3)
        assert pts == [(0, 2), (1, 1), (2, 0)]

    def test_scale_points_flat_series_draws_midline(self) -> None:
        display = self._display()

        pts = display._scale_points([5.0, 5.0], 10, 20, 2, 4)
        assert pts == [(10, 22), (11, 22)]


# ============================================================================
# New rotation screens: clock, history, sky, ISS, celebrations
# ============================================================================

class TestWrigleyClock:
    def _display(self):
        from clock_display import WrigleyClockDisplay

        return WrigleyClockDisplay.__new__(WrigleyClockDisplay)

    def test_hand_angles(self) -> None:
        angles = self._display()._hand_angles
        assert angles(3, 0, 0) == (90.0, 0.0, 0.0)
        assert angles(6, 30, 0) == (195.0, 180.0, 0.0)
        assert angles(12, 0, 30) == (0.0, 0.0, 180.0)
        assert angles(15, 45, 0) == (112.5, 270.0, 0.0)  # 24h input wraps


class TestCubsHistory:
    def _display(self):
        from cubs_history_display import CubsHistoryDisplay

        return CubsHistoryDisplay.__new__(CubsHistoryDisplay)

    def test_entry_lookup_by_date(self) -> None:
        display = self._display()
        display.history = {'11-02': [{'year': 2016, 'text': 'WORLD CHAMPS'}]}

        assert display._entries_for(11, 2)[0]['year'] == 2016
        assert display._entries_for(7, 4) == []

    def test_history_file_loads_with_famous_dates(self) -> None:
        from cubs_history_display import CubsHistoryDisplay

        history = CubsHistoryDisplay._load_history()
        assert any(e['year'] == 2016 for e in history.get('11-02', []))
        assert any(e['year'] == 1998 for e in history.get('05-06', []))
        for date_key, entries in history.items():
            month, day = date_key.split('-')
            assert 1 <= int(month) <= 12 and 1 <= int(day) <= 31
            for entry in entries:
                assert entry['text'] == entry['text'].upper()
                assert len(entry['text']) <= 96

    def test_wrap_text_to_pixel_lines(self) -> None:
        wrap = self._display()._wrap
        assert wrap('KERRY WOOD STRIKES OUT 20 ASTROS', 12) == [
            'KERRY WOOD', 'STRIKES OUT', '20 ASTROS']
        assert wrap('SHORT', 12) == ['SHORT']


class TestSkyDisplay:
    def _display(self):
        from sky_display import SkyDisplay

        return SkyDisplay.__new__(SkyDisplay)

    def test_moon_phase_at_known_new_and_full_moons(self) -> None:
        moon = self._display()._moon_phase
        frac, name = moon(pendulum.datetime(2000, 1, 6, 18, tz='UTC'))
        assert frac < 0.02 or frac > 0.98
        assert name == 'NEW MOON'
        frac, name = moon(pendulum.datetime(2000, 1, 21, 4, tz='UTC'))
        assert abs(frac - 0.5) < 0.03
        assert name == 'FULL MOON'

    def test_sun_fraction_across_the_day(self) -> None:
        sun = self._display()._sun_fraction
        assert sun(1200, 1000, 2000) == pytest.approx(0.2)
        assert sun(2000, 1000, 2000) is None   # after sunset
        assert sun(500, 1000, 2000) is None    # before sunrise
        assert sun(1000, 1000, 2000) == pytest.approx(0.0)


class TestISSDisplay:
    def _display(self):
        from iss_display import ISSDisplay

        return ISSDisplay.__new__(ISSDisplay)

    def test_distance_and_bearing_to_iss(self) -> None:
        display = self._display()
        # Same point: zero distance
        assert display._distance_mi(41.7, -88.0, 41.7, -88.0) < 1
        # Due north: bearing ~0, one degree of latitude ~69 miles
        dist = display._distance_mi(41.7, -88.0, 42.7, -88.0)
        assert 66 <= dist <= 72
        assert display._cardinal(display._bearing(41.7, -88.0, 42.7, -88.0)) == 'N'
        assert display._cardinal(display._bearing(0.0, 0.0, 0.0, 10.0)) == 'E'

    def test_parse_iss_position(self) -> None:
        display = self._display()
        payload = {'message': 'success',
                   'iss_position': {'latitude': '41.9', 'longitude': '-87.6'}}
        assert display._parse_position(payload) == (41.9, -87.6)
        assert display._parse_position({'message': 'error'}) is None
        assert display._parse_position({}) is None


class TestCelebrations:
    def _display(self):
        from celebration_display import CelebrationDisplay

        return CelebrationDisplay.__new__(CelebrationDisplay)

    def test_matches_todays_celebrations(self) -> None:
        display = self._display()
        config = {'celebrations': [
            {'date': '07-09', 'name': 'RYAN', 'type': 'birthday'},
            {'date': '12-25', 'name': 'CHRISTMAS', 'type': 'holiday'},
        ]}
        today = pendulum.datetime(2026, 7, 9)

        matches = display._todays_celebrations(config, today)
        assert len(matches) == 1 and matches[0]['name'] == 'RYAN'

    def test_ignores_malformed_entries(self) -> None:
        display = self._display()
        config = {'celebrations': [
            {'date': 'bogus', 'name': 'X', 'type': 'birthday'},
            {'name': 'NO DATE'},
            'not-a-dict',
        ]}
        assert display._todays_celebrations(
            config, pendulum.datetime(2026, 7, 9)) == []

    def test_message_for_each_type(self) -> None:
        display = self._display()
        msg = display._message_for
        assert msg({'type': 'birthday', 'name': 'EMMA'}) == 'HAPPY BIRTHDAY EMMA!'
        assert msg({'type': 'anniversary', 'name': 'M & D'}) == 'HAPPY ANNIVERSARY M & D!'
        assert msg({'type': 'holiday', 'name': 'CHRISTMAS'}) == 'HAPPY CHRISTMAS!'


class TestNewScreensInRotation:
    def test_rotation_schedule_has_new_segments(self) -> None:
        import off_season_handler as osh
        import inspect

        source = inspect.getsource(osh)
        for segment in ('clock', 'cubs_history', 'sky', 'iss', 'celebration'):
            assert f"'{segment}'" in source, f'{segment} missing from rotation'


class TestWrigleyClockSky:
    """The clock screen's sky tracks time of day and weather"""

    def test_sky_phase_day_dawn_dusk_night(self) -> None:
        from clock_display import WrigleyClockDisplay

        phase = WrigleyClockDisplay._sky_phase
        sunrise, sunset = 100000.0, 100000.0 + 14 * 3600
        assert phase(sunrise + 5 * 3600, sunrise, sunset) == 'day'
        assert phase(sunrise + 60, sunrise, sunset) == 'dawn'
        assert phase(sunrise - 600, sunrise, sunset) == 'dawn'
        assert phase(sunset - 60, sunrise, sunset) == 'dusk'
        assert phase(sunset + 3600, sunrise, sunset) == 'night'
        assert phase(sunrise - 4 * 3600, sunrise, sunset) == 'night'

    def test_sky_colors_follow_phase_and_weather(self) -> None:
        from clock_display import WrigleyClockDisplay

        colors = WrigleyClockDisplay._sky_colors
        day_top, _ = colors('day', 'Clear')
        assert day_top[2] > day_top[0] + 40         # clear day: blue sky
        rain_top, _ = colors('day', 'Rain')
        assert abs(rain_top[0] - rain_top[1]) < 25  # rain: gray sky
        _, dusk_horizon = colors('dusk', 'Clear')
        assert dusk_horizon[0] > dusk_horizon[2]    # dusk: warm horizon
        night_top, _ = colors('night', 'Clear')
        assert max(night_top) < 60                  # night: dark sky

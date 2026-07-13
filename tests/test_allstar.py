"""Tests for the All-Star break screens (allstar_display.py)"""

from __future__ import annotations

import pendulum
import pytest
from unittest.mock import Mock


def _display():
    from allstar_display import AllStarDisplay

    display = AllStarDisplay.__new__(AllStarDisplay)
    display.manager = Mock()
    display._asg_cache = None
    display._asg_cached_at = 0.0
    display._feed_cache = None
    display._feed_cached_at = 0.0
    return display


ASG_SCHEDULE_FIXTURE = {
    'dates': [{'date': '2026-07-14', 'games': [{
        'gamePk': 823443,
        'gameDate': '2026-07-15T00:00:00Z',
        'venue': {'name': 'Citizens Bank Park'},
        'status': {'abstractGameState': 'Preview',
                   'detailedState': 'Scheduled'},
    }]}]
}

FEED_FIXTURE = {
    'gameData': {'status': {'abstractGameState': 'Live'}},
    'liveData': {
        'linescore': {
            'teams': {'away': {'runs': 3}, 'home': {'runs': 5}},
            'currentInning': 5, 'inningState': 'Top', 'outs': 2,
            'offense': {'first': {'id': 1}, 'third': {'id': 2}},
        },
        'plays': {'currentPlay': {'matchup': {'batter': {
            'id': 691718, 'fullName': 'Pete Crow-Armstrong'}}}},
        'boxscore': {'teams': {
            'away': {'players': {
                'ID545361': {'person': {'fullName': 'Mike Trout'},
                             'parentTeamId': 108}}},
            'home': {'players': {
                'ID691718': {'person': {'fullName': 'Pete Crow-Armstrong'},
                             'parentTeamId': 112}}},
        }},
    },
}


class TestAsgData:
    def test_parse_asg_schedule(self) -> None:
        display = _display()

        info = display._parse_asg_schedule(ASG_SCHEDULE_FIXTURE)
        assert info['game_pk'] == 823443
        assert info['venue'] == 'Citizens Bank Park'
        assert info['abstract'] == 'Preview'
        # 00:00Z on the 15th is 7 PM Central on the 14th
        assert info['date'].format('YYYY-MM-DD HH') == '2026-07-14 19'

    def test_parse_empty_schedule_returns_none(self) -> None:
        display = _display()

        assert display._parse_asg_schedule({'dates': []}) is None

    def test_allstar_window_days(self) -> None:
        display = _display()
        display._asg_cache = display._parse_asg_schedule(ASG_SCHEDULE_FIXTURE)
        display._asg_cached_at = 10**12  # never expire in test

        tz = 'America/Chicago'
        window = display.is_allstar_window
        assert window(now=pendulum.datetime(2026, 7, 13, 12, tz=tz)) is True
        assert window(now=pendulum.datetime(2026, 7, 14, 20, tz=tz)) is True
        assert window(now=pendulum.datetime(2026, 7, 12, 12, tz=tz)) is False
        assert window(now=pendulum.datetime(2026, 7, 15, 12, tz=tz)) is False

    def test_derby_active_only_on_derby_evening(self) -> None:
        display = _display()
        display._asg_cache = display._parse_asg_schedule(ASG_SCHEDULE_FIXTURE)
        display._asg_cached_at = 10**12

        tz = 'America/Chicago'
        active = display._derby_active
        assert active(now=pendulum.datetime(2026, 7, 13, 18, tz=tz)) is True
        assert active(now=pendulum.datetime(2026, 7, 13, 23, 30, tz=tz)) is False
        assert active(now=pendulum.datetime(2026, 7, 14, 18, tz=tz)) is False

    def test_stale_derby_constant_disables_derby(self, monkeypatch) -> None:
        import allstar_display as ad

        display = _display()
        display._asg_cache = display._parse_asg_schedule(ASG_SCHEDULE_FIXTURE)
        display._asg_cached_at = 10**12
        # Constant left at last year's date: never active
        monkeypatch.setitem(ad.DERBY_INFO, 'date', '2025-07-14')

        tz = 'America/Chicago'
        assert display._derby_active(
            now=pendulum.datetime(2026, 7, 13, 18, tz=tz)) is False

    def test_asg_is_live_follows_abstract_state(self) -> None:
        display = _display()
        display._asg_cached_at = 10**12

        display._asg_cache = None
        assert display.asg_is_live() is False
        display._asg_cache = {'abstract': 'Preview'}
        assert display.asg_is_live() is False
        display._asg_cache = {'abstract': 'Live'}
        assert display.asg_is_live() is True


class TestFeedParsing:
    def test_cubs_allstars_from_boxscore(self) -> None:
        display = _display()

        names = display._cubs_allstars_from_boxscore(FEED_FIXTURE)
        assert names == ['Pete Crow-Armstrong']

    def test_extract_live_state(self) -> None:
        display = _display()

        state = display._extract_live_state(FEED_FIXTURE)
        assert state['away_runs'] == 3 and state['home_runs'] == 5
        assert state['inning'] == 5 and state['inning_state'] == 'Top'
        assert state['outs'] == 2
        assert state['bases'] == {'first': True, 'second': False,
                                  'third': True}
        assert state['batter_name'] == 'Pete Crow-Armstrong'
        assert state['batter_is_cub'] is True
        assert state['is_final'] is False

    def test_extract_live_state_handles_missing_fields(self) -> None:
        display = _display()

        state = display._extract_live_state(
            {'gameData': {'status': {'abstractGameState': 'Final'}}})
        assert state['is_final'] is True
        assert state['batter_name'] == ''
        assert state['batter_is_cub'] is False
        assert state['bases'] == {'first': False, 'second': False,
                                  'third': False}


class _FakeTime:
    def __init__(self) -> None:
        self.now = 1000.0

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class TestPromoScreens:
    def _live_display(self, monkeypatch, now):
        import allstar_display as ad

        monkeypatch.setattr(ad, 'time', _FakeTime())

        class _FakePendulum:
            @staticmethod
            def now(tz=None):
                return now
            parse = staticmethod(pendulum.parse)
            datetime = staticmethod(pendulum.datetime)
        monkeypatch.setattr(ad, 'pendulum', _FakePendulum)

        display = _display()
        display._asg_cache = display._parse_asg_schedule(ASG_SCHEDULE_FIXTURE)
        display._asg_cached_at = 10**12
        display._feed_cache = FEED_FIXTURE
        display._feed_cached_at = 10**12
        return display

    def _drawn_text(self, display):
        return ' | '.join(
            str(c) for c in display.manager.draw_text.call_args_list)

    def test_promo_shows_derby_on_derby_evening(self, monkeypatch) -> None:
        now = pendulum.datetime(2026, 7, 13, 17, tz='America/Chicago')
        display = self._live_display(monkeypatch, now)

        display.display_promo(1)
        text = self._drawn_text(display)
        assert 'HOME RUN DERBY' in text
        assert 'SCHWARBER' in text            # scrolling field
        assert '2H' in text                   # countdown to 7 PM

    def test_promo_shows_pregame_on_asg_day(self, monkeypatch) -> None:
        now = pendulum.datetime(2026, 7, 14, 12, tz='America/Chicago')
        display = self._live_display(monkeypatch, now)

        display.display_promo(1)
        text = self._drawn_text(display)
        assert 'ALL-STAR GAME' in text
        assert 'CROW-ARMSTRONG' in text       # Cubs all-stars line
        assert 'FIRST PITCH' in text

    def test_promo_noop_outside_window(self, monkeypatch) -> None:
        now = pendulum.datetime(2026, 7, 20, 12, tz='America/Chicago')
        display = self._live_display(monkeypatch, now)

        display.display_promo(1)
        display.manager.draw_text.assert_not_called()


class TestLiveScreen:
    def _live_display(self, monkeypatch, feed):
        import allstar_display as ad

        monkeypatch.setattr(ad, 'time', _FakeTime())
        display = _display()
        display._asg_cache = display._parse_asg_schedule(ASG_SCHEDULE_FIXTURE)
        display._asg_cached_at = 10**12
        display._feed_cache = feed
        display._feed_cached_at = 10**12
        return display

    def test_live_frame_draws_score_and_cubs_banner(self, monkeypatch) -> None:
        display = self._live_display(monkeypatch, FEED_FIXTURE)

        final = display.display_live_game(1)
        assert final is False
        text = ' | '.join(
            str(c) for c in display.manager.draw_text.call_args_list)
        assert "'AL'" in text and "'NL'" in text
        assert "'3'" in text and "'5'" in text       # away/home runs
        assert 'TOP 5' in text
        # Cubs batter: either the flash banner or the name is up
        assert 'CUBS STAR AT BAT' in text or 'CROW-ARMSTRONG' in text

    def test_live_game_returns_true_on_final(self, monkeypatch) -> None:
        import copy

        feed = copy.deepcopy(FEED_FIXTURE)
        feed['gameData']['status']['abstractGameState'] = 'Final'
        display = self._live_display(monkeypatch, feed)

        assert display.display_live_game(1) is True

    def test_final_screen_shows_final_score_and_invalidates(
            self, monkeypatch) -> None:
        import copy

        feed = copy.deepcopy(FEED_FIXTURE)
        feed['gameData']['status']['abstractGameState'] = 'Final'
        display = self._live_display(monkeypatch, feed)

        display.display_final(1)
        text = ' | '.join(
            str(c) for c in display.manager.draw_text.call_args_list)
        assert 'FINAL' in text
        assert 'AL 3' in text and 'NL 5' in text
        assert display._asg_cached_at == 0.0     # cache invalidated


class TestRotationIntegration:
    def test_rotation_cycle_has_allstar_segment(self) -> None:
        import inspect
        from off_season_handler import OffSeasonHandler

        init_source = inspect.getsource(OffSeasonHandler.__init__)
        assert "'allstar'" in init_source

        cycle_source = inspect.getsource(
            OffSeasonHandler._display_rotation_cycle)
        assert 'display_promo' in cycle_source
        assert 'enable_allstar' in cycle_source


class TestLiveTakeover:
    def _scoreboard(self):
        from main import CubsScoreboard

        board = CubsScoreboard.__new__(CubsScoreboard)
        board.manager = Mock()
        board.allstar_display = Mock()
        board.off_season_handler = Mock()
        board.state_handler = Mock()
        return board

    def test_asg_live_takes_over_cycle(self) -> None:
        board = self._scoreboard()
        board.allstar_display.asg_is_live.return_value = True
        board.allstar_display.display_live_game.return_value = False

        board.process_game_cycle()

        board.allstar_display.display_live_game.assert_called_once()
        board.manager.get_schedule.assert_not_called()

    def test_asg_final_shows_final_screen(self) -> None:
        board = self._scoreboard()
        board.allstar_display.asg_is_live.return_value = True
        board.allstar_display.display_live_game.return_value = True

        board.process_game_cycle()

        board.allstar_display.display_final.assert_called_once()

    def test_no_asg_runs_normal_cycle(self) -> None:
        board = self._scoreboard()
        board.allstar_display.asg_is_live.return_value = False
        board.manager.get_schedule.return_value = []

        board.process_game_cycle()

        board.manager.get_schedule.assert_called_once()
        board.off_season_handler.display_off_season_content.assert_called_once()

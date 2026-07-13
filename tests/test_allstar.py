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

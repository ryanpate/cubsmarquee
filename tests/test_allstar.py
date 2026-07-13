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
    display._derby_pk = None
    display._derby_pk_checked_at = 0.0
    display._derby_cache = None
    display._derby_cached_at = 0.0
    display._derby_prev_hrs = {}
    display._derby_burst = None
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
        # Derby bracket unpublished unless a test injects one
        display.fetch_derby_data = Mock(return_value=None)
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

    def test_derby_promo_draws_stars_and_ball(self, monkeypatch) -> None:
        now = pendulum.datetime(2026, 7, 13, 17, tz='America/Chicago')
        display = self._live_display(monkeypatch, now)

        display.display_promo(1)
        pixels = display.manager.draw_pixel.call_args_list
        stars = [c for c in pixels if c.args[1] > 0]
        assert len(stars) >= 12                   # twinkling star field
        whites = [c for c in pixels
                  if tuple(c.args[2:]) == (255, 255, 255)]
        assert whites                             # home-run ball in flight
        assert display.manager.set_image.called   # ballpark scene background

    def test_derby_promo_background_scene(self) -> None:
        display = _display()
        img = display._derby_promo_background()
        assert img.getpixel((48, 4)) == (255, 215, 0)     # gold banner
        assert img.getpixel((48, 10)) == (191, 13, 62)    # AL red stripe
        assert img.getpixel((48, 11)) == (10, 35, 120)    # NL blue stripe
        assert img.getpixel((48, 20)) == (8, 10, 28)      # night sky
        assert img.getpixel((48, 45)) != (8, 10, 28)      # outfield grass
        assert img.getpixel((11, 33)) == (235, 235, 230)  # baseball, left
        assert img.getpixel((84, 33)) == (235, 235, 230)  # baseball, right


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


def _derby_seed(name, hrs, started, complete, winner=False):
    return {
        'player': {'id': 1, 'fullName': name},
        'numHomeRuns': hrs, 'isStarted': started,
        'isComplete': complete, 'isWinner': winner,
    }


DERBY_FIXTURE = {
    'status': {'state': 'In Progress', 'currentRound': 2,
               'currentRoundTimeLeft': '1:23'},
    'rounds': [
        {'round': 1, 'matchups': [
            {'topSeed': _derby_seed('Kyle Schwarber', 14, True, True, True),
             'bottomSeed': _derby_seed('Ben Rice', 9, True, True)},
            {'topSeed': _derby_seed('Bryce Harper', 12, True, True, True),
             'bottomSeed': _derby_seed('Jordan Walker', 11, True, True)},
        ]},
        {'round': 2, 'matchups': [
            {'topSeed': _derby_seed('Kyle Schwarber', 6, True, False),
             'bottomSeed': _derby_seed('Bryce Harper', 0, False, False)},
        ]},
    ],
}


class TestDerbyTracker:
    def test_parse_derby_current_matchup_and_batter(self) -> None:
        display = _display()

        state = display._parse_derby(DERBY_FIXTURE)
        assert state['state'] == 'In Progress'
        assert state['round'] == 2 and state['total_rounds'] == 2
        assert state['clock'] == '1:23'
        a, b = state['matchup']
        assert a['name'] == 'SCHWARBER' and a['hrs'] == 6
        assert b['name'] == 'HARPER' and b['hrs'] == 0
        assert state['batter'] == 'SCHWARBER'
        assert state['champion'] is None
        assert 'SCHWARBER 14 DEF RICE 9' in state['results']
        assert 'HARPER 12 DEF WALKER 11' in state['results']

    def test_parse_derby_champion_on_final(self) -> None:
        import copy

        data = copy.deepcopy(DERBY_FIXTURE)
        data['status']['state'] = 'Final'
        final = data['rounds'][1]['matchups'][0]
        final['topSeed'] = _derby_seed('Kyle Schwarber', 15, True, True, True)
        final['bottomSeed'] = _derby_seed('Bryce Harper', 13, True, True)
        display = _display()

        state = display._parse_derby(data)
        assert state['champion']['name'] == 'SCHWARBER'
        assert state['champion']['hrs'] == 15
        assert state['batter'] is None

    def test_derby_candidates_prefers_gametype_then_events(
            self, monkeypatch) -> None:
        import allstar_display as ad

        monkeypatch.setattr(ad, 'statsapi', Mock(get=Mock(return_value={
            'dates': [{'games': [{'gamePk': 777001}]}]})))

        events_json = {'dates': [{'events': [
            {'id': 851300, 'name': 'Home Run Derby Batting Practice'},
            {'id': 851298, 'name': 'Home Run Derby Test #3'},
            {'id': 838655,
             'name': '2026 MLB All-Star Workout Day: Home Run Derby'},
            {'id': 839032, 'name': '2026 MLB Home Run Derby'},
            {'id': 832396, 'name': 'Oracle Park Tour'},
        ]}]}
        fake_resp = Mock()
        fake_resp.json.return_value = events_json
        fake_resp.raise_for_status.return_value = None
        monkeypatch.setattr(ad, 'requests', Mock(
            get=Mock(return_value=fake_resp)))

        display = _display()
        candidates = display._derby_event_candidates()
        assert candidates[0] == 777001            # gameTypes=D first
        assert 838655 in candidates and 839032 in candidates
        assert 851300 not in candidates           # batting practice excluded
        assert 851298 not in candidates           # MLB test event excluded
        assert 832396 not in candidates           # unrelated event excluded

    def test_rejects_mlb_rehearsal_derby_payload(self) -> None:
        import copy

        display = _display()
        display._asg_cache = display._parse_asg_schedule(ASG_SCHEDULE_FIXTURE)
        display._asg_cached_at = 10**12

        rehearsal = copy.deepcopy(DERBY_FIXTURE)
        rehearsal['info'] = {'name': 'Home Run Derby Test #3',
                             'eventDate': '2026-07-08T00:00:00Z'}
        assert display._derby_payload_is_real(rehearsal) is False

        wrong_day = copy.deepcopy(DERBY_FIXTURE)
        wrong_day['info'] = {'name': 'Some Derby',
                             'eventDate': '2026-07-08T00:00:00Z'}
        assert display._derby_payload_is_real(wrong_day) is False

        real = copy.deepcopy(DERBY_FIXTURE)
        real['info'] = {'name': '2026 MLB Home Run Derby',
                        'eventDate': '2026-07-14T00:00:00Z'}
        assert display._derby_payload_is_real(real) is True

    def test_fetch_derby_data_finds_first_published_pk(
            self, monkeypatch) -> None:
        import allstar_display as ad
        import requests as real_requests

        monkeypatch.setattr(ad, 'time', _FakeTime())

        def fake_get(endpoint, params):
            if params['gamePk'] == '838655':
                raise real_requests.HTTPError('404')
            return DERBY_FIXTURE
        monkeypatch.setattr(ad, 'statsapi', Mock(get=Mock(
            side_effect=fake_get)))

        display = _display()
        display._derby_event_candidates = Mock(return_value=[838655, 839032])

        data = display.fetch_derby_data()
        assert data is DERBY_FIXTURE
        assert display._derby_pk == 839032        # remembered for next poll

    def test_fetch_derby_data_none_when_unpublished(
            self, monkeypatch) -> None:
        import allstar_display as ad
        import requests as real_requests

        monkeypatch.setattr(ad, 'time', _FakeTime())
        monkeypatch.setattr(ad, 'statsapi', Mock(get=Mock(
            side_effect=real_requests.HTTPError('404'))))

        display = _display()
        display._derby_event_candidates = Mock(return_value=[838655])

        assert display.fetch_derby_data() is None

    def test_promo_routes_to_live_tracker_when_data_available(
            self, monkeypatch) -> None:
        now = pendulum.datetime(2026, 7, 13, 20, tz='America/Chicago')
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
        display._derby_cache = DERBY_FIXTURE
        display._derby_cached_at = 10**12
        display._derby_pk = 839032

        display.display_promo(1)
        text = ' | '.join(
            str(c) for c in display.manager.draw_text.call_args_list)
        assert 'HR DERBY' in text
        assert 'SCHWARBER' in text and 'HARPER' in text
        assert "'6'" in text                      # live HR count
        assert '1:23' in text                     # round clock
        assert 'DEF' in text                      # results ticker

    def test_live_tracker_shows_champion_when_final(
            self, monkeypatch) -> None:
        import copy
        import allstar_display as ad

        monkeypatch.setattr(ad, 'time', _FakeTime())

        data = copy.deepcopy(DERBY_FIXTURE)
        data['status']['state'] = 'Final'
        final = data['rounds'][1]['matchups'][0]
        final['topSeed'] = _derby_seed('Kyle Schwarber', 15, True, True, True)
        final['bottomSeed'] = _derby_seed('Bryce Harper', 13, True, True)

        display = _display()
        display._derby_cache = data
        display._derby_cached_at = 10**12
        display._derby_pk = 839032

        display._display_derby_live(1)
        text = ' | '.join(
            str(c) for c in display.manager.draw_text.call_args_list)
        assert 'CHAMPION' in text
        assert 'SCHWARBER' in text


class TestDerbyFlair:
    def test_star_field_stays_in_bounds(self) -> None:
        from scoreboard_config import DisplayConfig

        display = _display()
        display._draw_star_field(0.3)
        calls = display.manager.draw_pixel.call_args_list
        assert len(calls) >= 12
        for c in calls:
            x, y = c.args[0], c.args[1]
            assert 0 <= x < DisplayConfig.MATRIX_COLS
            assert 0 < y < DisplayConfig.MATRIX_ROWS   # never over the header

    def test_hr_ball_arcs_only_during_flight(self) -> None:
        display = _display()
        display._draw_hr_ball(0.75)               # mid-flight
        whites = [c for c in display.manager.draw_pixel.call_args_list
                  if tuple(c.args[2:]) == (255, 255, 255)]
        assert whites

        display.manager.reset_mock()
        display._draw_hr_ball(3.0)                # between flights
        display.manager.draw_pixel.assert_not_called()

    def test_hr_burst_fires_when_active_hitter_count_rises(
            self, monkeypatch) -> None:
        import copy
        import allstar_display as ad

        monkeypatch.setattr(ad, 'time', _FakeTime())
        display = _display()
        display._derby_pk = 839032
        display._derby_cache = DERBY_FIXTURE
        display._derby_cached_at = 10**12

        display._display_derby_live(0.05)
        assert display._derby_burst is None       # first look: no burst

        bumped = copy.deepcopy(DERBY_FIXTURE)
        bumped['rounds'][1]['matchups'][0]['topSeed']['numHomeRuns'] = 7
        display._derby_cache = bumped
        display.manager.reset_mock()
        display._display_derby_live(0.05)
        assert display._derby_burst is not None
        golds = [c for c in display.manager.draw_pixel.call_args_list
                 if c.args[1] > 0 and tuple(c.args[2:]) == (255, 215, 0)]
        assert golds                              # burst pixels off-header

    def test_champion_screen_draws_fireworks(self, monkeypatch) -> None:
        import copy
        import allstar_display as ad

        monkeypatch.setattr(ad, 'time', _FakeTime())

        data = copy.deepcopy(DERBY_FIXTURE)
        data['status']['state'] = 'Final'
        final = data['rounds'][1]['matchups'][0]
        final['topSeed'] = _derby_seed('Kyle Schwarber', 15, True, True, True)
        final['bottomSeed'] = _derby_seed('Bryce Harper', 13, True, True)

        display = _display()
        display._derby_pk = 839032
        display._derby_cache = data
        display._derby_cached_at = 10**12

        display._display_derby_live(0.05)
        fireworks = [c for c in display.manager.draw_pixel.call_args_list
                     if c.args[1] > 0]
        assert len(fireworks) >= 10


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

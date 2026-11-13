"""College basketball screens: ESPN parsing, season gating, live takeover.

The JSON under tests/data/ncaab_*.json is recorded ESPN output (2026-11-12),
trimmed of logo and link arrays.
"""

from __future__ import annotations

import json
import os
from unittest.mock import Mock

import pendulum
import pytest

import ncaab_display as nd

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
ILLINI = '356'


def _fixture(name):
    with open(os.path.join(DATA_DIR, name)) as f:
        return json.load(f)


@pytest.fixture
def schedule():
    return _fixture('ncaab_schedule.json')


def _event(schedule, short_name):
    return next(e for e in schedule['events'] if e['shortName'] == short_name)


def _display(schedule=None):
    """A display with no manager I/O and no network"""
    d = nd.CollegeBasketballDisplay.__new__(nd.CollegeBasketballDisplay)
    d.manager = Mock()
    d.team = nd.get_active_ncaab_team({})
    d.schedule = schedule
    d.last_schedule_update = 10 ** 12  # never stale
    d.schedule_interval = 3600
    return d


class TestCompetitors:
    def test_team_is_found_by_id_at_home_and_away(self, schedule):
        home = _event(schedule, 'SHSU @ ILL')['competitions'][0]
        team, opp = nd.split_competitors(home, ILLINI)
        assert team['team']['abbreviation'] == 'ILL'
        assert opp['team']['abbreviation'] == 'SHSU'

        away = _event(schedule, 'ILL @ DUKE')['competitions'][0]
        team, opp = nd.split_competitors(away, ILLINI)
        assert team['team']['abbreviation'] == 'ILL'
        assert opp['team']['abbreviation'] == 'DUKE'

    def test_game_without_the_team_is_an_error(self, schedule):
        competition = _event(schedule, 'ILL @ DUKE')['competitions'][0]
        with pytest.raises(ValueError):
            nd.split_competitors(competition, '99999')

    def test_rank_is_none_for_espns_unranked_sentinel(self, schedule):
        competition = _event(schedule, 'SHSU @ ILL')['competitions'][0]
        team, opp = nd.split_competitors(competition, ILLINI)
        assert nd.competitor_rank(team) == 3
        assert nd.competitor_rank(opp) is None  # ESPN sends 99
        assert nd.competitor_rank({}) is None

    def test_score_reads_both_espn_shapes(self):
        # schedule endpoint: dict; scoreboard endpoint: bare string
        assert nd.competitor_score({'score': {'displayValue': '78'}}) == '78'
        assert nd.competitor_score({'score': '84'}) == '84'
        assert nd.competitor_score({}) == '0'
        assert nd.competitor_score({'score': ''}) == '0'

    def test_site_label(self, schedule):
        for short_name, expected in (('SHSU @ ILL', 'VS'),
                                     ('ILL @ DUKE', 'AT'),
                                     # neutral floor, Illinois listed away
                                     ('ILL VS MIZ', 'VS')):
            competition = _event(schedule, short_name)['competitions'][0]
            team, _ = nd.split_competitors(competition, ILLINI)
            assert nd.site_label(competition, team) == expected


class TestLiveParsing:
    def test_half_scores(self):
        competitor = {'linescores': [{'displayValue': '39'},
                                     {'displayValue': '45'}]}
        assert nd.extract_half_scores(competitor) == ['39', '45']

    def test_every_overtime_sums_into_one_column(self):
        competitor = {'linescores': [{'value': 30.0}, {'value': 35.0},
                                     {'value': 8.0}, {'value': 11.0}]}
        assert nd.extract_half_scores(competitor) == ['30', '35', '19']

    def test_half_scores_absent(self):
        assert nd.extract_half_scores({}) == []

    def test_recorded_live_event_parses(self):
        event = _fixture('ncaab_live_event.json')
        competition = event['competitions'][0]
        assert competition['status']['type']['state'] == 'in'
        home = competition['competitors'][0]
        assert nd.competitor_score(home) == '46'
        assert nd.extract_half_scores(home) == ['46']
        stats = nd.extract_stats(home)
        assert stats['fieldGoalPct'] == '65.4'
        assert stats['rebounds'] == '16'

    def test_lead_text(self):
        assert nd.lead_text('ILL', '68', 'DUKE', '61') == 'ILL BY 7'
        assert nd.lead_text('ILL', '60', 'DUKE', '61') == 'DUKE BY 1'
        assert nd.lead_text('ILL', '61', 'DUKE', '61') == 'TIED'
        assert nd.lead_text('ILL', None, 'DUKE', '61') == ''


class TestCardText:
    def test_tournament_round_is_shortened(self):
        def note(headline):
            return nd.short_note({'notes': [{'headline': headline}]})

        assert note("NCAA Men's Basketball Championship - South Region - "
                    "Sweet 16") == 'NCAA SWEET 16'
        assert note("NCAA Men's Basketball Championship - Final Four"
                    ) == 'NCAA FINAL FOUR'
        assert note('Big Ten Tournament - Quarterfinal'
                    ) == 'BIG TEN TOURN QUARTERFIN'
        assert note('Bad Boy Mowers Series') == 'BAD BOY MOWERS SERIES'

    def test_every_note_fits_one_micro_line(self, schedule):
        for event in schedule['events']:
            assert len(nd.short_note(event['competitions'][0])) <= 24

    def test_ordinary_game_has_no_note(self):
        assert nd.short_note({}) == ''
        assert nd.short_note({'notes': []}) == ''

    def test_fit_name_takes_the_first_that_fits(self):
        names = ['Michigan State', 'Michigan St', 'MSU']
        assert nd.fit_name(names, 14) == 'MICHIGAN STATE'
        assert nd.fit_name(names, 11) == 'MICHIGAN ST'
        assert nd.fit_name(names, 5) == 'MSU'
        assert nd.fit_name(names, 2) == 'MS'
        assert nd.fit_name([None, None], 5) == ''

    def test_ordinal(self):
        assert [nd._ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 18)] == [
            '1ST', '2ND', '3RD', '4TH', '11TH', '12TH', '13TH', '18TH']


class TestRankings:
    def test_recorded_poll(self):
        rankings = nd.parse_rankings(_fixture('ncaab_rankings.json'), ILLINI)
        assert rankings['poll_name'] == 'AP TOP 25'
        assert len(rankings['rows']) == 25
        assert [row['rank'] for row in rankings['rows']] == list(range(1, 26))
        assert rankings['team']['ap'] == 3
        assert rankings['team']['coaches'] is not None
        assert [row['is_team'] for row in rankings['rows']].count(True) == 1
        # Michigan State moved up one spot that week
        assert rankings['rows'][4]['trend'] == 1

    def test_unranked_team_reports_votes(self):
        payload = _fixture('ncaab_rankings.json')
        also_receiving = payload['rankings'][0]['others'][0]
        rankings = nd.parse_rankings(payload, also_receiving['team']['id'])
        assert rankings['team']['ap'] is None
        assert rankings['team']['votes'] == int(also_receiving['points'])

    def test_team_nowhere_in_the_poll(self):
        rankings = nd.parse_rankings(_fixture('ncaab_rankings.json'), '1')
        assert rankings['team'] == {
            'ap': None, 'coaches': None, 'trend': 0, 'votes': None}

    def test_empty_payload(self):
        assert nd.parse_rankings({}, ILLINI)['rows'] == []

    def test_trend(self):
        assert nd.parse_trend('+3') == 3
        assert nd.parse_trend('-2') == -2
        assert nd.parse_trend('-') == 0
        assert nd.parse_trend(None) == 0


class TestStandings:
    @staticmethod
    def _payload(*teams):
        return {'standings': {'entries': [
            {'team': {'id': team_id, 'abbreviation': abbrev},
             'stats': [{'name': 'vs. Conf.', 'displayValue': conf},
                       {'name': 'overall', 'displayValue': overall}]}
            for team_id, abbrev, conf, overall in teams]}}

    def test_ordered_by_conference_record_then_overall(self):
        rows = nd.parse_standings(self._payload(
            ('1', 'AAA', '2-3', '15-2'),
            ('356', 'ILL', '4-1', '12-5'),
            ('2', 'BBB', '4-1', '14-3'),
            ('3', 'CCC', '0-0', '9-0')), ILLINI)
        assert [row['abbrev'] for row in rows] == ['BBB', 'ILL', 'AAA', 'CCC']
        assert [row['position'] for row in rows] == [1, 2, 3, 4]
        assert [row['is_team'] for row in rows] == [False, True, False, False]

    def test_recorded_conference(self):
        rows = nd.parse_standings(_fixture('ncaab_standings.json'), ILLINI)
        assert len(rows) == 18
        assert sum(row['is_team'] for row in rows) == 1
        # Nobody had played a league game: order falls to overall record
        overall = [nd._record_pct(row['overall']) for row in rows]
        assert overall == sorted(overall, reverse=True)

    def test_empty_payload(self):
        assert nd.parse_standings({}, ILLINI) == []

    def test_page_count(self):
        assert nd.page_count(25) == 5
        assert nd.page_count(18) == 4
        assert nd.page_count(0) == 1


class TestSeasonWindow:
    """Recorded schedule: games on Nov 10 and Nov 13, 2026 (Central)."""

    def _at(self, monkeypatch, when):
        fixed = pendulum.parse(when, tz='America/Chicago')
        monkeypatch.setattr(nd.pendulum, 'now', lambda tz=None: (
            fixed.in_timezone(tz) if tz else fixed))

    def test_in_season(self, monkeypatch, schedule):
        self._at(monkeypatch, '2026-11-12T12:00:00')
        assert _display(schedule).has_game_within() is True

    def test_two_weeks_before_the_opener_counts(self, monkeypatch, schedule):
        self._at(monkeypatch, '2026-10-25T12:00:00')
        assert _display(schedule).has_game_within() is True

    def test_summer_is_out_of_season(self, monkeypatch, schedule):
        # ESPN keeps the finished season's schedule up all summer
        self._at(monkeypatch, '2027-07-01T12:00:00')
        assert _display(schedule).has_game_within() is False

    def test_unreachable_schedule_falls_back_to_the_month_gate(
            self, monkeypatch):
        d = _display(None)
        d.last_schedule_update = None
        monkeypatch.setattr(d, '_fetch_schedule', lambda: False)
        self._at(monkeypatch, '2027-01-15T12:00:00')
        assert d.has_game_within() is True
        self._at(monkeypatch, '2027-07-15T12:00:00')
        assert d.has_game_within() is False

    def test_todays_game(self, monkeypatch, schedule):
        self._at(monkeypatch, '2026-11-13T09:00:00')
        game = _display(schedule)._get_todays_game()
        assert game['shortName'] == 'SHSU @ ILL'

    def test_no_game_today(self, monkeypatch, schedule):
        self._at(monkeypatch, '2026-11-15T09:00:00')
        assert _display(schedule)._get_todays_game() is None

    def test_late_game_is_still_current_after_midnight(
            self, monkeypatch, schedule):
        # Tips 9:00 PM Central on Feb 23; still being played at 12:15 AM
        self._at(monkeypatch, '2027-02-24T00:15:00')
        game = _display(schedule)._get_todays_game()
        assert game['shortName'] == 'ILL @ WASH'

    def test_next_game(self, monkeypatch, schedule):
        self._at(monkeypatch, '2026-11-14T09:00:00')
        assert _display(schedule)._get_next_game()['shortName'] == 'ILL @ DUKE'


class TestSchedule:
    def test_postseason_is_merged_in_date_order(self, monkeypatch, schedule):
        regular = {'events': schedule['events'][:2]}
        post = {'events': [
            {'id': 'p1', 'date': '2027-03-19T17:00Z'},
            dict(schedule['events'][0]),  # a repeat must not duplicate
        ]}
        d = _display(None)
        monkeypatch.setattr(d, '_get_json', lambda url: (
            post if 'seasontype=3' in url else regular))
        assert d._fetch_schedule() is True
        assert [e['id'] for e in d.schedule['events']] == [
            regular['events'][0]['id'], regular['events'][1]['id'], 'p1']

    def test_postseason_failure_keeps_the_regular_season(
            self, monkeypatch, schedule):
        d = _display(None)

        def get(url):
            if 'seasontype=3' in url:
                raise OSError('down')
            return {'events': schedule['events'][:3]}

        monkeypatch.setattr(d, '_get_json', get)
        assert d._fetch_schedule() is True
        assert len(d.schedule['events']) == 3

    def test_regular_season_failure_reports_failure(self, monkeypatch):
        d = _display(None)

        def get(url):
            raise OSError('down')

        monkeypatch.setattr(d, '_get_json', get)
        assert d._fetch_schedule() is False
        assert d.schedule is None


class TestLiveGame:
    def _live_display(self, monkeypatch, schedule, state):
        d = _display(schedule)
        game = _event(schedule, 'SHSU @ ILL')
        monkeypatch.setattr(d, '_get_todays_game', lambda: game)
        fresh = json.loads(json.dumps(game))
        fresh['competitions'][0]['status']['type']['state'] = state
        monkeypatch.setattr(d, '_fetch_live_event', lambda game_id: fresh)
        return d, game

    def test_live_when_scoreboard_says_in(self, monkeypatch, schedule):
        d, game = self._live_display(monkeypatch, schedule, 'in')
        assert d.live_game() is game

    def test_not_live_before_tip_or_after_final(self, monkeypatch, schedule):
        for state in ('pre', 'post'):
            d, _ = self._live_display(monkeypatch, schedule, state)
            assert d.live_game() is None

    def test_no_game_today_makes_no_scoreboard_call(
            self, monkeypatch, schedule):
        d = _display(schedule)
        monkeypatch.setattr(d, '_get_todays_game', lambda: None)
        fetch = Mock()
        monkeypatch.setattr(d, '_fetch_live_event', fetch)
        assert d.live_game() is None
        fetch.assert_not_called()

    def test_scoreboard_error_is_not_live(self, monkeypatch, schedule):
        d = _display(schedule)
        monkeypatch.setattr(
            d, '_get_todays_game', Mock(side_effect=RuntimeError('boom')))
        assert d.live_game() is None

    def test_takeover_leaves_when_the_game_is_no_longer_live(
            self, monkeypatch, schedule):
        """loop_until_final must exit on 'post' - a postponed game never
        reaches STATUS_FINAL and would otherwise hold the panel for hours."""
        d = _display(schedule)
        monkeypatch.setattr(d, '_get_current_scores', lambda game: {
            'status': 'STATUS_POSTPONED', 'state': 'post', 'detail': '',
            'team_score': '0', 'opp_score': '0'})
        monkeypatch.setattr(nd.time, 'sleep', lambda s: None)
        d._display_game_day(_event(schedule, 'SHSU @ ILL'), 0,
                            loop_until_final=True, yield_to=None)
        d.manager.swap_canvas.assert_not_called()

    def test_takeover_shows_the_final_before_releasing(
            self, monkeypatch, schedule):
        d = _display(schedule)
        d._header_bg = d._compact_bg = Mock()
        d._logo_cache = {}
        d.PRIMARY, d.ACCENT = d.team.primary_color, d.team.accent_color
        d.TEXT_WHITE = d.TEXT_GRAY = d.LOSS_RED = (1, 1, 1)
        monkeypatch.setattr(d, '_get_current_scores', lambda game: {
            'status': 'STATUS_FINAL', 'state': 'post', 'detail': 'FINAL',
            'team_score': '70', 'opp_score': '78', 'opp_abbr': 'SHSU',
            'opp_id': '2534', 'team_lines': ['30', '40'],
            'opp_lines': ['38', '40']})
        monkeypatch.setattr(nd.time, 'sleep', lambda s: None)
        d._display_game_day(_event(schedule, 'SHSU @ ILL'), 0,
                            loop_until_final=True, yield_to=None)
        assert d.manager.swap_canvas.call_count == int(
            nd.FINAL_HOLD_SECONDS / nd.FRAME_SECONDS)
        drawn = [call.args[4] for call in d.manager.draw_text.call_args_list]
        assert 'LOSS' in drawn and 'FINAL' in drawn


class TestOffSeasonHooks:
    def _handler(self, config=None, live=False, mlb_active=False):
        import off_season_handler as osh

        h = osh.OffSeasonHandler.__new__(osh.OffSeasonHandler)
        h.config = config or {}
        h.ncaab_display = Mock()
        h.ncaab_display.live_game.return_value = {'id': '1'} if live else None
        h.mlb_game_active = lambda on_error=True: mlb_active
        return h

    def test_live_game_fills_an_idle_screen(self):
        assert self._handler(live=True).ncaab_fills_idle_screen() is True

    def test_mlb_game_keeps_the_screen(self):
        h = self._handler(live=True, mlb_active=True)
        assert h.ncaab_fills_idle_screen() is False

    def test_nothing_to_fill_with_when_not_live(self):
        assert self._handler(live=False).ncaab_fills_idle_screen() is False

    def test_disabled_screen_never_takes_over_or_calls_espn(self):
        h = self._handler(config={'enable_ncaab': False}, live=True)
        assert h.ncaab_fills_idle_screen() is False
        h.ncaab_display.live_game.assert_not_called()

    def test_a_failing_live_check_reads_as_not_live(self):
        h = self._handler(live=True)
        h.ncaab_display.live_game.side_effect = RuntimeError('boom')
        assert h.ncaab_fills_idle_screen() is False


class TestPack:
    def test_default_pack_is_illinois(self):
        from teams import NCAAB_TEAMS, get_active_ncaab_team
        assert get_active_ncaab_team({}).slug == 'illini'
        assert get_active_ncaab_team({'ncaab_team': 'nope'}).slug == 'illini'
        assert NCAAB_TEAMS['illini'].espn_team_id == ILLINI

    def test_kentucky_is_selectable(self):
        from teams import get_active_ncaab_team
        pack = get_active_ncaab_team({'ncaab_team': 'kentucky'})
        assert pack.espn_team_id == '96'
        assert pack.conference_id == '23'
        # White is the body text, so it cannot also be the highlight
        assert pack.accent_color != (255, 255, 255)

    def test_indiana_is_selectable(self):
        from teams import get_active_ncaab_team
        pack = get_active_ncaab_team({'ncaab_team': 'indiana'})
        assert pack.espn_team_id == '84'
        assert pack.conference_id == '7'
        assert pack.accent_color != (255, 255, 255)

    def test_loss_colour_is_not_red_on_a_red_background(self, monkeypatch):
        from teams import NCAAB_TEAMS

        def loss_colour(slug):
            monkeypatch.setattr(nd, 'get_active_ncaab_team',
                                lambda: NCAAB_TEAMS[slug])
            return nd.CollegeBasketballDisplay(Mock()).LOSS_RED

        red, green, blue = loss_colour('indiana')
        assert green > 120  # amber, not red-on-crimson
        assert loss_colour('illini') == (220, 60, 60)

    def test_win_banner_fits_the_panel_for_every_pack(self):
        from scoreboard_config import Fonts
        from teams import NCAAB_TEAMS
        for pack in NCAAB_TEAMS.values():
            banner = f'{pack.short_name.upper()} WIN!'
            assert len(banner) * Fonts.CHAR_WIDTH_STANDARD - 1 <= 96, banner

    def test_every_pack_has_its_assets(self):
        from teams import NCAAB_TEAMS
        for pack in NCAAB_TEAMS.values():
            assert os.path.exists(pack.logo_path), pack.logo_path
            assert pack.logo_path == f'./logos/ncaab/{pack.espn_team_id}.png'
            with open(pack.facts_basename) as f:
                facts = json.load(f)['facts']
            assert len(facts) >= 20
            assert all(fact == fact.upper() for fact in facts)
            assert pack.win_chant
            # The full-size header font holds 13 characters
            assert len(pack.header_name) <= 13

    def test_every_scheduled_opponent_has_a_logo(self, schedule):
        for event in schedule['events']:
            _, opponent = nd.split_competitors(
                event['competitions'][0], ILLINI)
            path = f"./logos/ncaab/{opponent['team']['id']}.png"
            assert os.path.exists(path), event['shortName']

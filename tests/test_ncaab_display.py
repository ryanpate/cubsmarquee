"""College basketball screens: ESPN parsing, season gating, live takeover.

The JSON under tests/data/ncaab_*.json is recorded ESPN output (2026-11-12;
ncaab_live_running_event.json 2026-11-27), trimmed of logo and link arrays.
"""

from __future__ import annotations

import json
import os
import time as real_time
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


class _FakeTime:
    """Stands in for the time module inside ncaab_display. Sleeping moves
    the clock on at once; the short real pause lets the background score
    fetch land before the next frame."""

    def __init__(self):
        self.now = 1000.0

    def time(self):
        return self.now

    monotonic = time

    def sleep(self, seconds):
        self.now += seconds
        real_time.sleep(0.001)


def _play(type_text, text=''):
    return {'type': {'text': type_text}, 'text': text}


class TestClockRuns:
    def test_runs_after_a_live_ball_play(self):
        for play in ('JumpShot', 'LayUpShot', 'DunkShot', 'TipShot',
                     'Block Shot', 'Defensive Rebound', 'Offensive Rebound',
                     'Steal', 'Jumpball'):
            assert nd.clock_runs_after(_play(play), period=1, clock=600), play

    def test_stopped_after_a_whistle(self):
        for play in ('PersonalFoul', 'Technical Foul', 'MadeFreeThrow',
                     'OfficialTVTimeOut', 'ShortTimeOut', 'RegularTimeOut',
                     'Substitution', 'Dead Ball Rebound',
                     'Lost Ball Turnover', 'End Period'):
            assert not nd.clock_runs_after(
                _play(play), period=1, clock=600), play

    def test_stopped_when_espn_names_no_play(self):
        assert not nd.clock_runs_after(None, period=1, clock=600)
        assert not nd.clock_runs_after({}, period=1, clock=600)

    def test_made_basket_stops_the_clock_in_the_final_minute(self):
        made = _play('LayUpShot', 'Kylan Boswell makes layup')
        missed = _play('LayUpShot', 'Kylan Boswell misses layup')
        assert not nd.clock_runs_after(made, period=2, clock=45)
        assert not nd.clock_runs_after(made, period=3, clock=45)  # overtime
        assert nd.clock_runs_after(made, period=1, clock=45)
        assert nd.clock_runs_after(made, period=2, clock=75)
        assert nd.clock_runs_after(missed, period=2, clock=45)


def _tl(*plays):
    """A timeline from (period, clock, at, running) rows, with an optional
    fifth item of extra fields"""
    timeline = nd.PlayTimeline()
    for period, clock, at, running, *extra in plays:
        timeline.add(dict({
            'period': period, 'clock': float(clock), 'at': float(at),
            'running': running, 'over': False, 'home': 0, 'away': 0},
            **(extra[0] if extra else {})))
    return timeline


def _clock(timeline, moment):
    reading = timeline.at(moment)
    return reading['period'], reading['seconds']


class TestPlayTimeline:
    def test_empty_timeline_has_no_reading(self):
        assert nd.PlayTimeline().at(1000) is None

    def test_clock_holds_after_a_whistle(self):
        timeline = _tl((1, 850, 1000, False))
        assert _clock(timeline, 1090) == (1, 850)

    def test_clock_counts_down_from_when_the_play_happened(self):
        timeline = _tl((1, 850, 1000, True))
        assert _clock(timeline, 1000) == (1, 850)
        assert _clock(timeline, 1000.9) == (1, 850)
        assert _clock(timeline, 1001) == (1, 849)
        assert _clock(timeline, 1007.5) == (1, 843)

    def test_never_runs_past_one_shot_clock(self):
        """A live ball must produce a play within 30 seconds; silence
        beyond that means the feed stalled, not that the game ran on."""
        timeline = _tl((1, 850, 1000, True))
        assert _clock(timeline, 1300) == (1, 850 - nd.SHOT_CLOCK_SECONDS)

    def test_never_runs_below_zero(self):
        timeline = _tl((2, 5, 1000, True))
        assert _clock(timeline, 1020) == (2, 0)

    def test_stops_at_the_next_play_already_known(self):
        """The whistle was logged at 14:00 but reached ESPN 20 seconds
        after the shot; the count must not run on past it."""
        timeline = _tl((1, 850, 1000, True), (1, 840, 1020, False))
        assert _clock(timeline, 1005) == (1, 845)
        assert _clock(timeline, 1015) == (1, 840)
        assert _clock(timeline, 1020) == (1, 840)

    def test_restarts_in_time_to_reach_the_next_play(self):
        """After a whistle the inbound is never logged, but a known next
        play says when the clock must have started again."""
        timeline = _tl((1, 850, 1000, False), (1, 835, 1040, True))
        assert _clock(timeline, 1020) == (1, 850)
        assert _clock(timeline, 1030) == (1, 845)
        assert _clock(timeline, 1040) == (1, 835)

    def test_before_the_first_known_play_holds_its_clock(self):
        timeline = _tl((1, 1200, 1000, True))
        assert _clock(timeline, 980) == (1, 1200)

    def test_a_play_entered_late_does_not_turn_the_clock_back(self):
        timeline = _tl((1, 850, 1000, False), (1, 900, 1010, False))
        assert _clock(timeline, 1020) == (1, 850)

    def test_a_play_stamped_before_the_last_one_counts_from_it(self):
        timeline = _tl((1, 850, 1000, False), (1, 850, 990, True))
        assert _clock(timeline, 1003) == (1, 847)

    def test_a_new_period_starts_from_its_own_clock(self):
        timeline = _tl((1, 0, 1000, False), (2, 1200, 2000, True))
        assert _clock(timeline, 1500) == (1, 0)
        assert _clock(timeline, 2003) == (2, 1197)

    def test_score_is_the_one_at_that_moment(self):
        timeline = _tl(
            (1, 850, 1000, True, {'home': 10, 'away': 8}),
            (1, 830, 1020, True, {'home': 12, 'away': 8}))
        assert timeline.at(1019)['home'] == 10
        assert timeline.at(1020)['home'] == 12
        assert timeline.at(1020)['away'] == 8

    def test_caught_up_once_the_last_play_has_been_shown(self):
        timeline = _tl((1, 850, 1000, True), (1, 840, 1020, False))
        assert not timeline.caught_up(1019)
        assert timeline.caught_up(1020)

    def test_period_over_after_its_end_play(self):
        timeline = _tl((1, 3, 1000, True),
                       (1, 0, 1004, False, {'over': True}))
        assert not timeline.at(1003)['over']
        assert timeline.at(1004)['over']


class TestPlayParsing:
    def test_recorded_made_shot(self):
        play = nd.parse_play(_fixture('ncaab_plays.json')['items'][0])
        assert play['period'] == 1
        assert play['clock'] == 1187.0
        assert play['at'] == pendulum.parse(
            '2026-11-27T23:01:48Z').timestamp()
        assert play['running'] is True
        assert play['over'] is False
        assert (play['home'], play['away']) == (0, 3)

    def test_recorded_foul_stops_the_clock(self):
        play = nd.parse_play(_fixture('ncaab_plays.json')['items'][1])
        assert play['running'] is False
        assert (play['home'], play['away']) == (2, 3)

    def test_end_of_period(self):
        item = dict(_fixture('ncaab_plays.json')['items'][1],
                    type={'id': '412', 'text': 'End Period'})
        assert nd.parse_play(item)['over'] is True

    def test_play_without_a_timestamp_is_skipped(self):
        item = dict(_fixture('ncaab_plays.json')['items'][0])
        del item['wallclock']
        assert nd.parse_play(item) is None

    def test_period_label(self):
        assert [nd.period_label(n) for n in (1, 2, 3, 4)] == [
            '1ST', '2ND', 'OT', '2OT']

    def test_format_clock(self):
        assert nd.format_clock(755) == '12:35'
        assert nd.format_clock(9) == '0:09'
        assert nd.format_clock(0) == '0:00'


class TestPlayFetch:
    """_fetch_plays against a fake ESPN holding `total` plays"""

    def _espn(self, monkeypatch, total):
        d = _display()
        item = _fixture('ncaab_plays.json')['items'][0]
        urls = []

        def get(url):
            urls.append(url.split('/plays')[1])
            query = dict(pair.split('=') for pair in
                         url.split('?')[1].split('&'))
            limit, page = int(query['limit']), int(query.get('page', 1))
            first = (page - 1) * limit
            return {'count': total[0], 'items': [
                dict(item, id=str(n))
                for n in range(first, min(first + limit, total[0]))]}

        monkeypatch.setattr(d, '_get_json_once', get)
        return d, urls

    def test_first_fetch_loads_recent_history(self, monkeypatch):
        d, urls = self._espn(monkeypatch, [60])
        seen, plays = d._fetch_plays('1', None)
        assert seen == 60
        assert len(plays) == 35  # the last two pages of 25: plays 25-59
        assert urls == ['?limit=1', '?limit=25&page=2', '?limit=25&page=3']

    def test_nothing_new_costs_one_small_request(self, monkeypatch):
        d, urls = self._espn(monkeypatch, [60])
        assert d._fetch_plays('1', 60) == (60, [])
        assert urls == ['?limit=1']

    def test_new_plays_are_fetched_one_by_one(self, monkeypatch):
        """A page of one has its own URL per play, so ESPN's 10-second
        cache of the shared last page cannot hide a new play."""
        d, urls = self._espn(monkeypatch, [62])
        seen, plays = d._fetch_plays('1', 60)
        assert seen == 62 and len(plays) == 2
        assert urls == ['?limit=1', '?limit=1&page=61', '?limit=1&page=62']

    def test_a_long_gap_reloads_history_instead(self, monkeypatch):
        d, urls = self._espn(monkeypatch, [100])
        seen, plays = d._fetch_plays('1', 60)
        assert seen == 100
        assert urls == ['?limit=1', '?limit=25&page=3', '?limit=25&page=4']

    def test_a_deleted_play_lowers_the_count(self, monkeypatch):
        d, _ = self._espn(monkeypatch, [59])
        assert d._fetch_plays('1', 60) == (59, [])

    def test_failure_keeps_the_old_count(self, monkeypatch):
        d = _display()
        monkeypatch.setattr(
            d, '_get_json_once', Mock(side_effect=RuntimeError('boom')))
        assert d._fetch_plays('1', 60) == (60, [])


class TestHomeAway:
    """The play-by-play scores are home and away; the screen wants the
    team's own and the opponent's"""

    def _scores(self, monkeypatch, team_id):
        d = _display()
        event = _fixture('ncaab_live_running_event.json')  # WKU @ ILL
        d.team = Mock(espn_team_id=team_id)
        monkeypatch.setattr(d, '_fetch_live_event', lambda game_id: event)
        return d._get_current_scores(event)

    def test_home_team(self, monkeypatch):
        scores = self._scores(monkeypatch, ILLINI)
        assert scores['team_home'] is True
        assert (scores['team_score'], scores['opp_score']) == ('16', '12')

    def test_away_team(self, monkeypatch):
        scores = self._scores(monkeypatch, '98')
        assert scores['team_home'] is False
        assert (scores['team_score'], scores['opp_score']) == ('12', '16')


class TestDelayedScores:
    SCORES = {'status': 'STATUS_IN_PROGRESS', 'state': 'in',
              'detail': '11:39 - 1ST', 'team_score': '20', 'opp_score': '14',
              'team_home': True}

    def test_clock_and_score_come_from_the_delayed_timeline(self):
        timeline = _tl((1, 760, 1000, True, {'home': 16, 'away': 12}))
        view = nd.delayed_scores(self.SCORES, timeline, 1005)
        assert view['detail'] == '12:35 - 1ST'
        assert (view['team_score'], view['opp_score']) == ('16', '12')

    def test_away_team_reads_the_away_score(self):
        timeline = _tl((1, 760, 1000, True, {'home': 16, 'away': 12}))
        view = nd.delayed_scores(
            dict(self.SCORES, team_home=False), timeline, 1005)
        assert (view['team_score'], view['opp_score']) == ('12', '16')

    def test_without_plays_espns_own_line_is_shown(self):
        view = nd.delayed_scores(self.SCORES, nd.PlayTimeline(), 1005)
        assert view == self.SCORES

    def test_halftime_waits_for_the_delayed_clock_to_run_out(self):
        halftime = dict(self.SCORES, status='STATUS_HALFTIME',
                        detail='HALFTIME')
        timeline = _tl((1, 20, 1000, True),
                       (1, 0, 1020, False, {'over': True}))
        assert nd.delayed_scores(
            halftime, timeline, 1010)['detail'] == '0:10 - 1ST'
        assert nd.delayed_scores(
            halftime, timeline, 1021)['detail'] == 'HALFTIME'

    def test_break_text_does_not_wait_for_espns_status(self):
        """ESPN's status flips to the second half up to 30 seconds before
        the delayed screen gets there."""
        timeline = _tl((1, 0, 1000, False, {'over': True}))
        assert nd.delayed_scores(
            self.SCORES, timeline, 1500)['detail'] == 'HALFTIME'
        overtime = _tl((2, 0, 1000, False, {'over': True}))
        assert nd.delayed_scores(
            self.SCORES, overtime, 1500)['detail'] == 'END OF 2ND'

    def test_espns_status_shows_once_caught_up_if_no_end_play_came(self):
        delayed = dict(self.SCORES, status='STATUS_DELAYED', detail='DELAYED')
        timeline = _tl((1, 300, 1000, False))
        assert nd.delayed_scores(
            delayed, timeline, 1500)['detail'] == 'DELAYED'


class TestLiveScreen:
    """The live loop on a fake clock, with ESPN answering from a script"""

    def _run(self, monkeypatch, schedule, duration, plays_at=None,
             status_at=None, yield_to=None, loop_until_final=False):
        """plays_at(now) -> list of timeline rows known by then;
        status_at(now) -> overrides for the status feed"""
        d = _display(schedule)
        d._header_bg = d._compact_bg = Mock()
        d._logo_cache = {}
        d.PRIMARY, d.ACCENT = d.team.primary_color, d.team.accent_color
        d.TEXT_WHITE = d.TEXT_GRAY = d.LOSS_RED = (1, 1, 1)
        monkeypatch.setattr(d, '_play_win_celebration', lambda: None)
        clock = _FakeTime()
        monkeypatch.setattr(nd, 'time', clock)
        calls = []

        def scores(game):
            calls.append(clock.now)
            return dict({
                'status': 'STATUS_IN_PROGRESS', 'state': 'in',
                'detail': '9:99 - ESPN', 'team_score': '99',
                'opp_score': '98', 'opp_abbr': 'SHSU', 'opp_id': '2534',
                'team_home': True, 'team_lines': ['30', '40'],
                'opp_lines': ['38', '40']},
                **(status_at(clock.now) if status_at else {}))

        def plays(game_id, seen):
            rows = plays_at(clock.now) if plays_at else []
            seen = seen or 0
            return len(rows), [
                {'period': r[0], 'clock': float(r[1]), 'at': float(r[2]),
                 'running': r[3], 'over': False, 'home': r[4], 'away': r[5]}
                for r in rows[seen:]]

        monkeypatch.setattr(d, '_get_current_scores', scores)
        monkeypatch.setattr(d, '_fetch_plays', plays)
        started = clock.now
        d._display_game_day(_event(schedule, 'SHSU @ ILL'), duration,
                            loop_until_final=loop_until_final,
                            yield_to=yield_to)
        drawn = [call.args[4] for call in d.manager.draw_text.call_args_list]
        return drawn, calls, clock.now - started

    START = 1000.0  # _FakeTime's first reading

    def test_clock_ticks_thirty_seconds_behind(self, monkeypatch, schedule):
        """A live-ball play logged 30 seconds ago is 'now' on the panel"""
        delay = nd.LIVE_DELAY_SECONDS
        drawn, _, _ = self._run(
            monkeypatch, schedule, duration=3.5, plays_at=lambda now: [
                (1, 850, self.START - delay, True, 16, 12)])
        ticks = [text for text in drawn if text.endswith(' - 1ST')]
        assert list(dict.fromkeys(ticks)) == [
            '14:10 - 1ST', '14:09 - 1ST', '14:08 - 1ST', '14:07 - 1ST']

    def test_score_stays_in_step_with_the_delayed_clock(
            self, monkeypatch, schedule):
        """A basket ESPN reports now reaches the panel when the delayed
        clock gets to it, not before."""
        delay = nd.LIVE_DELAY_SECONDS
        drawn, _, _ = self._run(
            monkeypatch, schedule, duration=10, plays_at=lambda now: [
                (1, 850, self.START - delay, True, 16, 12),
                (1, 845, self.START - delay + 5, True, 18, 12)])
        scores = [text for text in drawn if text in ('16', '18', '99')]
        assert '99' not in scores  # ESPN's undelayed status score
        assert scores[0] == '16' and scores[-1] == '18'
        first_18 = drawn.index('18')
        assert '14:06 - 1ST' in drawn[:first_18]
        assert '14:05 - 1ST' in drawn[first_18:first_18 + 12]

    def test_without_plays_espns_own_line_is_shown(
            self, monkeypatch, schedule):
        drawn, _, _ = self._run(monkeypatch, schedule, duration=2)
        assert '9:99 - ESPN' in drawn and '99' in drawn

    def test_feeds_are_asked_every_few_seconds(self, monkeypatch, schedule):
        _, calls, _ = self._run(monkeypatch, schedule, duration=20.5)
        assert len(calls) == 1 + 20 // nd.LIVE_UPDATE_SECONDS
        assert nd.LIVE_UPDATE_SECONDS <= 5

    def test_a_play_arriving_mid_screen_is_used(self, monkeypatch, schedule):
        delay = nd.LIVE_DELAY_SECONDS

        def plays_at(now):
            rows = [(1, 850, self.START - delay, False, 16, 12)]
            if now >= self.START + 6:
                rows.append((1, 838, self.START - delay + 12, False, 16, 14))
            return rows

        drawn, _, _ = self._run(
            monkeypatch, schedule, duration=14, plays_at=plays_at)
        assert '13:58 - 1ST' in drawn and '14' in drawn

    def test_takeover_outlasts_espns_final_by_the_delay(
            self, monkeypatch, schedule):
        """ESPN calls the game over 30 seconds before the delayed screen
        has shown its last play."""
        delay = nd.LIVE_DELAY_SECONDS
        final_at = self.START + 8

        def status_at(now):
            if now < final_at:
                return {}
            return {'status': 'STATUS_FINAL', 'state': 'post',
                    'detail': 'FINAL', 'team_score': '70',
                    'opp_score': '78'}

        drawn, _, elapsed = self._run(
            monkeypatch, schedule, duration=0, status_at=status_at,
            loop_until_final=True, plays_at=lambda now: [
                (2, 20, self.START - delay, True, 68, 78),
                (2, 3, final_at + 2 - delay + 15, True, 70, 78)])
        assert '0:03 - 2ND' in drawn
        assert drawn.index('0:03 - 2ND') < drawn.index('FINAL')
        assert elapsed >= 8 + delay

    def test_hand_back_is_checked_no_more_often_than_before(
            self, monkeypatch, schedule):
        """yield_to asks other sports' APIs; the faster score poll must
        not multiply those requests."""
        yield_to = Mock(return_value=False)
        self._run(monkeypatch, schedule, duration=41, yield_to=yield_to)
        assert yield_to.call_count == 2

    def test_hand_back_ends_the_screen(self, monkeypatch, schedule):
        _, _, elapsed = self._run(
            monkeypatch, schedule, duration=600, yield_to=lambda: True)
        assert elapsed < 30


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

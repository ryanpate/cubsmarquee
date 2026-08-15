"""NFL preseason detection and MLB/NFL precedence"""

from __future__ import annotations

import json
import time

import pendulum


def _event(days_from_now, state='pre', game_id='401'):
    """An ESPN schedule event N days from now, in the shape the code reads."""
    when = pendulum.now('America/Chicago').add(days=days_from_now)
    return {
        'id': game_id,
        'date': when.to_iso8601_string(),
        'shortName': 'CLE @ CHI',
        'competitions': [
            {'status': {'type': {'name': 'STATUS_SCHEDULED', 'state': state}}}
        ],
    }


def _make_bears(events, fetch_ok=True):
    import bears_display as bd
    d = bd.BearsDisplay.__new__(bd.BearsDisplay)
    d.bears_data = {'events': list(events)} if fetch_ok else None
    d.last_update = time.time()
    d.update_interval = 3600
    d.live_update_interval = 30
    return d


class TestFootballSeasonWindow:
    def test_game_today_is_in_season(self):
        assert _make_bears([_event(0)]).has_game_within() is True

    def test_game_next_week_is_in_season(self):
        assert _make_bears([_event(7)]).has_game_within() is True

    def test_game_a_month_out_is_not_in_season(self):
        # ESPN publishes next season's schedule months early; a bare
        # "any events?" check would put NFL content up in the spring.
        assert _make_bears([_event(30)]).has_game_within() is False

    def test_game_two_days_ago_still_counts(self):
        assert _make_bears([_event(-2)]).has_game_within() is True

    def test_empty_schedule_is_not_in_season(self):
        assert _make_bears([]).has_game_within() is False

    def test_unreachable_schedule_falls_back_to_month_gate(self, monkeypatch):
        # A network blip must not silently hide all NFL content.
        import bears_display as bd
        d = _make_bears([], fetch_ok=False)
        monkeypatch.setattr(d, '_should_update_schedule', lambda: True)
        monkeypatch.setattr(d, '_fetch_bears_schedule', lambda: False)
        monkeypatch.setattr(bd, 'extended_month_gate', lambda: True)
        assert d.has_game_within() is True


class TestExtendedMonthGate:
    def test_august_counts_as_football(self, monkeypatch):
        import bears_display as bd
        monkeypatch.setattr(
            bd.pendulum, 'now',
            lambda *a, **k: pendulum.datetime(2026, 8, 15, tz='America/Chicago'))
        assert bd.extended_month_gate() is True

    def test_may_does_not(self, monkeypatch):
        import bears_display as bd
        monkeypatch.setattr(
            bd.pendulum, 'now',
            lambda *a, **k: pendulum.datetime(2026, 5, 15, tz='America/Chicago'))
        assert bd.extended_month_gate() is False


class TestLiveGameDetection:
    def _ready(self, monkeypatch, events, scoreboard_state):
        d = _make_bears(events)
        monkeypatch.setattr(d, '_should_update_schedule', lambda: False)
        if scoreboard_state is None:
            monkeypatch.setattr(d, '_fetch_live_scores', lambda gid: None)
        else:
            monkeypatch.setattr(
                d, '_fetch_live_scores',
                lambda gid: {'competitions': [
                    {'status': {'type': {'state': scoreboard_state}}}]})
        return d

    def test_in_progress_game_is_live(self, monkeypatch):
        d = self._ready(monkeypatch, [_event(0)], 'in')
        assert d.live_game() is not None

    def test_scheduled_game_is_not_live(self, monkeypatch):
        d = self._ready(monkeypatch, [_event(0)], 'pre')
        assert d.live_game() is None

    def test_finished_game_is_not_live(self, monkeypatch):
        d = self._ready(monkeypatch, [_event(0)], 'post')
        assert d.live_game() is None

    def test_no_game_today_is_not_live(self, monkeypatch):
        d = self._ready(monkeypatch, [_event(5)], 'in')
        assert d.live_game() is None

    def test_falls_back_to_schedule_state_when_scoreboard_is_down(
            self, monkeypatch):
        # _fetch_live_scores returning None must not crash the guard; the
        # schedule event's own state is the fallback.
        d = self._ready(monkeypatch, [_event(0, state='in')], None)
        assert d.live_game() is not None


class TestTakeoverRouting:
    def _routed(self, monkeypatch, **kwargs):
        """Record which display branch display_bears_info picks."""
        d = _make_bears([_event(0)])
        calls = []
        monkeypatch.setattr(d, '_should_update_schedule', lambda: False)
        monkeypatch.setattr(
            d, '_display_game_day',
            lambda g, dur, loop_until_final=False: calls.append(
                ('game_day', loop_until_final)))
        monkeypatch.setattr(
            d, '_display_next_game',
            lambda g, dur: calls.append(('next_game', False)))
        d.display_bears_info(**kwargs)
        return calls

    def test_default_shows_the_live_game_card(self, monkeypatch):
        assert self._routed(monkeypatch) == [('game_day', False)]

    def test_loop_until_final_is_forwarded(self, monkeypatch):
        assert self._routed(
            monkeypatch, loop_until_final=True) == [('game_day', True)]

    def test_force_scheduled_shows_the_scheduled_card(self, monkeypatch):
        assert self._routed(
            monkeypatch, force_scheduled=True) == [('next_game', False)]


class _CeilingManager:
    """Stub ScoreboardManager that counts drawn frames and blows up past a
    ceiling, so a regression to an infinite takeover loop fails the test
    loudly instead of hanging the suite forever."""

    def __init__(self, max_iters):
        self.max_iters = max_iters
        self.iters = 0

    def clear_canvas(self):
        pass

    def swap_canvas(self):
        self.iters += 1
        if self.iters > self.max_iters:
            raise RuntimeError(
                'takeover loop exceeded the test iteration ceiling - '
                'looks like an infinite loop')

    def set_image(self, *a, **k):
        pass

    def draw_text(self, *a, **k):
        pass

    def draw_pixel(self, *a, **k):
        pass

    def get_frame_copy(self):
        return None


class TestTakeoverBackstop:
    """Covers the fix for a Critical review finding: the takeover loop's
    score refresh was gated on score_data['status'] == 'STATUS_IN_PROGRESS',
    so a live-but-not-that-string status (e.g. ESPN's STATUS_HALFTIME) would
    never refresh again, status could never reach STATUS_FINAL, and the only
    exit was process shutdown."""

    def _score(self, status):
        return {
            'status': status,
            'game_time': '1:23 - 2ND',
            'bears_score': '7',
            'opp_score': '0',
            'opponent_abbr': 'CLE',
            'opponent_name': 'Browns',
            'possession': None,
            'down_distance': None,
            'is_red_zone': False,
            'last_play': None,
        }

    def _run(self, monkeypatch, statuses, loop_until_final=True,
              duration=999999, max_iters=500):
        """Run _display_game_day against a scripted status sequence (each
        call to _get_current_scores advances one step, holding the last
        entry once exhausted). Every drawing/sleeping call is stubbed so
        nothing touches hardware or real time, and the manager enforces a
        hard iteration ceiling so a hung loop fails fast."""
        import bears_display as bd
        d = bd.BearsDisplay.__new__(bd.BearsDisplay)
        d.manager = _CeilingManager(max_iters)
        d.live_update_interval = 0

        game = _event(0)
        calls = {'n': 0}

        def fake_scores(g, gid):
            i = min(calls['n'], len(statuses) - 1)
            calls['n'] += 1
            return self._score(statuses[i])

        monkeypatch.setattr(d, '_get_current_scores', fake_scores)
        monkeypatch.setattr(
            d, '_maybe_play_win_celebration', lambda sd, played: played)
        monkeypatch.setattr(d, '_play_scoring_celebration', lambda delta: None)
        monkeypatch.setattr(d, '_draw_sweater_header', lambda: None)
        monkeypatch.setattr(d, '_draw_live_content', lambda *a, **k: None)
        monkeypatch.setattr(d, '_draw_final_content', lambda *a, **k: None)
        monkeypatch.setattr(d, '_draw_pregame_content', lambda *a, **k: None)
        monkeypatch.setattr(d, '_scroll_last_play', lambda text: None)
        monkeypatch.setattr(bd.time, 'sleep', lambda s: None)
        monkeypatch.setattr(bd, 'is_shutdown_requested', lambda: False)

        d._display_game_day(
            game, duration, loop_until_final=loop_until_final)
        return calls['n'], d.manager.iters

    def test_takeover_exits_on_final_after_a_few_refreshes(self, monkeypatch):
        fetches, frames = self._run(
            monkeypatch,
            ['STATUS_IN_PROGRESS', 'STATUS_IN_PROGRESS', 'STATUS_FINAL'])
        assert fetches == 3
        assert frames <= 5

    def test_takeover_does_not_hang_at_halftime(self, monkeypatch):
        # Without the refresh-gate fix, status gets stuck at
        # 'STATUS_HALFTIME' forever (the refresh block only fires when
        # status == 'STATUS_IN_PROGRESS'), so this would exhaust the
        # iteration ceiling and fail with the manager's RuntimeError rather
        # than ever reaching STATUS_FINAL.
        fetches, frames = self._run(
            monkeypatch,
            ['STATUS_IN_PROGRESS', 'STATUS_HALFTIME', 'STATUS_HALFTIME',
             'STATUS_FINAL'])
        assert fetches == 4
        assert frames <= 5

    def test_non_takeover_path_still_exits_after_duration(self, monkeypatch):
        # Deterministic fake clock: each time.time() call advances by a
        # fixed step, so the duration bound is exercised without relying on
        # real wall-clock time.
        import bears_display as bd
        clock = {'t': 0.0}

        def fake_time():
            clock['t'] += 1.0
            return clock['t']

        monkeypatch.setattr(bd.time, 'time', fake_time)
        try:
            fetches, frames = self._run(
                monkeypatch,
                ['STATUS_HALFTIME'] * 10,
                loop_until_final=False,
                duration=2.5)
        finally:
            pass

        # Status never reaches STATUS_IN_PROGRESS, so the (unchanged)
        # non-takeover refresh gate must never re-fetch - only the initial
        # fetch before the loop happens - and the loop must still end on
        # its own via the duration bound, not the iteration ceiling.
        assert fetches == 1
        assert frames < 500


def _score_dict(status, state=None):
    """A _get_current_scores return value, optionally carrying ESPN's
    coarse state field ('pre' / 'in' / 'post')."""
    score = {
        'status': status,
        'game_time': '1:23 - 2ND',
        'bears_score': '7',
        'opp_score': '0',
        'opponent_abbr': 'CLE',
        'opponent_name': 'Browns',
        'possession': None,
        'down_distance': None,
        'is_red_zone': False,
        'last_play': None,
    }
    if state is not None:
        score['state'] = state
    return score


def _drive_game_day(monkeypatch, scores, loop_until_final=True,
                    duration=999999, max_iters=500):
    """Run _display_game_day against a scripted sequence of score dicts.

    Each call to _get_current_scores advances one step, holding the last
    entry once exhausted. Drawing and sleeping are stubbed, and the manager
    enforces a hard iteration ceiling so a hung loop fails fast.
    """
    import bears_display as bd
    d = bd.BearsDisplay.__new__(bd.BearsDisplay)
    d.manager = _CeilingManager(max_iters)
    d.live_update_interval = 0
    calls = {'n': 0}

    def fake_scores(g, gid):
        i = min(calls['n'], len(scores) - 1)
        calls['n'] += 1
        return scores[i]

    monkeypatch.setattr(d, '_get_current_scores', fake_scores)
    monkeypatch.setattr(
        d, '_maybe_play_win_celebration', lambda sd, played: played)
    monkeypatch.setattr(d, '_play_scoring_celebration', lambda delta: None)
    monkeypatch.setattr(d, '_draw_sweater_header', lambda: None)
    monkeypatch.setattr(d, '_draw_live_content', lambda *a, **k: None)
    monkeypatch.setattr(d, '_draw_final_content', lambda *a, **k: None)
    monkeypatch.setattr(d, '_draw_pregame_content', lambda *a, **k: None)
    monkeypatch.setattr(d, '_scroll_last_play', lambda text: None)
    monkeypatch.setattr(bd.time, 'sleep', lambda s: None)
    monkeypatch.setattr(bd, 'is_shutdown_requested', lambda: False)

    d._display_game_day(_event(0), duration, loop_until_final=loop_until_final)
    return calls['n'], d.manager.iters


class TestTakeoverTerminalStates:
    """The takeover is entered on status.type.state == 'in', so it has to
    leave on state != 'in'. ESPN's terminal 'post' state covers more names
    than STATUS_FINAL - a game canceled or suspended after kickoff would
    otherwise hold the screen for the full six-hour backstop, drawing an
    'UP NEXT' card for a game that will never resume."""

    def test_canceled_after_kickoff_exits_the_takeover(self, monkeypatch):
        fetches, frames = _drive_game_day(monkeypatch, [
            _score_dict('STATUS_IN_PROGRESS', 'in'),
            _score_dict('STATUS_CANCELED', 'post'),
        ])
        assert fetches == 2
        assert frames <= 3

    def test_suspended_after_kickoff_exits_the_takeover(self, monkeypatch):
        fetches, frames = _drive_game_day(monkeypatch, [
            _score_dict('STATUS_IN_PROGRESS', 'in'),
            _score_dict('STATUS_SUSPENDED', 'post'),
        ])
        assert fetches == 2
        assert frames <= 3

    def test_final_overtime_exits_the_takeover(self, monkeypatch):
        fetches, frames = _drive_game_day(monkeypatch, [
            _score_dict('STATUS_IN_PROGRESS', 'in'),
            _score_dict('STATUS_FINAL_OVERTIME', 'post'),
        ])
        assert fetches == 2
        assert frames <= 3

    def test_live_states_keep_the_takeover_running(self, monkeypatch):
        # Halftime is still state 'in' - the takeover must hold the screen.
        fetches, frames = _drive_game_day(monkeypatch, [
            _score_dict('STATUS_IN_PROGRESS', 'in'),
            _score_dict('STATUS_HALFTIME', 'in'),
            _score_dict('STATUS_END_PERIOD', 'in'),
            _score_dict('STATUS_FINAL', 'post'),
        ])
        assert fetches == 4
        assert frames <= 5

    def test_non_takeover_ignores_state_and_honors_duration(self, monkeypatch):
        # loop_until_final=False must still exit purely on duration, even
        # when the state has gone terminal.
        import bears_display as bd
        clock = {'t': 0.0}

        def fake_time():
            clock['t'] += 1.0
            return clock['t']

        monkeypatch.setattr(bd.time, 'time', fake_time)
        fetches, frames = _drive_game_day(
            monkeypatch,
            [_score_dict('STATUS_CANCELED', 'post')] * 5,
            loop_until_final=False,
            duration=2.5)
        assert fetches == 1
        assert 0 < frames < 500


class TestMlbInProgress:
    def _handler(self, schedule, config=None):
        import off_season_handler as osh

        class _FakeManager:
            def get_schedule(self_inner):
                if isinstance(schedule, Exception):
                    raise schedule
                return schedule

        h = osh.OffSeasonHandler.__new__(osh.OffSeasonHandler)
        h.manager = _FakeManager()
        h.config = config or {}
        h._mlb_status_cached = False
        h._mlb_status_checked = None
        return h

    def test_in_progress_game_is_detected(self):
        assert self._handler([{'status': 'In Progress'}])._mlb_in_progress()

    def test_replay_review_counts_as_in_progress(self):
        # route_by_status treats challenges/reviews as mid-game states.
        h = self._handler([{'status': 'Manager challenge: Force play'}])
        assert h._mlb_in_progress() is True

    def test_scheduled_game_is_not_in_progress(self):
        assert self._handler([{'status': 'Scheduled'}])._mlb_in_progress() is False

    def test_schedule_error_does_not_suppress_nfl(self):
        # Failing open here keeps live NFL scores on screen.
        h = self._handler(RuntimeError('statsapi down'))
        assert h._mlb_in_progress() is False

    def test_result_is_cached_within_the_ttl(self):
        calls = []
        import off_season_handler as osh

        class _CountingManager:
            def get_schedule(self_inner):
                calls.append(1)
                return [{'status': 'In Progress'}]

        h = osh.OffSeasonHandler.__new__(osh.OffSeasonHandler)
        h.manager = _CountingManager()
        h.config = {}
        h._mlb_status_cached = False
        h._mlb_status_checked = None
        assert h._mlb_in_progress() is True
        assert h._mlb_in_progress() is True
        assert len(calls) == 1


class TestPreemptGuard:
    def _board(self, tmp_path, config, live):
        import main as m
        path = tmp_path / 'config.json'
        path.write_text(json.dumps(config))

        class _FakeBears:
            def live_game(self_inner):
                return {'id': '401'} if live else None

        class _FakeHandler:
            bears_display = _FakeBears()

        board = m.CubsScoreboard.__new__(m.CubsScoreboard)
        board.off_season_handler = _FakeHandler()
        return board, str(path)

    def test_preempts_when_enabled_and_nfl_is_live(self, tmp_path):
        board, path = self._board(tmp_path, {'nfl_preempt_mlb': True}, live=True)
        assert board._nfl_preempts(config_path=path) is True

    def test_does_not_preempt_when_option_is_off(self, tmp_path):
        board, path = self._board(
            tmp_path, {'nfl_preempt_mlb': False}, live=True)
        assert board._nfl_preempts(config_path=path) is False

    def test_does_not_preempt_when_no_nfl_game_is_live(self, tmp_path):
        board, path = self._board(
            tmp_path, {'nfl_preempt_mlb': True}, live=False)
        assert board._nfl_preempts(config_path=path) is False

    def test_defaults_to_off_when_key_is_absent(self, tmp_path):
        board, path = self._board(tmp_path, {}, live=True)
        assert board._nfl_preempts(config_path=path) is False

    def test_missing_config_file_does_not_preempt(self, tmp_path):
        board, _ = self._board(tmp_path, {'nfl_preempt_mlb': True}, live=True)
        assert board._nfl_preempts(
            config_path=str(tmp_path / 'nope.json')) is False


def _advancing_sleep(clock, sleeps):
    """A time.sleep stub that records the request and advances a fake clock."""
    def _sleep(seconds):
        sleeps.append(seconds)
        clock['t'] += seconds
    return _sleep


class TestPreemptDwell:
    """Covers a Critical review finding: display_bears_info has early-return
    paths (a failed schedule fetch returns before anything is drawn), so a
    dead ESPN schedule endpoint plus a scoreboard still reporting 'in' would
    spin the preempt branch at network speed with a frozen panel. The branch
    must floor each pass."""

    def _run_loop(self, monkeypatch, iterations=4):
        import main as m

        counts = {'iters': 0, 'display': 0}
        sleeps = []
        clock = {'t': 1000.0}

        class _FakeBears:
            def display_bears_info(self_inner, loop_until_final=False):
                # Returns instantly, exactly like a failed schedule fetch
                counts['display'] += 1

        class _FakeHandler:
            bears_display = _FakeBears()

            def display_off_season_content(self_inner):
                raise AssertionError('off-season path must not be reached')

        class _FakeManager:
            def clear_canvas(self_inner):
                pass

            def swap_canvas(self_inner):
                pass

            def set_status(self_inner, *a, **k):
                pass

        board = m.CubsScoreboard.__new__(m.CubsScoreboard)
        board.manager = _FakeManager()
        board.off_season_handler = _FakeHandler()

        def count_iteration():
            counts['iters'] += 1
            return 'auto'

        monkeypatch.setattr(m, 'needs_setup', lambda: False)
        # Fake clock: sleeping advances time instead of spending it, so the
        # 30s dwells are exercised without a two-minute test run.
        monkeypatch.setattr(m.time, 'sleep', _advancing_sleep(clock, sleeps))
        monkeypatch.setattr(m.time, 'time', lambda: clock['t'])
        # Hard ceiling: shutdown trips after a fixed number of loop passes,
        # so a regression fails on the assertions instead of hanging.
        monkeypatch.setattr(
            m, 'is_shutdown_requested', lambda: counts['iters'] > iterations)
        monkeypatch.setattr(board, '_get_display_mode', count_iteration)
        monkeypatch.setattr(board, '_nfl_preempts', lambda: True)
        monkeypatch.setattr(board, 'is_off_season', lambda: (_ for _ in ()).throw(
            AssertionError('preempt branch must own the iteration')))
        monkeypatch.setattr(board, 'process_game_cycle', lambda: (_ for _ in ()).throw(
            AssertionError('preempt branch must own the iteration')))

        board.run()
        return counts, sleeps

    def test_instant_return_still_dwells(self, monkeypatch):
        counts, sleeps = self._run_loop(monkeypatch, iterations=4)
        assert counts['display'] == 5
        # Five passes, the last cut short by shutdown; even two full dwells
        # of 30s dwarf the 2s startup sleep, which is the only sleep a
        # spinning branch would record.
        assert sum(sleeps) >= 60

    def test_dwell_stops_early_on_shutdown(self, monkeypatch):
        import main as m
        board = m.CubsScoreboard.__new__(m.CubsScoreboard)
        sleeps = []
        monkeypatch.setattr(m.time, 'sleep', lambda s: sleeps.append(s))
        monkeypatch.setattr(m, 'is_shutdown_requested', lambda: True)
        board._sleep_interruptibly(30)
        assert sleeps == []

    def test_dwell_sleeps_in_short_slices(self, monkeypatch):
        # SIGTERM must not wait out a 30s uninterruptible block.
        import main as m
        board = m.CubsScoreboard.__new__(m.CubsScoreboard)
        sleeps = []
        clock = {'t': 1000.0}
        monkeypatch.setattr(m.time, 'sleep', _advancing_sleep(clock, sleeps))
        monkeypatch.setattr(m.time, 'time', lambda: clock['t'])
        monkeypatch.setattr(m, 'is_shutdown_requested', lambda: False)
        board._sleep_interruptibly(5)
        assert sum(sleeps) == 5
        assert max(sleeps) <= 1.0


class _LoopCeiling(BaseException):
    """Escapes display_off_season_content's broad `except Exception`, so a
    loop that never returns fails the test instead of hanging the suite."""


class TestOffSeasonTakeoverHandoff:
    """Covers an Important review finding: display_off_season_content is a
    while True that only returns on the once-per-day season check, so the
    NFL takeover guard in main.py was unreachable for months at a time. The
    rotation now aborts between segments when a takeover is pending."""

    def _handler(self, monkeypatch, config, live, takeover_raises=False):
        import off_season_handler as osh

        class _FakeBears:
            def live_game(self_inner):
                if takeover_raises:
                    raise AssertionError(
                        'live_game must not be called when the flag is off')
                return {'id': '401'} if live else None

        h = osh.OffSeasonHandler.__new__(osh.OffSeasonHandler)
        h.config = dict(config)
        h.bears_display = _FakeBears()
        h.last_season_check = None
        h.season_check_interval = 86400
        monkeypatch.setattr(h, '_load_config', lambda: dict(config))
        return h

    def _run_content(self, monkeypatch, h, season_started=False, ceiling=5):
        """Drive display_off_season_content with a rotation stub that just
        runs the between-segment callback, and a bounded loop count."""
        import off_season_handler as osh
        state = {'cycles': 0, 'season_checks': 0}
        monkeypatch.setattr(osh.time, 'sleep', lambda s: None)

        def fake_rotation(between_callback=None):
            state['cycles'] += 1
            if state['cycles'] > ceiling:
                raise _LoopCeiling('off-season loop never returned')
            if between_callback is not None:
                between_callback()

        def fake_season_check():
            state['season_checks'] += 1
            return season_started

        monkeypatch.setattr(h, '_display_rotation_cycle', fake_rotation)
        monkeypatch.setattr(h, '_should_check_season', lambda: True)
        monkeypatch.setattr(h, '_check_season_started', fake_season_check)
        h.display_off_season_content()
        return state

    def test_returns_when_a_takeover_is_pending(self, monkeypatch):
        h = self._handler(
            monkeypatch, {'zip_code': '60613', 'nfl_preempt_mlb': True},
            live=True)
        state = self._run_content(monkeypatch, h)
        assert state['cycles'] == 1
        # Returned on the takeover, not by waiting for the 24hr season check
        assert state['season_checks'] == 0

    def test_keeps_cycling_when_the_option_is_off(self, monkeypatch):
        # Flag off: live_game must never even be called (it is an ESPN
        # request between every rotation segment).
        h = self._handler(
            monkeypatch, {'zip_code': '60613', 'nfl_preempt_mlb': False},
            live=True, takeover_raises=True)
        state = self._run_content(monkeypatch, h, season_started=True)
        assert state['cycles'] == 1
        assert state['season_checks'] == 1

    def test_keeps_cycling_when_no_nfl_game_is_live(self, monkeypatch):
        h = self._handler(
            monkeypatch, {'zip_code': '60613', 'nfl_preempt_mlb': True},
            live=False)
        state = self._run_content(monkeypatch, h, season_started=True)
        assert state['cycles'] == 1
        assert state['season_checks'] == 1

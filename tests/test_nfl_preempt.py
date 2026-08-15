"""NFL preseason detection and MLB/NFL precedence"""

from __future__ import annotations

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

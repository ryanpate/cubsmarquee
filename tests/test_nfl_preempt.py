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

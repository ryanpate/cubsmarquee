# NFL Preseason + MLB/NFL Precedence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show NFL preseason games the same way regular season games are shown, and let the user choose whether a live NFL game takes over the display from MLB.

**Architecture:** Approach A from the spec — two named predicates used inline, rather than a central resolver. `BearsDisplay` gains `has_game_within()` and `live_game()`; `OffSeasonHandler` gains `_mlb_in_progress()`. One guard is added to `main.py`'s run loop and one to the rotation's NFL slot. No existing MLB routing structure is restructured, and `display_game_on()` is not touched.

**Tech Stack:** Python 3.9+, pendulum (timezone math), ESPN public JSON API, Flask (admin panel), pytest with `rgbmatrix` mocked in `tests/conftest.py`.

**Spec:** `docs/superpowers/specs/2026-08-15-nfl-preseason-preempt-design.md`

## Global Constraints

- All modified modules already use `from __future__ import annotations`; keep it and use Python 3.9+ type hints.
- **No new dependencies.** Everything here uses libraries already in `requirements.txt`.
- **Config key schema is frozen on the `bears` naming** (project rule from the NFL team support design): the new key is `nfl_preempt_mlb`; do not rename `enable_bears` or `enable_bears_news`.
- New config key `nfl_preempt_mlb` defaults to `False` everywhere it is read, so existing boards are unchanged.
- Every new network/lookup path must degrade safely: a failure returns the value that *keeps* content on screen, never one that blanks it.
- Tests must run without hardware — construct display objects with `__new__` and set attributes directly, as `tests/test_weather_openmeteo.py` does.
- Timezone for all game-date comparisons is `America/Chicago`, matching existing code in `bears_display.py`.

---

### Task 1: Schedule-driven football season

**Files:**
- Modify: `bears_display.py` (add module-level helper + `has_game_within()` method)
- Modify: `off_season_handler.py:415-421` (`_is_football_season`)
- Test: `tests/test_nfl_preempt.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `BearsDisplay.has_game_within(days_back: int = 3, days_ahead: int = 14) -> bool` and module-level `bears_display.extended_month_gate() -> bool`. Task 3 relies on `OffSeasonHandler._is_football_season()` continuing to return `bool`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_nfl_preempt.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_nfl_preempt.py -v`
Expected: FAIL — `AttributeError: 'BearsDisplay' object has no attribute 'has_game_within'` and `module 'bears_display' has no attribute 'extended_month_gate'`.

- [ ] **Step 3: Write minimal implementation**

In `bears_display.py`, add after the existing module-level helpers (near `format_kickoff_time`, before `class BearsDisplay`):

```python
def extended_month_gate() -> bool:
    """Fallback season window when the schedule cannot be reached.

    August through February, so preseason still counts. Used only when the
    ESPN schedule is unavailable -- returning False there would silently
    hide every NFL screen on a network blip.
    """
    month = pendulum.now().month
    return month >= 8 or month <= 2
```

Add this method to `BearsDisplay` (place it directly after `_get_next_game`):

```python
    def has_game_within(self, days_back: int = 3, days_ahead: int = 14) -> bool:
        """True when the schedule holds a game in the recent past or near future.

        This replaces a hardcoded month gate, so preseason, regular season
        and playoffs all count without a code change. The window deliberately
        stays narrow: ESPN publishes next season's schedule months ahead, and
        a bare "are there any events?" test would light up NFL screens in
        spring.
        """
        try:
            if self._should_update_schedule():
                self._fetch_bears_schedule()
            if not self.bears_data:
                return extended_month_gate()

            now = pendulum.now('America/Chicago')
            window_start = now.subtract(days=days_back)
            window_end = now.add(days=days_ahead)

            for event in self.bears_data.get('events', []):
                when = pendulum.parse(
                    event['date']).in_timezone('America/Chicago')
                if window_start <= when <= window_end:
                    return True
            return False
        except Exception as e:
            print(f"NFL schedule window check failed: {e}")
            return extended_month_gate()
```

In `off_season_handler.py`, replace `_is_football_season` (lines 415-421) with:

```python
    def _is_football_season(self):
        """Football season is whatever the NFL schedule says.

        Schedule-driven rather than month-driven, so preseason games count
        exactly like regular season ones.
        """
        return self.bears_display.has_game_within()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_nfl_preempt.py -v && python3 -m pytest tests/ -q`
Expected: new tests PASS; full suite still green.

- [ ] **Step 5: Commit**

```bash
git add bears_display.py off_season_handler.py tests/test_nfl_preempt.py
git commit -m "Let the NFL schedule decide the season so preseason counts"
```

---

### Task 2: NFL live detection and takeover loop

**Files:**
- Modify: `bears_display.py` (`display_bears_info` at 420-438, `_display_game_day` at 440-521, add `live_game()` and a shutdown helper)
- Test: `tests/test_nfl_preempt.py`

**Interfaces:**
- Consumes: `_get_todays_game()`, `_fetch_live_scores(game_id)`, `_should_update_schedule()`, `_fetch_bears_schedule()` — all already exist in `bears_display.py`.
- Produces: `BearsDisplay.live_game() -> dict | None` (consumed by Task 4) and the keyword arguments `display_bears_info(duration=180, loop_until_final=False, force_scheduled=False)` (consumed by Tasks 3 and 4).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_nfl_preempt.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_nfl_preempt.py -k "LiveGame or Takeover" -v`
Expected: FAIL — `AttributeError: 'BearsDisplay' object has no attribute 'live_game'`, and `display_bears_info() got an unexpected keyword argument 'loop_until_final'`.

- [ ] **Step 3: Write minimal implementation**

In `bears_display.py`, add the shutdown helper at module level (after `extended_month_gate`), mirroring the existing pattern in `setup_display.py:43-49`:

```python
def is_shutdown_requested() -> bool:
    """Lazy import to avoid a circular dependency with main.py."""
    try:
        from main import is_shutdown_requested as _check
        return _check()
    except Exception:
        return False
```

Add `live_game()` to `BearsDisplay`, directly after `has_game_within`:

```python
    def live_game(self) -> dict | None:
        """Today's game when ESPN reports it in progress, else None.

        Liveness is read from the scoreboard endpoint rather than the
        schedule, because the schedule is cached for an hour
        (GameConfig.SCHEDULE_UPDATE_INTERVAL) and its state field would lag
        kickoff badly. Falls back to the schedule event's own state if the
        scoreboard call comes back empty.
        """
        try:
            if self._should_update_schedule():
                self._fetch_bears_schedule()
            game = self._get_todays_game()
            if not game:
                return None
            fresh = self._fetch_live_scores(game.get('id')) or game
            state = fresh['competitions'][0]['status']['type']['state']
            return game if state == 'in' else None
        except Exception as e:
            print(f"NFL live check failed: {e}")
            return None
```

Replace `display_bears_info` (lines 420-438) with:

```python
    def display_bears_info(self, duration=180, loop_until_final=False,
                           force_scheduled=False):
        """Display NFL game information.

        loop_until_final: keep the live game on screen until it ends,
            mirroring how MLB owns the display (preempt mode).
        force_scheduled: show today's game as an upcoming card instead of
            live scores, because MLB currently owns the day.
        """
        # Fetch schedule if needed
        if self._should_update_schedule():
            if not self._fetch_bears_schedule():
                return  # Failed to fetch

        if not self.bears_data:
            return

        # Check for today's game
        todays_game = self._get_todays_game()

        if todays_game:
            if force_scheduled:
                self._display_next_game(todays_game, duration)
            else:
                self._display_game_day(
                    todays_game, duration, loop_until_final=loop_until_final)
        else:
            next_game = self._get_next_game()
            if next_game:
                self._display_next_game(next_game, duration)
```

Change the `_display_game_day` signature (line 440) and its loop condition (line 464). The signature becomes:

```python
    def _display_game_day(self, game, duration, loop_until_final=False):
```

Replace the `while time.time() - start_time < duration:` line with:

```python
            while True:
                if loop_until_final:
                    if (score_data['status'] == 'STATUS_FINAL'
                            or is_shutdown_requested()):
                        break
                elif time.time() - start_time >= duration:
                    break

```

Leave the entire rest of the loop body unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_nfl_preempt.py -v && python3 -m pytest tests/ -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add bears_display.py tests/test_nfl_preempt.py
git commit -m "Add NFL live detection and a takeover loop that runs to final"
```

---

### Task 3: Demote the NFL slot while MLB is in progress

**Files:**
- Modify: `off_season_handler.py` (`__init__` — add TTL cache attributes; add `_mlb_in_progress()`; NFL slot at lines 564-584)
- Test: `tests/test_nfl_preempt.py`

**Interfaces:**
- Consumes: `display_bears_info(..., force_scheduled=...)` from Task 2; `self.manager.get_schedule()` (exists, `scoreboard_manager.py:350`).
- Produces: `OffSeasonHandler._mlb_in_progress() -> bool`.

Reminder from the spec: this path is reachable only in `display_mode: no_games`, by explicit user decision. Implement it anyway — it is the documented behavior.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_nfl_preempt.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_nfl_preempt.py -k MlbInProgress -v`
Expected: FAIL — `AttributeError: 'OffSeasonHandler' object has no attribute '_mlb_in_progress'`.

- [ ] **Step 3: Write minimal implementation**

In `off_season_handler.py`, add the class constant just inside `class OffSeasonHandler` (beside the other class-level attributes):

```python
    # How long an MLB in-progress lookup stays good. The rotation loops
    # continuously in no_games mode and get_schedule's today path is not
    # cached upstream, so this keeps statsapi calls down.
    MLB_STATUS_TTL = 120
```

In `__init__`, next to the other cache attributes:

```python
        # Cached answer for _mlb_in_progress (value, checked_at)
        self._mlb_status_cached: bool = False
        self._mlb_status_checked: float | None = None
```

Add the method next to `_is_football_season`:

```python
    def _mlb_in_progress(self) -> bool:
        """True when the MLB game is actually underway.

        manager.current_status is set only by route_by_status, which never
        runs in no_games mode -- the very mode this check matters in -- so
        the schedule is queried directly, behind a short TTL. Any failure
        returns False, which keeps live NFL scores on screen rather than
        suppressing them.
        """
        now = time.time()
        if (self._mlb_status_checked is not None
                and now - self._mlb_status_checked < self.MLB_STATUS_TTL):
            return self._mlb_status_cached

        live = False
        try:
            for game in self.manager.get_schedule() or []:
                status = game.get('status', '')
                if (status == 'In Progress'
                        or 'challenge' in status.lower()
                        or 'review' in status.lower()):
                    live = True
                    break
        except Exception as e:
            print(f"MLB status check failed: {e}")
            live = False

        self._mlb_status_cached = live
        self._mlb_status_checked = now
        return live
```

Replace the NFL slot body (lines 564-576, the `if self._is_football_season() and bears_enabled:` block up to its `except`) with:

```python
        # Display NFL info if it's football season and enabled
        bears_enabled = self.config.get('enable_bears', True)
        if self._is_football_season() and bears_enabled:
            # MLB owns the day while its game is actually underway, so the
            # NFL slot drops to an upcoming-game card instead of live scores.
            force_scheduled = (
                not self.config.get('nfl_preempt_mlb', False)
                and self._mlb_in_progress())
            if force_scheduled:
                print("MLB game in progress - showing NFL game as scheduled")
            else:
                print("Displaying Bears info (football season)...")
            try:
                self.bears_display.display_bears_info(
                    duration=self.rotation_schedule['bears'] * 60,
                    force_scheduled=force_scheduled
                )
                print("Bears display finished")
            except Exception as e:
                print(f"Error in Bears display: {e}")
                import traceback
                traceback.print_exc()
```

Leave the `if _tick(): return` and the `else:` branch that follows unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_nfl_preempt.py -v && python3 -m pytest tests/ -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add off_season_handler.py tests/test_nfl_preempt.py
git commit -m "Show the NFL game as scheduled while an MLB game is underway"
```

---

### Task 4: The preempt guard in the main loop

**Files:**
- Modify: `main.py` (add `_nfl_preempts()` near `_get_display_mode` at 195-201; add guard in `run()` between lines 132 and 134)
- Test: `tests/test_nfl_preempt.py`

**Interfaces:**
- Consumes: `BearsDisplay.live_game()` and `display_bears_info(loop_until_final=True)` from Task 2.
- Produces: `CubsScoreboard._nfl_preempts() -> bool`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_nfl_preempt.py`:

First add `import json` to the imports at the top of `tests/test_nfl_preempt.py`
(the file created in Task 1 imports only `time` and `pendulum`), then append:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_nfl_preempt.py -k PreemptGuard -v`
Expected: FAIL — `AttributeError: 'CubsScoreboard' object has no attribute '_nfl_preempts'`.

- [ ] **Step 3: Write minimal implementation**

In `main.py`, add directly after `_get_display_mode` (which ends at line 201):

```python
    def _nfl_preempts(self, config_path: str = '/home/pi/config.json') -> bool:
        """True when the user wants football first and an NFL game is live.

        Off by default, so existing boards keep MLB priority. Any failure
        returns False, which leaves normal MLB routing in charge.
        """
        try:
            with open(config_path, 'r') as f:
                if not json.load(f).get('nfl_preempt_mlb', False):
                    return False
        except Exception:
            return False

        try:
            return (self.off_season_handler.bears_display.live_game()
                    is not None)
        except Exception as e:
            logger.error(f"NFL preempt check failed: {e}")
            return False
```

In `run()`, insert this block between the `no_games` branch's `continue` (line 132) and `if self.is_off_season():` (line 134). Placing it here means `no_games` still wins, while preempt applies on both the in-season and off-season paths:

```python
                    # Football-first mode: a live NFL game takes the screen
                    # the way a live MLB game normally would.
                    if self._nfl_preempts():
                        logger.info(
                            "NFL game live and nfl_preempt_mlb set - "
                            "NFL takes over the display")
                        self.manager.set_status('NFL game')
                        self.off_season_handler.bears_display.display_bears_info(
                            loop_until_final=True)
                        if is_shutdown_requested():
                            break
                        continue

```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_nfl_preempt.py -v && python3 -m pytest tests/ -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_nfl_preempt.py
git commit -m "Let a live NFL game preempt MLB when the user asks for it"
```

---

### Task 5: Admin panel option

**Files:**
- Modify: `wifi_config_server.py` at five sites — defaults (~line 153), HTML (~763), JS load (~1239), JS save (~1505), POST handler (~2201)
- Test: `tests/test_admin_config.py`

**Interfaces:**
- Consumes: the `nfl_preempt_mlb` key read in Tasks 3 and 4.
- Produces: nothing consumed by later tasks (final task).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_admin_config.py`:

```python
def test_admin_page_offers_nfl_preempt_toggle(client):
    html = client.get('/admin').data.decode()
    assert 'id="nfl_preempt_mlb"' in html


def test_save_config_round_trips_nfl_preempt(client, tmp_path):
    resp = client.post('/save_config', json={'nfl_preempt_mlb': True})
    assert resp.get_json()['success']
    saved = json.loads((tmp_path / 'config.json').read_text())
    assert saved['nfl_preempt_mlb'] is True


def test_nfl_preempt_defaults_to_off(client):
    import wifi_config_server as wcs
    assert wcs.load_config()['nfl_preempt_mlb'] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_admin_config.py -k preempt -v`
Expected: FAIL — `assert 'id="nfl_preempt_mlb"' in html` fails, and `KeyError: 'nfl_preempt_mlb'`.

- [ ] **Step 3: Write minimal implementation**

Site 1 — defaults dict, add after the `'enable_bears_news': True,` line (~154):

```python
        'nfl_preempt_mlb': False,
```

Site 2 — HTML, add a new form-group after the `enable_bears_news` block (~772):

```html
                        <div class="form-group">
                            <label>
                                <input type="checkbox" id="nfl_preempt_mlb">
                                NFL preempts MLB
                            </label>
                            <div class="help-text">A live football game takes over the display, the way a baseball game normally does. Off by default, so baseball wins.</div>
                        </div>
```

Site 3 — JS load, add after the `enable_bears_news` line (~1240):

```javascript
            document.getElementById('nfl_preempt_mlb').checked = config.nfl_preempt_mlb === true;
```

Note the `=== true` rather than the `!== false` used by the enable_* keys: this option defaults **off**, so an absent key must render unchecked.

Site 4 — JS save, add after the `enable_bears_news` line (~1506):

```javascript
                nfl_preempt_mlb: document.getElementById('nfl_preempt_mlb').checked,
```

Site 5 — POST handler, add after the `enable_bears_news` line (~2202):

```python
            'nfl_preempt_mlb': data.get(
                'nfl_preempt_mlb', current_config.get('nfl_preempt_mlb', False)),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_admin_config.py -v && python3 -m pytest tests/ -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add wifi_config_server.py tests/test_admin_config.py
git commit -m "Add the NFL-preempts-MLB toggle to the admin panel"
```

---

### Task 6: Documentation and hardware verification

**Files:**
- Modify: `CLAUDE.md` (Configuration section)

**Interfaces:**
- Consumes: everything above.
- Produces: nothing.

- [ ] **Step 1: Document the new config key**

In `CLAUDE.md`, under the `/home/pi/config.json` bullet list, add after the `nfl_team` line:

```markdown
- `nfl_preempt_mlb` — when `true`, a live NFL game takes over the display the way a live MLB game does, and MLB drops to its scheduled card (default `false`). Football season is detected from the ESPN schedule (game within -3/+14 days), not from a month range, so preseason counts like the regular season
```

- [ ] **Step 2: Run the full suite**

Run: `python3 -m pytest tests/ -q`
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "Document nfl_preempt_mlb and schedule-driven football season"
```

- [ ] **Step 4: Verify against the live ESPN feed**

Run this on the Mac (it hits only public endpoints, no hardware needed):

```bash
python3 -c "
import bears_display as bd
d = bd.BearsDisplay.__new__(bd.BearsDisplay)
d.bears_data = None; d.last_update = None
d.update_interval = 3600; d.live_update_interval = 30
d.nfl_team = __import__('teams').get_active_nfl_team()
d.schedule_url = ('https://site.api.espn.com/apis/site/v2/sports/football/nfl/'
                  f'teams/{d.nfl_team.espn_slug}/schedule')
print('in season:', d.has_game_within())
print('live game:', d.live_game() is not None)
"
```

Expected during preseason: `in season: True`. `live game` is True only while a game is actually being played.

- [ ] **Step 5: Deploy and reboot**

```bash
scp bears_display.py off_season_handler.py main.py wifi_config_server.py pi@cubsmarquee.local:/home/pi/
ssh pi@cubsmarquee.local 'sudo reboot'
```

Repeat for `cardsmarquee-one.local` (fall back to `192.168.5.94` if mDNS fails). Reboot rather than `systemctl restart` — restarts leave zombie processes on these units.

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| 1. Season detection (schedule-driven + month fallback) | Task 1 |
| 2. NFL live takeover (`live_game`, `loop_until_final`, main guard) | Tasks 2, 4 |
| 3. Default demotion (`_mlb_in_progress`, `force_scheduled`) | Task 3 |
| 4. Admin panel | Task 5 |
| 5. Testing | Tasks 1-5, plus `test_admin_config.py` in Task 5 |
| Out of scope (`display_game_on` untouched) | No task modifies it |

**Type consistency:** `has_game_within` → `bool`; `live_game` → `dict | None`; `_mlb_in_progress` → `bool`; `_nfl_preempts` → `bool`. `display_bears_info(duration, loop_until_final, force_scheduled)` is defined in Task 2 and called with those exact names in Tasks 3 and 4. `extended_month_gate` is module-level in `bears_display` and referenced by that name in Task 1's fallback test.

**Placeholder scan:** none — every step carries runnable code.

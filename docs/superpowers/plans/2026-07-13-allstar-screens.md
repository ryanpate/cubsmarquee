# All-Star Break Screens Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Derby promo, ASG pregame countdown, live AL vs NL scoreboard, and final screen on the 96x48 marquee, with Cubs all-stars celebrated generically via `parentTeamId`.

**Architecture:** One new handler module `allstar_display.py` (pattern: `spring_training_display.py`). Rotation gets an `allstar` segment; `main.process_game_cycle()` gets a live-takeover check; the hybrid rotation call gets a `between_callback` so rotation aborts when the game goes live. `LiveGameHandler` is not touched.

**Tech Stack:** Python 3.9+ (`from __future__ import annotations`), MLB-StatsAPI (`statsapi.get`), pendulum, PIL, pytest with `Mock` manager (existing pattern in `tests/test_features.py`).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-13-allstar-screens-design.md`
- Verified live data: schedule `gameTypes=A` → ASG pk 823443 (2026); feed `statsapi.get('game', {'gamePk': pk})` has `parentTeamId` per boxscore player (Cubs id = `TeamConfig.CUBS_TEAM_ID` = 112).
- Never crash the game cycle: every fetch failure logs and returns None/False.
- All timestamps in `America/Chicago`.
- Reuse `format_countdown`, `countdown_color`, `format_kickoff_time` from `bears_display` (module-level pure functions).
- Testable time-dependent helpers take an optional `now` parameter defaulting to `pendulum.now('America/Chicago')`.
- Fonts available: `micro`(4px), `tiny`/`tiny_bold`(5px), `small`/`small_bold`(6px), `standard_bold`(7px), `medium_bold`(9px). Manager API: `clear_canvas()`, `fill_canvas(r,g,b)`, `draw_pixel(x,y,r,g,b)`, `draw_text(font,x,y,color,text)`, `set_image(img,x,y)`, `swap_canvas()`.

---

### Task 1: AllStarDisplay data core

**Files:**
- Create: `allstar_display.py`
- Test: `tests/test_allstar.py`

**Interfaces:**
- Produces: `AllStarDisplay(manager)` with `fetch_asg_info() -> dict|None` (`{'game_pk': int, 'date': pendulum.DateTime, 'venue': str, 'status': str, 'abstract': str}`), `is_allstar_window(now=None) -> bool`, `asg_is_live() -> bool`, `_derby_active(now=None) -> bool`, `_fetch_feed(game_pk, ttl) -> dict|None`, static `_parse_asg_schedule(data)`, `_cubs_allstars_from_boxscore(feed) -> list[str]`, `_extract_live_state(feed) -> dict`. Module constant `DERBY_INFO`.

- [ ] **Step 1: Write the failing tests**

Append to a new file `tests/test_allstar.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_allstar.py -v`
Expected: FAIL / errors with `ModuleNotFoundError: No module named 'allstar_display'`

- [ ] **Step 3: Write the data core**

Create `allstar_display.py`:

```python
"""All-Star break display - Derby promo, ASG countdown, live AL vs NL score"""

from __future__ import annotations

import time
import pendulum
import statsapi
from PIL import Image
from typing import TYPE_CHECKING, Any

from scoreboard_config import (
    Colors, DisplayConfig, Fonts, RGBColor, TeamConfig,
)
from bears_display import format_countdown, countdown_color, format_kickoff_time
from retry import retry_api_call

if TYPE_CHECKING:
    from scoreboard_manager import ScoreboardManager

# Updated by hand each July (no public API exists for the Derby). The Derby
# screen self-disables unless this date is exactly one day before the ASG
# date from the live schedule lookup, so a stale year never shows the wrong
# field (see _derby_active).
DERBY_INFO: dict[str, Any] = {
    'date': '2026-07-13',
    'start_hour': 19,               # 7 PM America/Chicago
    'venue': 'CITIZENS BANK PARK',
    'field': [
        'SCHWARBER PHI', 'HARPER PHI', 'CAMINERO TB', 'RICE NYY',
        'CONTRERAS BOS', 'WALKER STL', 'CAGLIANONE KC', 'MURAKAMI CWS',
    ],
}

AL_RED: RGBColor = (191, 13, 62)
NL_BLUE: RGBColor = (10, 35, 120)
GOLD: RGBColor = (255, 215, 0)
DARK_BG: RGBColor = (8, 10, 28)
PANEL_BG: RGBColor = (5, 15, 40)
DIM_GRAY: RGBColor = (120, 120, 120)


class AllStarDisplay:
    """All-Star break screens: Derby promo, ASG pregame countdown,
    live AL vs NL scoreboard, and final screen."""

    ASG_CACHE_SECONDS = 3600
    ASG_CACHE_SECONDS_GAMEDAY = 60
    FEED_CACHE_SECONDS_LIVE = 20
    FEED_CACHE_SECONDS_PREGAME = 1800

    def __init__(self, scoreboard_manager: ScoreboardManager) -> None:
        self.manager = scoreboard_manager
        self._asg_cache: dict[str, Any] | None = None
        self._asg_cached_at: float = 0.0
        self._feed_cache: dict[str, Any] | None = None
        self._feed_cached_at: float = 0.0

    # ------------------------------------------------------------ data

    def fetch_asg_info(self) -> dict[str, Any] | None:
        """This season's All-Star Game from the schedule API, cached.
        Cache drops to 60s within an hour of first pitch so the live
        takeover reacts quickly."""
        ttl = self.ASG_CACHE_SECONDS
        if self._asg_cache:
            game_dt = self._asg_cache['date']
            now_local = pendulum.now('America/Chicago')
            if (game_dt.date() == now_local.date()
                    and now_local >= game_dt.subtract(hours=1)):
                ttl = self.ASG_CACHE_SECONDS_GAMEDAY
        if self._asg_cache is not None and time.time() - self._asg_cached_at < ttl:
            return self._asg_cache

        year = pendulum.now('America/Chicago').year
        try:
            data = retry_api_call(
                statsapi.get, 'schedule',
                {'sportId': 1, 'gameTypes': 'A',
                 'startDate': f'{year}-07-01', 'endDate': f'{year}-07-31'})
            self._asg_cache = self._parse_asg_schedule(data)
            self._asg_cached_at = time.time()
        except Exception as e:
            print(f"ASG schedule fetch failed: {e}")
        return self._asg_cache

    @staticmethod
    def _parse_asg_schedule(data: dict[str, Any]) -> dict[str, Any] | None:
        for day in data.get('dates', []):
            for game in day.get('games', []):
                return {
                    'game_pk': game['gamePk'],
                    'date': pendulum.parse(
                        game['gameDate']).in_timezone('America/Chicago'),
                    'venue': game.get('venue', {}).get('name', ''),
                    'status': game.get('status', {}).get('detailedState', ''),
                    'abstract': game.get('status', {}).get(
                        'abstractGameState', ''),
                }
        return None

    def is_allstar_window(self, now: pendulum.DateTime | None = None) -> bool:
        """True on Derby day (ASG - 1) and ASG day."""
        info = self.fetch_asg_info()
        if not info:
            return False
        today = (now or pendulum.now('America/Chicago')).date()
        asg_dt = info['date']
        return today in (asg_dt.date(), asg_dt.subtract(days=1).date())

    def asg_is_live(self) -> bool:
        info = self.fetch_asg_info()
        return bool(info) and info.get('abstract') == 'Live'

    def _derby_active(self, now: pendulum.DateTime | None = None) -> bool:
        """Derby promo window: DERBY_INFO date matches ASG - 1 (guards a
        stale constant) and it's that day before 11 PM."""
        info = self.fetch_asg_info()
        if not info:
            return False
        now = now or pendulum.now('America/Chicago')
        derby_date = pendulum.parse(
            DERBY_INFO['date'], tz='America/Chicago').date()
        if derby_date != info['date'].subtract(days=1).date():
            return False
        return now.date() == derby_date and now.hour < 23

    def _fetch_feed(self, game_pk: int, ttl: float) -> dict[str, Any] | None:
        if (self._feed_cache is not None
                and time.time() - self._feed_cached_at < ttl):
            return self._feed_cache
        try:
            self._feed_cache = retry_api_call(
                statsapi.get, 'game', {'gamePk': game_pk})
            self._feed_cached_at = time.time()
        except Exception as e:
            print(f"ASG feed fetch failed: {e}")
        return self._feed_cache

    @staticmethod
    def _cubs_allstars_from_boxscore(feed: dict[str, Any]) -> list[str]:
        names = []
        teams = feed.get('liveData', {}).get('boxscore', {}).get('teams', {})
        for side in ('away', 'home'):
            for player in teams.get(side, {}).get('players', {}).values():
                if player.get('parentTeamId') == TeamConfig.CUBS_TEAM_ID:
                    name = player.get('person', {}).get('fullName', '')
                    if name:
                        names.append(name)
        return names

    @staticmethod
    def _extract_live_state(feed: dict[str, Any]) -> dict[str, Any]:
        live = feed.get('liveData', {})
        linescore = live.get('linescore', {})
        offense = linescore.get('offense', {})
        batter = (live.get('plays', {}).get('currentPlay', {})
                  .get('matchup', {}).get('batter', {}))
        parent_team = None
        if batter.get('id'):
            for side in ('away', 'home'):
                player = (live.get('boxscore', {}).get('teams', {})
                          .get(side, {}).get('players', {})
                          .get(f"ID{batter['id']}"))
                if player:
                    parent_team = player.get('parentTeamId')
                    break
        return {
            'away_runs': linescore.get('teams', {}).get('away', {}).get('runs', 0),
            'home_runs': linescore.get('teams', {}).get('home', {}).get('runs', 0),
            'inning': linescore.get('currentInning', 1),
            'inning_state': linescore.get('inningState', ''),
            'outs': linescore.get('outs', 0),
            'bases': {base: base in offense
                      for base in ('first', 'second', 'third')},
            'batter_name': batter.get('fullName', ''),
            'batter_is_cub': parent_team == TeamConfig.CUBS_TEAM_ID,
            'is_final': feed.get('gameData', {}).get('status', {}).get(
                'abstractGameState') == 'Final',
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_allstar.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add allstar_display.py tests/test_allstar.py
git commit -m "Add All-Star display data core: ASG lookup, window, feed parsing"
```

---

### Task 2: Derby promo and ASG pregame screens

**Files:**
- Modify: `allstar_display.py` (append methods to `AllStarDisplay`)
- Test: `tests/test_allstar.py`

**Interfaces:**
- Consumes: Task 1 data methods.
- Produces: `display_promo(duration: int) -> None` (rotation entry point; returns immediately outside the window), `_display_derby_promo(duration)`, `_display_asg_pregame(duration, info)`, `_get_cubs_allstars(game_pk) -> list[str]`, `_center_x(text, char_width) -> int`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_allstar.py`. A `_FakeTime` (same shape as `tests/test_features.py`) makes display loops finish instantly:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_allstar.py::TestPromoScreens -v`
Expected: FAIL with `AttributeError: ... no attribute 'display_promo'`

- [ ] **Step 3: Implement the promo screens**

Append to the `AllStarDisplay` class:

```python
    # --------------------------------------------------------- promo

    @staticmethod
    def _center_x(text: str, char_width: int) -> int:
        return max(0, (DisplayConfig.MATRIX_COLS - len(text) * char_width) // 2)

    def display_promo(self, duration: int) -> None:
        """Rotation segment: Derby promo on Derby evening, ASG pregame
        countdown otherwise. No-op outside the All-Star window or once
        the game has started (the live takeover handles that)."""
        info = self.fetch_asg_info()
        if not info or not self.is_allstar_window():
            return
        if self._derby_active():
            self._display_derby_promo(duration)
        elif info.get('abstract') == 'Preview':
            self._display_asg_pregame(duration, info)

    def _display_derby_promo(self, duration: int) -> None:
        tz = 'America/Chicago'
        derby_start = pendulum.parse(DERBY_INFO['date'], tz=tz).add(
            hours=DERBY_INFO['start_hour'])
        field_text = '  *  '.join(DERBY_INFO['field'])
        field_width = len(field_text) * Fonts.CHAR_WIDTH_MICRO
        scroll_x = float(DisplayConfig.MATRIX_COLS)
        start = time.time()

        while time.time() - start < duration:
            self.manager.clear_canvas()
            self.manager.fill_canvas(*DARK_BG)
            for x in range(DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, 0, *GOLD)

            title = 'HOME RUN DERBY'
            self.manager.draw_text(
                'tiny_bold', self._center_x(title, Fonts.CHAR_WIDTH_TINY),
                10, GOLD, title)

            seconds = (derby_start - pendulum.now(tz)).total_seconds()
            if seconds > 0:
                line = f'TONIGHT {format_countdown(seconds)}'
                color = countdown_color(seconds, yellow_under=3 * 3600,
                                        orange_under=30 * 60)
            else:
                line, color = 'UNDERWAY', GOLD
            self.manager.draw_text(
                'micro', self._center_x(line, Fonts.CHAR_WIDTH_MICRO),
                20, color, line)

            venue = DERBY_INFO['venue']
            self.manager.draw_text(
                'micro', self._center_x(venue, Fonts.CHAR_WIDTH_MICRO),
                28, (150, 150, 150), venue)

            self.manager.draw_text(
                'micro', int(scroll_x), 40, Colors.WHITE, field_text)
            scroll_x -= 1
            if scroll_x < -field_width:
                scroll_x = float(DisplayConfig.MATRIX_COLS)

            self.manager.swap_canvas()
            time.sleep(0.05)

    def _get_cubs_allstars(self, game_pk: int) -> list[str]:
        feed = self._fetch_feed(game_pk, self.FEED_CACHE_SECONDS_PREGAME)
        if not feed:
            return []
        return self._cubs_allstars_from_boxscore(feed)

    def _display_asg_pregame(self, duration: int, info: dict) -> None:
        tz = 'America/Chicago'
        cubs_stars = self._get_cubs_allstars(info['game_pk'])
        stars_text = ('CUBS ALL-STARS: ' + ', '.join(cubs_stars).upper()
                      if cubs_stars else '')
        stars_width = len(stars_text) * Fonts.CHAR_WIDTH_MICRO
        scroll_x = float(DisplayConfig.MATRIX_COLS)
        game_dt = info['date']
        date_line = (f"{game_dt.format('ddd').upper()} "
                     f"{format_kickoff_time(game_dt)}")
        start = time.time()

        while time.time() - start < duration:
            self.manager.clear_canvas()
            self.manager.fill_canvas(*DARK_BG)
            for x in range(DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, 0, *GOLD)

            title = 'ALL-STAR GAME'
            self.manager.draw_text(
                'tiny_bold', self._center_x(title, Fonts.CHAR_WIDTH_TINY),
                10, GOLD, title)

            self.manager.draw_text('tiny_bold', 30, 19, AL_RED, 'AL')
            self.manager.draw_text('tiny_bold', 43, 19, Colors.WHITE, 'VS')
            self.manager.draw_text('tiny_bold', 56, 19, NL_BLUE, 'NL')

            seconds = (game_dt - pendulum.now(tz)).total_seconds()
            if seconds > 0:
                line = f'FIRST PITCH {format_countdown(seconds)}'
                color = countdown_color(seconds, yellow_under=3 * 3600,
                                        orange_under=30 * 60)
            else:
                line, color = 'STARTING SOON', GOLD
            self.manager.draw_text(
                'micro', self._center_x(line, Fonts.CHAR_WIDTH_MICRO),
                27, color, line)

            self.manager.draw_text(
                'micro', self._center_x(date_line, Fonts.CHAR_WIDTH_MICRO),
                35, (150, 150, 150), date_line)

            if stars_text:
                self.manager.draw_text(
                    'micro', int(scroll_x), 45, Colors.YELLOW, stars_text)
                scroll_x -= 1
                if scroll_x < -stars_width:
                    scroll_x = float(DisplayConfig.MATRIX_COLS)

            self.manager.swap_canvas()
            time.sleep(0.05)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_allstar.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add allstar_display.py tests/test_allstar.py
git commit -m "Add Derby promo and ASG pregame countdown screens"
```

---

### Task 3: Live AL vs NL screen and final screen

**Files:**
- Modify: `allstar_display.py` (append methods)
- Test: `tests/test_allstar.py`

**Interfaces:**
- Consumes: Task 1 `_fetch_feed`, `_extract_live_state`, `fetch_asg_info`.
- Produces: `display_live_game(display_time: int) -> bool` (True once feed says Final), `display_final(duration: int) -> None` (invalidates the ASG cache on exit so `asg_is_live()` re-checks promptly), `_render_live_frame(state)`, `_draw_league_tiles()`, `_draw_bases(cx, cy, bases)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_allstar.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_allstar.py::TestLiveScreen -v`
Expected: FAIL with `AttributeError: ... no attribute 'display_live_game'`

- [ ] **Step 3: Implement the live and final screens**

Append to the `AllStarDisplay` class:

```python
    # ---------------------------------------------------------- live

    def display_live_game(self, display_time: int) -> bool:
        """Run the live AL vs NL screen for display_time seconds.
        Returns True as soon as the feed reports the game is over."""
        info = self.fetch_asg_info()
        if not info:
            return False
        start = time.time()
        while time.time() - start < display_time:
            feed = self._fetch_feed(info['game_pk'],
                                    self.FEED_CACHE_SECONDS_LIVE)
            if not feed:
                return False
            state = self._extract_live_state(feed)
            if state['is_final']:
                return True
            self._render_live_frame(state)
            time.sleep(0.5)
        return False

    def _draw_league_tiles(self) -> Image.Image:
        """Base image mirroring the live-game layout: league tiles in the
        16px logo column, white score boxes, dark info panel."""
        base = Image.new('RGB', (96, 48))
        px = base.load()
        for y in range(0, 15):
            for x in range(0, 16):
                px[x, y] = AL_RED
        for y in range(16, 31):
            for x in range(0, 16):
                px[x, y] = NL_BLUE
        for x in range(17, 32):
            for y in range(0, 31):
                px[x, y] = (255, 255, 255) if y != 15 else (0, 0, 0)
        for x in range(32, 96):
            for y in range(0, 31):
                px[x, y] = PANEL_BG
        return base

    def _draw_star(self, x: int, y: int) -> None:
        for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
            self.manager.draw_pixel(x + dx, y + dy, *GOLD)

    def _draw_bases(self, cx: int, cy: int, bases: dict[str, bool]) -> None:
        spots = {'second': (cx, cy - 4), 'first': (cx + 4, cy),
                 'third': (cx - 4, cy)}
        for name, (bx, by) in spots.items():
            color = Colors.YELLOW if bases[name] else (70, 70, 90)
            for dx in range(2):
                for dy in range(2):
                    self.manager.draw_pixel(bx + dx, by + dy, *color)

    def _render_live_frame(self, state: dict) -> None:
        m = self.manager
        m.clear_canvas()
        m.set_image(self._draw_league_tiles(), 0, 0)

        m.draw_text('tiny_bold', 3, 11, Colors.WHITE, 'AL')
        m.draw_text('tiny_bold', 3, 27, Colors.WHITE, 'NL')
        self._draw_star(13, 3)
        self._draw_star(13, 19)

        for runs, y in ((state['away_runs'], 11), (state['home_runs'], 27)):
            text = str(runs)
            x = 17 + max(0, (15 - len(text) * Fonts.CHAR_WIDTH_STANDARD) // 2)
            m.draw_text('standard_bold', x, y, (0, 0, 0), text)

        title = 'ALL-STAR GAME'
        title_x = 32 + max(0, (64 - len(title) * Fonts.CHAR_WIDTH_MICRO) // 2)
        m.draw_text('micro', title_x, 7, GOLD, title)

        inning_line = f"{state['inning_state'][:3].upper()} {state['inning']}"
        m.draw_text('tiny', 38, 18, Colors.WHITE, inning_line)
        for i in range(3):
            color = (255, 60, 60) if i < state['outs'] else (70, 70, 90)
            for dx in range(2):
                for dy in range(2):
                    m.draw_pixel(40 + i * 6 + dx, 23 + dy, *color)
        self._draw_bases(80, 20, state['bases'])

        name = state['batter_name'].upper()
        if name:
            if state['batter_is_cub'] and int(time.time()) % 4 < 2:
                for y in range(33, 48):
                    for x in range(0, 96):
                        m.draw_pixel(x, y, *Colors.YELLOW)
                banner = 'CUBS STAR AT BAT'
                m.draw_text(
                    'micro', self._center_x(banner, Fonts.CHAR_WIDTH_MICRO),
                    39, Colors.CUBS_BLUE, banner)
                m.draw_text(
                    'micro', self._center_x(name, Fonts.CHAR_WIDTH_MICRO),
                    46, Colors.CUBS_BLUE, name)
            else:
                m.draw_text('micro', 2, 39, (150, 150, 150), 'AT BAT')
                if len(name) * Fonts.CHAR_WIDTH_TINY > 94:
                    name = name.split()[-1]
                m.draw_text('tiny', 2, 46, Colors.WHITE, name)

        m.swap_canvas()

    def display_final(self, duration: int) -> None:
        info = self.fetch_asg_info()
        if not info:
            return
        feed = self._fetch_feed(info['game_pk'], self.FEED_CACHE_SECONDS_LIVE)
        if not feed:
            return
        state = self._extract_live_state(feed)
        away, home = state['away_runs'], state['home_runs']
        al_color = Colors.WHITE if away > home else DIM_GRAY
        nl_color = Colors.WHITE if home > away else DIM_GRAY

        start = time.time()
        while time.time() - start < duration:
            self.manager.clear_canvas()
            self.manager.fill_canvas(*DARK_BG)
            for x in range(DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, 0, *GOLD)

            title = 'ALL-STAR GAME'
            self.manager.draw_text(
                'tiny_bold', self._center_x(title, Fonts.CHAR_WIDTH_TINY),
                10, GOLD, title)
            self.manager.draw_text(
                'tiny_bold', self._center_x('FINAL', Fonts.CHAR_WIDTH_TINY),
                21, Colors.WHITE, 'FINAL')
            self.manager.draw_text('tiny_bold', 18, 34, al_color,
                                   f'AL {away}')
            self.manager.draw_text('tiny_bold', 54, 34, nl_color,
                                   f'NL {home}')

            self.manager.swap_canvas()
            time.sleep(0.1)

        # Force the next asg_is_live() to re-check the schedule so the
        # takeover loop exits promptly after the final screen.
        self._asg_cached_at = 0.0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_allstar.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add allstar_display.py tests/test_allstar.py
git commit -m "Add live AL vs NL scoreboard and final screen"
```

---

### Task 4: Rotation segment in off_season_handler

**Files:**
- Modify: `off_season_handler.py` (import block ~line 21, `__init__` ~line 45, `rotation_schedule` dict ~line 84-97, config defaults dict ~line 161-183, `_display_rotation_cycle` — insert after the spring_training segment block that ends ~line 827)
- Test: `tests/test_allstar.py`

**Interfaces:**
- Consumes: `AllStarDisplay(manager)`, `display_promo(duration)`, `is_allstar_window()`.
- Produces: `self.allstar_display` on `OffSeasonHandler`, `rotation_schedule['allstar']`, config key `enable_allstar` (default True).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_allstar.py`:

```python
class TestRotationIntegration:
    def test_rotation_schedule_has_allstar_segment(self) -> None:
        from off_season_handler import OffSeasonHandler

        handler = OffSeasonHandler.__new__(OffSeasonHandler)
        handler.rotation_schedule = {}
        # rebuild the schedule the same way __init__ does is brittle;
        # instead verify via the class-level construction in __init__
        import inspect

        source = inspect.getsource(OffSeasonHandler.__init__)
        assert "'allstar'" in source

        cycle_source = inspect.getsource(
            OffSeasonHandler._display_rotation_cycle)
        assert 'display_promo' in cycle_source
        assert 'enable_allstar' in cycle_source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_allstar.py::TestRotationIntegration -v`
Expected: FAIL on `assert "'allstar'" in source`

- [ ] **Step 3: Wire the segment**

In `off_season_handler.py`:

1. Import (next to the other display imports, ~line 21):
```python
from allstar_display import AllStarDisplay
```

2. In `__init__` (next to `self.spring_training_display`, ~line 45):
```python
self.allstar_display: AllStarDisplay = AllStarDisplay(scoreboard_manager)
```

3. In the `rotation_schedule` dict (~line 84-97) add:
```python
'allstar': 2,  # All-Star break: Derby promo / ASG countdown
```

4. In the `_load_config` defaults dict (~line 161-183) add:
```python
'enable_allstar': True,  # All-Star break screens (Derby promo, ASG countdown)
```

5. In `_display_rotation_cycle`, immediately after the spring_training
   segment's `if _tick(): return` (~line 827), insert:
```python
        # All-Star break: Derby promo / ASG pregame countdown. display_promo
        # is a no-op outside the two-day window, so this segment costs
        # nothing the rest of the year.
        if self.config.get('enable_allstar', True):
            try:
                self.allstar_display.display_promo(
                    duration=self.rotation_schedule['allstar'] * 60)
            except Exception as e:
                print(f"Error in All-Star display: {e}")
                import traceback
                traceback.print_exc()

        if _tick():
            return
```

- [ ] **Step 4: Run the full suite**

Run: `python3 -m pytest tests/ -q`
Expected: all PASS (existing rotation tests must not break)

- [ ] **Step 5: Commit**

```bash
git add off_season_handler.py tests/test_allstar.py
git commit -m "Add allstar rotation segment gated by window and toggle"
```

---

### Task 5: Live takeover in main.py

**Files:**
- Modify: `main.py` (imports ~line 20s, `__init__` where handlers are built, top of `process_game_cycle` ~line 201, hybrid rotation call ~line 377)
- Test: `tests/test_allstar.py`

**Interfaces:**
- Consumes: `AllStarDisplay.asg_is_live()`, `display_live_game(120) -> bool`, `display_final(60)`.
- Produces: `CubsScoreboard.allstar_display`; `process_game_cycle` returns early while the ASG is live.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_allstar.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_allstar.py::TestLiveTakeover -v`
Expected: FAIL — `display_live_game` not called (takeover missing)

- [ ] **Step 3: Implement the takeover**

In `main.py`:

1. Import next to the other handler imports:
```python
from allstar_display import AllStarDisplay
```

2. In `CubsScoreboard.__init__`, next to the other handlers:
```python
self.allstar_display = AllStarDisplay(self.manager)
```

3. At the very top of `process_game_cycle`'s `try:` block (before
   `game_data = self.manager.get_schedule()`):
```python
            # All-Star Game takes over the display while it's live
            # (it is not in the Cubs schedule, so normal routing never
            # sees it). Re-entered each main-loop iteration until Final.
            if self.allstar_display.asg_is_live():
                logger.info("All-Star Game live - taking over display")
                self.manager.set_status('All-Star Game')
                if self.allstar_display.display_live_game(120):
                    self.allstar_display.display_final(60)
                return
```

4. In `route_by_status`, change the hybrid rotation call (~line 377)
   so the rotation aborts between segments when the ASG goes live:
```python
                self.off_season_handler._display_rotation_cycle(
                    between_callback=self.allstar_display.asg_is_live)
```
   (was `self.off_season_handler._display_rotation_cycle()`)

- [ ] **Step 4: Run the full suite**

Run: `python3 -m pytest tests/ -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_allstar.py
git commit -m "Take over display with live All-Star Game, abort rotation when it starts"
```

---

### Task 6: Verify end-to-end and deploy

**Files:**
- No new files; deploy `allstar_display.py`, `off_season_handler.py`, `main.py` to the Pi.

- [ ] **Step 1: Full suite + import smoke test**

```bash
python3 -m pytest tests/ -q
python3 -c "import ast; ast.parse(open('allstar_display.py').read()); ast.parse(open('main.py').read()); ast.parse(open('off_season_handler.py').read())"
```
Expected: all tests pass; no syntax errors.

- [ ] **Step 2: Live-data smoke test (no LED hardware)**

```bash
python3 - <<'EOF'
from unittest.mock import Mock
from allstar_display import AllStarDisplay

d = AllStarDisplay(Mock())
info = d.fetch_asg_info()
print('info:', info)
assert info and info['game_pk'] == 823443
print('window:', d.is_allstar_window())
print('derby active:', d._derby_active())
print('cubs all-stars:', d._get_cubs_allstars(info['game_pk']))
EOF
```
Expected: info populated, `window: True`, cubs all-stars includes Pete Crow-Armstrong.

- [ ] **Step 3: Deploy to Pi and reboot**

```bash
scp allstar_display.py off_season_handler.py main.py pi@192.168.4.244:/home/pi/
ssh pi@192.168.4.244 "sudo reboot"
```
(Files go to `/home/pi/` root, never `/home/pi/cubsmarquee/`. Reboot, not restart.)

- [ ] **Step 4: Confirm on-screen**

Derby promo should appear in the rotation this evening. Ask the user to confirm the look; pixel-level tweaks iterate on hardware per usual.
```

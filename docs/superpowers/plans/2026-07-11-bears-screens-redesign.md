# Bears Screens Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Bears LED screens with a compact 12-row sweater header, a live game screen showing possession / down & distance / last-play scroll / scoring celebrations, a pregame countdown card, a win celebration, and a PGA-style next-game card.

**Architecture:** All game screens live in `bears_display.py` (class `BearsDisplay`, public API `display_bears_info(duration)` unchanged). New pure-logic helpers are module-level functions in `bears_display.py` so tests can import them without hardware. The Bears news screen header lives in `off_season_handler.py` and is updated to match. Spec: `docs/superpowers/specs/2026-07-11-bears-screens-redesign-design.md`.

**Tech Stack:** Python 3.9+ (`from __future__ import annotations`), PIL, pendulum, ESPN JSON APIs, rgbmatrix (mocked in tests via `tests/conftest.py`). Tests run with `pytest tests/ -v` on any machine — `conftest.py` mocks `rgbmatrix`.

## Global Constraints

- Display is 96×48 pixels. `draw_text(font, x, y, color, text)` — **y is the text baseline**, not the top.
- Fonts and per-character widths: `small_bold` = 6 px wide × 13 tall, `tiny_bold` = 5×8, `tiny` = 5×7, `micro` = 4×6, `ultra_micro` = 4×6.
- Colors come from `scoreboard_config.Colors`: `BEARS_NAVY = (11, 22, 42)`, `BEARS_ORANGE = (200, 56, 3)`, `WHITE = (255, 255, 255)`, `YELLOW = (255, 223, 0)`.
- All timestamps display in `America/Chicago`.
- Missing ESPN fields must never raise — degrade by omitting the line (use `.get()` chains).
- Match existing code style: `print()` logging, broad `try/except` around display loops, type hints.
- Commit after every task. Run `pytest tests/ -v` before every commit; the whole suite must pass.

---

### Task 1: Pure-logic helper functions

**Files:**
- Modify: `bears_display.py` (add module-level functions after imports, before `class BearsDisplay`)
- Test: `tests/test_core_logic.py` (append new test class at end of file)

**Interfaces:**
- Consumes: nothing new (existing `Colors` from `scoreboard_config`)
- Produces (used by Tasks 3–7):
  - `extract_situation(competition: dict) -> dict` — keys `possession` (`'bears'`/`'opponent'`/`None`), `down_distance` (`str | None`), `is_red_zone` (`bool`), `last_play` (`str | None`)
  - `extract_broadcast(competition: dict) -> str | None`
  - `extract_week(event: dict) -> int | None`
  - `format_countdown(seconds: float) -> str`
  - `countdown_color(seconds: float, yellow_under: float, orange_under: float) -> tuple`
  - `celebration_message(delta: int) -> str`
  - `format_kickoff_time(dt) -> str` (takes a pendulum datetime)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_core_logic.py`:

```python
# ============================================================================
# Bears Display Helper Tests
# ============================================================================

class TestBearsSituation:
    """Tests for ESPN in-game situation extraction"""

    def _competition_with_situation(self, situation: dict | None) -> dict[str, Any]:
        competition: dict[str, Any] = {
            'competitors': [
                {'team': {'id': '9', 'abbreviation': 'GB'}},
                {'team': {'id': '3', 'abbreviation': 'CHI'}},
            ]
        }
        if situation is not None:
            competition['situation'] = situation
        return competition

    def test_bears_possession(self) -> None:
        from bears_display import extract_situation
        competition = self._competition_with_situation({'possession': '3'})
        assert extract_situation(competition)['possession'] == 'bears'

    def test_opponent_possession(self) -> None:
        from bears_display import extract_situation
        competition = self._competition_with_situation({'possession': '9'})
        assert extract_situation(competition)['possession'] == 'opponent'

    def test_down_distance_string(self) -> None:
        from bears_display import extract_situation
        competition = self._competition_with_situation({
            'shortDownDistanceText': '2nd & 8',
            'possessionText': 'CHI 34',
        })
        assert extract_situation(competition)['down_distance'] == '2ND & 8 CHI 34'

    def test_down_distance_without_possession_text(self) -> None:
        from bears_display import extract_situation
        competition = self._competition_with_situation(
            {'shortDownDistanceText': '3rd & 1'})
        assert extract_situation(competition)['down_distance'] == '3RD & 1'

    def test_red_zone_and_last_play(self) -> None:
        from bears_display import extract_situation
        competition = self._competition_with_situation({
            'isRedZone': True,
            'lastPlay': {'text': 'D.Swift up the middle for 5 yards'},
        })
        result = extract_situation(competition)
        assert result['is_red_zone'] is True
        assert result['last_play'] == 'D.Swift up the middle for 5 yards'

    def test_no_situation_returns_empty_defaults(self) -> None:
        from bears_display import extract_situation
        result = extract_situation(self._competition_with_situation(None))
        assert result == {
            'possession': None,
            'down_distance': None,
            'is_red_zone': False,
            'last_play': None,
        }


class TestBearsBroadcastAndWeek:
    """Tests for broadcast and week extraction from both ESPN shapes"""

    def test_scoreboard_broadcast_shape(self) -> None:
        from bears_display import extract_broadcast
        competition = {'broadcasts': [{'names': ['FOX']}]}
        assert extract_broadcast(competition) == 'FOX'

    def test_schedule_broadcast_shape(self) -> None:
        from bears_display import extract_broadcast
        competition = {'broadcasts': [{'media': {'shortName': 'CBS'}}]}
        assert extract_broadcast(competition) == 'CBS'

    def test_missing_broadcast(self) -> None:
        from bears_display import extract_broadcast
        assert extract_broadcast({}) is None
        assert extract_broadcast({'broadcasts': []}) is None

    def test_week_number(self) -> None:
        from bears_display import extract_week
        assert extract_week({'week': {'number': 15}}) == 15

    def test_missing_week(self) -> None:
        from bears_display import extract_week
        assert extract_week({}) is None


class TestBearsCountdown:
    """Tests for countdown formatting and color thresholds"""

    def test_days_and_hours(self) -> None:
        from bears_display import format_countdown
        # 2 days, 14 hours
        assert format_countdown(2 * 86400 + 14 * 3600) == '2D 14H'

    def test_hours_and_minutes(self) -> None:
        from bears_display import format_countdown
        assert format_countdown(3 * 3600 + 22 * 60) == '3H 22M'

    def test_minutes_only(self) -> None:
        from bears_display import format_countdown
        assert format_countdown(22 * 60) == '22M'

    def test_color_thresholds(self) -> None:
        from bears_display import countdown_color
        from scoreboard_config import Colors
        assert countdown_color(5 * 3600, 3 * 3600, 3600) == Colors.WHITE
        assert countdown_color(2 * 3600, 3 * 3600, 3600) == Colors.YELLOW
        assert countdown_color(30 * 60, 3 * 3600, 3600) == (255, 120, 0)


class TestBearsCelebrationAndTime:
    """Tests for celebration message selection and kickoff time formatting"""

    def test_celebration_messages(self) -> None:
        from bears_display import celebration_message
        assert celebration_message(6) == 'TOUCHDOWN!'
        assert celebration_message(7) == 'TOUCHDOWN!'
        assert celebration_message(8) == 'TOUCHDOWN!'
        assert celebration_message(3) == 'FIELD GOAL!'
        assert celebration_message(2) == 'SAFETY!'
        assert celebration_message(1) == 'BEARS SCORE!'

    def test_noon_kickoff(self) -> None:
        import pendulum
        from bears_display import format_kickoff_time
        dt = pendulum.datetime(2026, 12, 14, 12, 0, tz='America/Chicago')
        assert format_kickoff_time(dt) == 'NOON'

    def test_regular_kickoff(self) -> None:
        import pendulum
        from bears_display import format_kickoff_time
        dt = pendulum.datetime(2026, 12, 14, 19, 20, tz='America/Chicago')
        assert format_kickoff_time(dt) == '7:20 PM'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_core_logic.py -v -k "Bears"`
Expected: FAIL — `ImportError: cannot import name 'extract_situation' from 'bears_display'` (and similar for each helper).

- [ ] **Step 3: Write the implementations**

In `bears_display.py`, after the `if TYPE_CHECKING:` block and before `class BearsDisplay`, add:

```python
def extract_situation(competition: dict) -> dict:
    """Extract the live in-game situation from an ESPN competition dict.

    All fields are optional in the ESPN payload (absent between plays,
    at halftime, and for non-live games) and degrade to None/False.
    """
    result: dict[str, Any] = {
        'possession': None,
        'down_distance': None,
        'is_red_zone': False,
        'last_play': None,
    }
    situation = competition.get('situation')
    if not situation:
        return result

    possession_id = situation.get('possession')
    if possession_id:
        for competitor in competition.get('competitors', []):
            team = competitor.get('team', {})
            if str(team.get('id')) == str(possession_id):
                if team.get('abbreviation') == 'CHI':
                    result['possession'] = 'bears'
                else:
                    result['possession'] = 'opponent'
                break

    down_distance = situation.get('shortDownDistanceText')
    possession_text = situation.get('possessionText')
    if down_distance and possession_text:
        result['down_distance'] = f'{down_distance} {possession_text}'.upper()
    elif down_distance:
        result['down_distance'] = down_distance.upper()

    result['is_red_zone'] = bool(situation.get('isRedZone'))
    result['last_play'] = (situation.get('lastPlay') or {}).get('text')
    return result


def extract_broadcast(competition: dict) -> str | None:
    """TV network from either ESPN shape: scoreboard uses broadcasts[].names,
    the schedule endpoint uses broadcasts[].media.shortName."""
    broadcasts = competition.get('broadcasts') or []
    if not broadcasts:
        return None
    first = broadcasts[0]
    names = first.get('names')
    if names:
        return names[0]
    return (first.get('media') or {}).get('shortName')


def extract_week(event: dict) -> int | None:
    """NFL week number from an ESPN event"""
    return (event.get('week') or {}).get('number')


def format_countdown(seconds: float) -> str:
    """Format seconds until kickoff as '2D 14H', '3H 22M', or '22M'"""
    total_minutes = int(seconds // 60)
    days, remainder = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(remainder, 60)
    if days > 0:
        return f'{days}D {hours}H'
    if hours > 0:
        return f'{hours}H {minutes}M'
    return f'{minutes}M'


def countdown_color(seconds: float, yellow_under: float,
                    orange_under: float) -> RGBColor:
    """Countdown text color: white, yellow when close, orange when imminent"""
    if seconds < orange_under:
        return (255, 120, 0)
    if seconds < yellow_under:
        return Colors.YELLOW
    return Colors.WHITE


def celebration_message(delta: int) -> str:
    """Pick the scoring celebration text from the score change"""
    if delta in (6, 7, 8):
        return 'TOUCHDOWN!'
    if delta == 3:
        return 'FIELD GOAL!'
    if delta == 2:
        return 'SAFETY!'
    return 'BEARS SCORE!'


def format_kickoff_time(dt) -> str:
    """Kickoff time in Central, with 12:00 PM shown as NOON"""
    if dt.hour == 12 and dt.minute == 0:
        return 'NOON'
    return dt.format('h:mm A')
```

Note: `Any` and `RGBColor` are already imported in `bears_display.py` (`from typing import TYPE_CHECKING, Any` and `RGBColor` from `scoreboard_config`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_core_logic.py -v -k "Bears"`
Expected: all new tests PASS.

- [ ] **Step 5: Run the whole suite and commit**

Run: `pytest tests/ -v` — expected: all pass.

```bash
git add bears_display.py tests/test_core_logic.py
git commit -m "Add pure-logic helpers for the Bears screens redesign"
```

---

### Task 2: Compact sweater header in bears_display.py

**Files:**
- Modify: `bears_display.py` — `_create_bears_sweater_background` (lines ~37–50) and `_draw_sweater_header` (lines ~244–251)
- Test: `tests/test_core_logic.py` (append)

**Interfaces:**
- Produces: `_draw_sweater_header()` renders the full-frame cached navy background with orange stripes at y0–1 and y10–11 plus centered "CHICAGO BEARS"; content area is y12–47 on plain navy. All later tasks draw content on top of this.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_core_logic.py`:

```python
class TestBearsCompactHeader:
    """Tests for the compact sweater header background"""

    def test_compact_sweater_background_layout(self) -> None:
        from scoreboard_config import Colors
        from bears_display import BearsDisplay

        display = BearsDisplay.__new__(BearsDisplay)
        display.BEARS_NAVY = Colors.BEARS_NAVY
        display.BEARS_ORANGE = Colors.BEARS_ORANGE
        img = display._create_bears_sweater_background()

        assert img.size == (96, 48)
        # Orange stripes at y0-1 and y10-11
        for y in (0, 1, 10, 11):
            assert img.getpixel((48, y)) == Colors.BEARS_ORANGE
        # Navy band between stripes and navy content area below
        for y in (2, 9, 12, 30, 47):
            assert img.getpixel((48, y)) == Colors.BEARS_NAVY
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_core_logic.py::TestBearsCompactHeader -v`
Expected: FAIL — current stripes are at y4–6 and y22–24, so `img.getpixel((48, 0))` is navy, not orange.

- [ ] **Step 3: Replace the header methods**

In `bears_display.py`, replace `_create_bears_sweater_background` with:

```python
    def _create_bears_sweater_background(self) -> Image.Image:
        """Pre-generate compact Bears sweater header background for performance

        Full 96x48 navy frame with orange stripes at y0-1 and y10-11; the
        header band is y0-11 and content draws on navy from y12 down.
        """
        img = Image.new("RGB", (96, 48), self.BEARS_NAVY)
        pixels = img.load()
        for y in (0, 1, 10, 11):
            for x in range(96):
                pixels[x, y] = self.BEARS_ORANGE
        print("Bears sweater background cached")
        return img
```

Replace `_draw_sweater_header` with:

```python
    def _draw_sweater_header(self):
        """Draw the compact Bears sweater header using the cached background"""
        self.manager.set_image(self._bears_sweater_bg, 0, 0)

        # "CHICAGO BEARS" in tiny_bold (5px/char, 13 chars = 65px), centered
        self.manager.draw_text('tiny_bold', 15, 9,
                               self.BEARS_WHITE, 'CHICAGO BEARS')
```

Do NOT touch the old content-drawing coordinates in `_display_game_day` / `_display_next_game` yet — they still render (in the wrong place visually) until Tasks 4–7 rework them. The suite stays green.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_core_logic.py::TestBearsCompactHeader -v` — expected: PASS.

- [ ] **Step 5: Run the whole suite and commit**

Run: `pytest tests/ -v` — expected: all pass.

```bash
git add bears_display.py tests/test_core_logic.py
git commit -m "Shrink the Bears sweater header to a compact 12-row band"
```

---

### Task 3: Extend `_get_current_scores` with situation fields

**Files:**
- Modify: `bears_display.py` — `_get_current_scores` (lines ~152–242)
- Test: `tests/test_core_logic.py` (append)

**Interfaces:**
- Consumes: `extract_situation(competition)` from Task 1.
- Produces: the dict returned by `_get_current_scores` gains keys `possession`, `down_distance`, `is_red_zone`, `last_play` (same semantics as `extract_situation`). Tasks 4 uses these.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_core_logic.py` (the `sample_bears_event` fixture is STATUS_FINAL with scores present, so `_get_current_scores` takes no network path):

```python
class TestBearsCurrentScores:
    """Tests for the extended _get_current_scores return value"""

    def test_includes_situation_fields(
        self, sample_bears_event: dict[str, Any]
    ) -> None:
        from bears_display import BearsDisplay

        display = BearsDisplay.__new__(BearsDisplay)
        result = display._get_current_scores(sample_bears_event, '401547417')

        assert result['bears_score'] == '17'
        assert result['opp_score'] == '24'
        assert result['possession'] is None
        assert result['down_distance'] is None
        assert result['is_red_zone'] is False
        assert result['last_play'] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_core_logic.py::TestBearsCurrentScores -v`
Expected: FAIL — `KeyError: 'possession'`.

- [ ] **Step 3: Extend the return dict**

In `_get_current_scores`, just before the `return {` statement, add:

```python
            # Live in-game situation (possession, down & distance, last play).
            # Uses the final `competition` value, which is the live scoreboard
            # data when a refetch happened above.
            situation = extract_situation(competition)
```

Then replace the `return {` block with:

```python
            return {
                'status': status,
                'game_time': game_time_raw,
                'bears_score': bears_score,
                'opp_score': opp_score,
                'opponent_abbr': opponent_abbr,
                'opponent_name': opponent_name,
                'possession': situation['possession'],
                'down_distance': situation['down_distance'],
                'is_red_zone': situation['is_red_zone'],
                'last_play': situation['last_play'],
            }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_core_logic.py::TestBearsCurrentScores -v` — expected: PASS.

- [ ] **Step 5: Run the whole suite and commit**

Run: `pytest tests/ -v` — expected: all pass.

```bash
git add bears_display.py tests/test_core_logic.py
git commit -m "Extract possession, down & distance, and last play for Bears games"
```

---

### Task 4: Live game screen — possession, situation, clock, last-play scroll, celebrations

**Files:**
- Modify: `bears_display.py` — rewrite `_display_game_day` (lines ~273–388), add methods `_draw_live_content`, `_draw_possession_dot`, `_scroll_last_play`, `_play_scoring_celebration`, `_draw_final_content` (placeholder holding current final logic), `_draw_pregame_content` (placeholder holding current pregame logic)
- Test: full suite (rendering is verified on hardware; the logic pieces were unit-tested in Tasks 1 and 3)

**Interfaces:**
- Consumes: `celebration_message(delta)` (Task 1), extended `_get_current_scores` (Task 3), `_draw_sweater_header` (Task 2), `manager.get_frame_copy()`, `Fonts.CHAR_WIDTH_MICRO`, `get_scroll_delay`.
- Produces: `_draw_pregame_content(self, game)` and `_draw_final_content(self, score_data, frame_count)` — Tasks 5 and 6 replace these bodies; signatures fixed here.

- [ ] **Step 1: Update imports**

In `bears_display.py`, change the config import line to include `Fonts`:

```python
from scoreboard_config import (
    Colors, Fonts, GameConfig, RGBColor, get_scroll_delay, load_user_config)
```

Add a gray color in `__init__` after `self.BEARS_WHITE`:

```python
        self.BEARS_GRAY: RGBColor = (170, 170, 170)
```

- [ ] **Step 2: Rewrite `_display_game_day`**

Replace the whole method with:

```python
    def _display_game_day(self, game, duration):
        """Display today's Bears game with live score updates"""
        start_time = time.time()
        last_score_update = 0
        frame_count = 0
        prev_bears_score = None
        last_scrolled_play = None

        try:
            game_id = game.get('id')

            score_data = self._get_current_scores(game, game_id)
            if not score_data:
                return

            try:
                prev_bears_score = int(float(score_data['bears_score']))
            except (ValueError, TypeError):
                prev_bears_score = None

            print(f"Game status: {score_data['status']}, "
                  f"Detail: {score_data['game_time']}")

            while time.time() - start_time < duration:
                # Refresh live scores every LIVE_SCORE_UPDATE_INTERVAL seconds
                current_time = time.time()
                if (score_data['status'] == 'STATUS_IN_PROGRESS' and
                        current_time - last_score_update >= self.live_update_interval):
                    print("Updating live scores...")
                    updated_data = self._get_current_scores(game, game_id)

                    if updated_data:
                        try:
                            new_score = int(float(updated_data['bears_score']))
                        except (ValueError, TypeError):
                            new_score = prev_bears_score

                        # Bears scored since the last poll - celebrate
                        if (prev_bears_score is not None and
                                new_score is not None and
                                new_score > prev_bears_score):
                            self._play_scoring_celebration(
                                new_score - prev_bears_score)

                        if new_score is not None:
                            prev_bears_score = new_score
                        score_data = updated_data
                        print(f"Scores updated - Bears: {score_data['bears_score']}, "
                              f"Opponent: {score_data['opp_score']}")

                    last_score_update = current_time

                self.manager.clear_canvas()
                self._draw_sweater_header()

                status = score_data['status']
                if status == 'STATUS_IN_PROGRESS':
                    self._draw_live_content(score_data, frame_count)
                elif status == 'STATUS_FINAL':
                    self._draw_final_content(score_data, frame_count)
                else:
                    self._draw_pregame_content(game)

                self.manager.swap_canvas()
                frame_count += 1
                time.sleep(0.5)

                # Scroll each new play description once across the bottom strip
                if status == 'STATUS_IN_PROGRESS':
                    play = score_data.get('last_play')
                    if play and play != last_scrolled_play:
                        self._scroll_last_play(play)
                        last_scrolled_play = play

        except Exception as e:
            print(f"Error displaying Bears game: {e}")
            import traceback
            traceback.print_exc()
```

- [ ] **Step 3: Add the live-content drawing methods**

Add after `_draw_sweater_header`:

```python
    def _draw_live_content(self, score_data, frame_count):
        """Draw scores, possession dot, down & distance, and clock (y12-47)"""
        bears_score = score_data['bears_score']
        opp_score = score_data['opp_score']
        opp_abbr = score_data['opponent_abbr']

        # Score row
        self.manager.draw_text('small_bold', 8, 24,
                               self.BEARS_WHITE, f'CHI {bears_score}')
        self.manager.draw_text('small_bold', 52, 24,
                               self.BEARS_WHITE, f'{opp_abbr} {opp_score}')

        # Orange possession dot beside the team with the ball
        possession = score_data.get('possession')
        if possession == 'bears':
            self._draw_possession_dot(3)
        elif possession == 'opponent':
            self._draw_possession_dot(91)

        # Down & distance; red and blinking in the red zone
        down_distance = score_data.get('down_distance')
        if down_distance:
            if score_data.get('is_red_zone'):
                color = (255, 60, 60) if frame_count % 2 == 0 else None
            else:
                color = self.BEARS_WHITE
            if color:
                x = max(0, (96 - len(down_distance) * Fonts.CHAR_WIDTH_TINY) // 2)
                self.manager.draw_text('tiny', x, 31, color, down_distance)

        # Quarter / clock
        game_time = score_data.get('game_time') or ''
        if game_time:
            x = max(0, (96 - len(game_time) * Fonts.CHAR_WIDTH_MICRO) // 2)
            self.manager.draw_text('micro', x, 38, self.BEARS_ORANGE, game_time)

    def _draw_possession_dot(self, x):
        """Draw a 3x3 orange football dot at the given x, beside the score row"""
        for px in range(x, x + 3):
            for py in range(18, 21):
                self.manager.draw_pixel(px, py, *self.BEARS_ORANGE)

    def _scroll_last_play(self, text):
        """Scroll a play description once across the bottom strip (y40-47)"""
        original = self.manager.get_frame_copy()
        snapshot = original.copy()

        # Clear the strip to plain navy so the text scrolls over clean rows
        pixels = snapshot.load()
        for y in range(40, 48):
            for x in range(96):
                pixels[x, y] = self.BEARS_NAVY

        text = text.upper()
        text_width = len(text) * Fonts.CHAR_WIDTH_MICRO
        config = self._load_scroll_config()
        scroll_delay = get_scroll_delay(config.get('scroll_speed_bears', 5))

        scroll_x = 96
        while scroll_x + text_width >= 0:
            self.manager.set_image(snapshot, 0, 0)
            self.manager.draw_text('micro', scroll_x, 46,
                                   self.BEARS_WHITE, text)
            self.manager.swap_canvas()
            time.sleep(scroll_delay)
            scroll_x -= 1

        # Restore the pre-scroll frame
        self.manager.set_image(original, 0, 0)
        self.manager.swap_canvas()

    def _play_scoring_celebration(self, delta):
        """Flash a scoring message for ~4 seconds when the Bears score"""
        message = celebration_message(delta)
        x = max(0, (96 - len(message) * Fonts.CHAR_WIDTH_SMALL) // 2)

        for i in range(8):
            self.manager.clear_canvas()
            self._draw_sweater_header()
            color = self.BEARS_ORANGE if i % 2 == 0 else self.BEARS_WHITE
            self.manager.draw_text('small_bold', x, 32, color, message)
            self.manager.swap_canvas()
            time.sleep(0.5)
```

- [ ] **Step 4: Add placeholder content methods holding today's behavior**

These keep the pregame and final branches working until Tasks 5 and 6 replace their bodies. Add after `_play_scoring_celebration`:

```python
    def _draw_pregame_content(self, game):
        """Draw the pregame card (game today, not yet started)"""
        competition = game['competitions'][0]
        home_team = competition['competitors'][0]
        away_team = competition['competitors'][1]
        bears_home = home_team['team']['abbreviation'] == 'CHI'
        opponent = away_team if bears_home else home_team
        opponent_name = opponent['team']['displayName']

        game_datetime = pendulum.parse(game['date'])
        game_datetime_central = game_datetime.in_timezone('America/Chicago')
        display_time = game_datetime_central.format('h:mm A')

        self.manager.draw_text('tiny', 28, 20, self.BEARS_WHITE, 'TODAY vs')

        opp_x = max(5, (96 - len(opponent_name) * 5) // 2)
        self.manager.draw_text('tiny', opp_x, 30, self.BEARS_ORANGE, opponent_name)

        time_x = max(5, (96 - len(display_time) * 4) // 2)
        self.manager.draw_text('micro', time_x, 40, self.BEARS_WHITE, display_time)

    def _draw_final_content(self, score_data, frame_count):
        """Draw the final-score screen"""
        bears_score = score_data['bears_score']
        opp_score = score_data['opp_score']
        opp_abbr = score_data['opponent_abbr']

        self.manager.draw_text('small_bold', 8, 24,
                               self.BEARS_WHITE, f'CHI {bears_score}')
        self.manager.draw_text('small_bold', 52, 24,
                               self.BEARS_WHITE, f'{opp_abbr} {opp_score}')

        try:
            bears_score_int = int(float(bears_score)) if bears_score else 0
            opp_score_int = int(float(opp_score)) if opp_score else 0
            result = 'WIN' if bears_score_int > opp_score_int else 'LOSS'
        except (ValueError, TypeError):
            result = 'FINAL'

        result_color = (0, 200, 0) if result == 'WIN' else (200, 0, 0)
        self.manager.draw_text('tiny_bold', 37, 36, result_color, result)
```

- [ ] **Step 5: Run the whole suite and commit**

Run: `pytest tests/ -v` — expected: all pass (no rendering tests exist; this confirms no imports or signatures broke).

```bash
git add bears_display.py
git commit -m "Show possession, down & distance, last-play scroll, and scoring celebrations for live Bears games"
```

---

### Task 5: Pregame screen — countdown, week, and TV network

**Files:**
- Modify: `bears_display.py` — replace the body of `_draw_pregame_content` (added in Task 4)

**Interfaces:**
- Consumes: `format_kickoff_time`, `format_countdown`, `countdown_color`, `extract_week`, `extract_broadcast` (Task 1); `Fonts` char widths.
- Produces: nothing new (leaf rendering method).

- [ ] **Step 1: Replace `_draw_pregame_content`**

```python
    def _draw_pregame_content(self, game):
        """Draw the pregame card: opponent, kickoff, countdown, week/TV"""
        competition = game['competitions'][0]
        home_team = competition['competitors'][0]
        away_team = competition['competitors'][1]
        bears_home = home_team['team']['abbreviation'] == 'CHI'
        opponent = away_team if bears_home else home_team
        vs_at = 'VS' if bears_home else 'AT'

        # Nickname always fits 96px (longest is BUCCANEERS = 50px in tiny_bold)
        opp_name = (opponent['team'].get('shortDisplayName')
                    or opponent['team']['displayName']).upper()

        kickoff = pendulum.parse(game['date']).in_timezone('America/Chicago')

        line1 = f'TODAY {vs_at}'
        x = max(0, (96 - len(line1) * Fonts.CHAR_WIDTH_TINY) // 2)
        self.manager.draw_text('tiny', x, 19, self.BEARS_WHITE, line1)

        x = max(0, (96 - len(opp_name) * Fonts.CHAR_WIDTH_TINY) // 2)
        self.manager.draw_text('tiny_bold', x, 27, self.BEARS_ORANGE, opp_name)

        time_str = format_kickoff_time(kickoff)
        x = max(0, (96 - len(time_str) * Fonts.CHAR_WIDTH_TINY) // 2)
        self.manager.draw_text('tiny', x, 35, self.BEARS_WHITE, time_str)

        # Live countdown, recomputed each frame
        seconds = (kickoff - pendulum.now('America/Chicago')).total_seconds()
        if seconds > 0:
            countdown = f'KICKOFF IN {format_countdown(seconds)}'
            color = countdown_color(seconds, yellow_under=3 * 3600,
                                    orange_under=3600)
            x = max(0, (96 - len(countdown) * Fonts.CHAR_WIDTH_MICRO) // 2)
            self.manager.draw_text('micro', x, 42, color, countdown)

        # Week and TV network, either part omitted when missing
        parts = []
        week = extract_week(game)
        if week:
            parts.append(f'WK {week}')
        network = extract_broadcast(competition)
        if network:
            parts.append(network.upper())
        if parts:
            line = ' '.join(parts)
            x = max(0, (96 - len(line) * Fonts.CHAR_WIDTH_MICRO) // 2)
            self.manager.draw_text('micro', x, 47, self.BEARS_GRAY, line)
```

Layout note (all y values are baselines): `TODAY VS` tiny y19 (spans 13–19), opponent tiny_bold y27 (20–27), time tiny y35 (29–35), countdown micro y42 (37–42), week/TV micro y47 (42–47 — one row below the countdown; micro's 6px height makes rows 42 shared but glyph overlap is avoided because baseline-42 text occupies y37–42 and baseline-47 occupies y42–47 with the shared row being descender space).

- [ ] **Step 2: Run the whole suite and commit**

Run: `pytest tests/ -v` — expected: all pass.

```bash
git add bears_display.py
git commit -m "Add kickoff countdown, week, and TV network to the Bears pregame screen"
```

---

### Task 6: Final screen — BEARS WIN! celebration

**Files:**
- Modify: `bears_display.py` — replace the win/loss label section of `_draw_final_content` (added in Task 4)

**Interfaces:**
- Consumes: `frame_count` parameter (0.5 s per frame; the caller increments it every loop iteration).
- Produces: nothing new (leaf rendering method).

- [ ] **Step 1: Replace `_draw_final_content`**

```python
    def _draw_final_content(self, score_data, frame_count):
        """Draw the final-score screen with a win celebration"""
        bears_score = score_data['bears_score']
        opp_score = score_data['opp_score']
        opp_abbr = score_data['opponent_abbr']

        self.manager.draw_text('small_bold', 8, 24,
                               self.BEARS_WHITE, f'CHI {bears_score}')
        self.manager.draw_text('small_bold', 52, 24,
                               self.BEARS_WHITE, f'{opp_abbr} {opp_score}')

        try:
            won = int(float(bears_score)) > int(float(opp_score))
        except (ValueError, TypeError):
            won = None

        if won:
            # Alternate orange/white every second (frames are 0.5s)
            message = 'BEARS WIN!'
            if (frame_count // 2) % 2 == 0:
                color = self.BEARS_ORANGE
            else:
                color = self.BEARS_WHITE
            x = max(0, (96 - len(message) * Fonts.CHAR_WIDTH_TINY) // 2)
            self.manager.draw_text('tiny_bold', x, 37, color, message)
        elif won is False:
            self.manager.draw_text('tiny_bold', 38, 37, (200, 0, 0), 'LOSS')

        x = max(0, (96 - 5 * Fonts.CHAR_WIDTH_MICRO) // 2)
        self.manager.draw_text('micro', x, 46, self.BEARS_ORANGE, 'FINAL')
```

- [ ] **Step 2: Run the whole suite and commit**

Run: `pytest tests/ -v` — expected: all pass.

```bash
git add bears_display.py
git commit -m "Flash BEARS WIN! on the final screen after a Bears victory"
```

---

### Task 7: Next-game card (no game today)

**Files:**
- Modify: `bears_display.py` — rewrite `_display_next_game` (lines ~390–449)

**Interfaces:**
- Consumes: `format_kickoff_time`, `format_countdown`, `countdown_color`, `extract_week`, `extract_broadcast` (Task 1); `_draw_sweater_header` (Task 2).
- Produces: nothing new. The scrolling one-liner and its `scroll_speed_bears` config lookup go away (the config key stays — the live last-play scroll still uses it).

- [ ] **Step 1: Rewrite `_display_next_game`**

Replace the whole method with:

```python
    def _display_next_game(self, game, duration):
        """Display the next upcoming Bears game as a structured card"""
        start_time = time.time()

        try:
            competition = game['competitions'][0]
            home_team = competition['competitors'][0]
            away_team = competition['competitors'][1]
            bears_home = home_team['team']['abbreviation'] == 'CHI'
            opponent = away_team if bears_home else home_team
            vs_at = 'VS' if bears_home else 'AT'
            opp_name = (opponent['team'].get('shortDisplayName')
                        or opponent['team']['displayName']).upper()
            opp_line = f'{vs_at} {opp_name}'

            kickoff = pendulum.parse(game['date']).in_timezone('America/Chicago')
            date_line = (f"{kickoff.format('ddd MMM D').upper()} "
                         f"{format_kickoff_time(kickoff)}")

            parts = []
            week = extract_week(game)
            if week:
                parts.append(f'WK {week}')
            network = extract_broadcast(competition)
            if network:
                parts.append(network.upper())
            week_line = ' '.join(parts)

            while time.time() - start_time < duration:
                self.manager.clear_canvas()
                self._draw_sweater_header()

                self.manager.draw_text('ultra_micro', 36, 18,
                                       (150, 150, 150), 'UP NEXT')

                x = max(0, (96 - len(opp_line) * Fonts.CHAR_WIDTH_TINY) // 2)
                self.manager.draw_text('tiny_bold', x, 26,
                                       self.BEARS_WHITE, opp_line)

                x = max(0, (96 - len(date_line) * Fonts.CHAR_WIDTH_TINY) // 2)
                self.manager.draw_text('tiny', x, 34,
                                       self.BEARS_WHITE, date_line)

                if week_line:
                    x = max(0, (96 - len(week_line) * Fonts.CHAR_WIDTH_MICRO) // 2)
                    self.manager.draw_text('micro', x, 41,
                                           self.BEARS_GRAY, week_line)

                seconds = (kickoff
                           - pendulum.now('America/Chicago')).total_seconds()
                if seconds > 0:
                    countdown = f'IN {format_countdown(seconds)}'
                    color = countdown_color(seconds, yellow_under=24 * 3600,
                                            orange_under=3 * 3600)
                    x = max(0, (96 - len(countdown) * Fonts.CHAR_WIDTH_MICRO) // 2)
                    self.manager.draw_text('micro', x, 47, color, countdown)

                self.manager.swap_canvas()
                time.sleep(0.5)

        except Exception as e:
            print(f"Error displaying Bears game: {e}")
            import traceback
            traceback.print_exc()
```

- [ ] **Step 2: Clean up orphans**

`_display_next_game` no longer uses `get_scroll_delay` or `_load_scroll_config`, but both are still used by `_scroll_last_play` (Task 4) — leave them. Verify nothing else broke:

Run: `python3 -c "import ast; ast.parse(open('bears_display.py').read())"` — expected: no output.

- [ ] **Step 3: Run the whole suite and commit**

Run: `pytest tests/ -v` — expected: all pass.

```bash
git add bears_display.py
git commit -m "Replace the Bears next-game scroll with a structured card and countdown"
```

---

### Task 8: Compact header for the Bears news screen

**Files:**
- Modify: `off_season_handler.py` — `_create_bears_sweater_background` (lines ~145–158), `_draw_sweater_header` (lines ~1064–1071), `_display_bears_loading` (lines ~1024–1042), `display_bears_news` scroll baseline (line ~1115)

**Interfaces:**
- Consumes: nothing from earlier tasks (this file has its own duplicate header code by existing design).
- Produces: the Bears news screen and loading screen render with the same compact header as `bears_display.py`.

- [ ] **Step 1: Replace the background and header methods**

Replace `_create_bears_sweater_background` in `off_season_handler.py` with (same layout as Task 2):

```python
    def _create_bears_sweater_background(self) -> Image.Image:
        """Pre-generate compact Bears sweater header background for performance"""
        img = Image.new("RGB", (96, 48), self.BEARS_NAVY)
        pixels = img.load()
        for y in (0, 1, 10, 11):
            for x in range(96):
                pixels[x, y] = self.BEARS_ORANGE
        print("Bears sweater background cached")
        return img
```

Replace `_draw_sweater_header` with:

```python
    def _draw_sweater_header(self):
        """Draw the compact Bears sweater header using the cached image"""
        self.manager.set_image(self._bears_sweater_bg, 0, 0)

        # "CHICAGO BEARS" in tiny_bold (5px/char, 13 chars = 65px), centered
        self.manager.draw_text('tiny_bold', 15, 9,
                               self.BEARS_WHITE, 'CHICAGO BEARS')
```

- [ ] **Step 2: Update the loading screen**

In `_display_bears_loading`, replace the two draw calls after `set_image` (the inline "CHICAGO BEARS" small_bold draw at y19 and the message draw) so it reuses the header and centers the message in the content area:

```python
    def _display_bears_loading(self, message="FETCHING NEWS..."):
        """Display loading message with Bears sweater header using cached image"""
        self.manager.clear_canvas()

        self._draw_sweater_header()

        # Display loading message centered in the content area
        message_width = len(message) * 5
        x_pos = max(0, (96 - message_width) // 2)
        self.manager.draw_text('small_bold', x_pos, 32,
                               self.BEARS_WHITE, message)

        self.manager.swap_canvas()
```

- [ ] **Step 3: Recenter the news scroll**

In `display_bears_news`, change the scroll draw from baseline 44 to the vertical center of the content area (medium_bold is 18px tall; baseline 32 spans y15–32):

```python
                # Draw scrolling text
                self.manager.draw_text(
                    'medium_bold', int(self.scroll_position), 32,
                    self.BEARS_WHITE, current_headline
                )
```

- [ ] **Step 4: Run the whole suite and commit**

Run: `pytest tests/ -v` — expected: all pass.

```bash
git add off_season_handler.py
git commit -m "Match the Bears news screen to the compact sweater header"
```

---

### Task 9: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Run the complete test suite**

Run: `pytest tests/ -v`
Expected: all tests pass, including the new `TestBears*` classes.

- [ ] **Step 2: Syntax-check both modified modules**

Run: `python3 -m py_compile bears_display.py off_season_handler.py`
Expected: no output.

- [ ] **Step 3: Confirm spec coverage**

Check each spec section has landed: compact header (Tasks 2, 8), live screen with possession dot / situation / clock / last-play scroll / celebrations (Tasks 3–4), pregame countdown + week/TV (Task 5), win celebration (Task 6), next-game card (Task 7), news screen (Task 8).

- [ ] **Step 4: Report ready for hardware verification**

Rendering cannot be verified off-Pi. Tell the user the work is ready to deploy: copy the changed files to `/home/pi/` on cubsmarquee-one (192.168.4.244) with scp, then `sudo reboot` (never just restart the service). Do not deploy without the user's go-ahead.

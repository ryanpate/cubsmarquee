# Holiday Facts Screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On each of 18 holidays, and only on that date, show a pixel-art title card and then facts about the holiday, switchable from the admin console.

**Architecture:** A new `holiday_display.py` holds the calendar (pure functions), the per-holiday table and the renderer. Art is 36 PNGs in `holidays/`; lettering and animation are drawn by code on top. One method on `OffSeasonHandler` runs the screen, called from the rotation slot and from the pre-game loop.

**Tech Stack:** Python 3.9+, Pillow, pendulum, Flask (admin), pytest with `rgbmatrix` mocked by `tests/conftest.py`.

**Spec:** `docs/superpowers/specs/2026-11-26-holiday-facts-screen-design.md`

## Global Constraints

- "Today" is the date in `America/Chicago`.
- No new pip dependency; Easter is computed in code.
- Matrix is 96x48. Card PNGs are exactly 96x48, band PNGs exactly 96x30, both RGB, with no lettering in them.
- Facts: uppercase, plain ASCII, 100 characters or fewer, at least 15 per holiday, family friendly, well established. Good Friday facts carry no exclamation marks.
- One holiday per day; `palm_sunday`, `good_friday` and `easter` win a clash.
- `palm_sunday` and `good_friday` use effect `none`.
- Slot is `GameConfig.HOLIDAY_FACTS_DURATION = 2` minutes; card is `GameConfig.HOLIDAY_CARD_SECONDS = 8` seconds.
- Config keys: `enable_holiday_facts` (default `True`), `scroll_speed_holiday_facts` (default `5`), `holiday_preview` (slug, hand-set, not in admin).
- Match existing style; `from __future__ import annotations` and type hints in new modules. Touch nothing unrelated.
- Each task ends with a commit on the current branch. Nothing is pushed.

## Review Focus

1. `holiday_preview` holds a typo or stale slug: the screen falls back to the real date instead of crashing. (Task 4)
2. `holiday_facts.json` or a PNG is missing on a Pi: `display_holiday` returns `False`; the pre-game loop keeps running. (Tasks 4, 5)
3. An effect draws below row 29 on the band and corrupts the scrolling fact. (Task 4)
4. The holiday pass raises inside the pre-game loop: next-game and standings still show. (Task 5)
5. Consecutive holidays (Dec 31 then Jan 1) or a slot that spans midnight: the deck belongs to the holiday being shown, never the previous day's. (Task 4)

---

### Task 1: Calendar

**Files:**
- Create: `holiday_display.py`
- Test: `tests/test_holiday_display.py`

**Interfaces:**
- Produces:
  - `easter_date(year: int) -> datetime.date`
  - `TextLine(font: str, x: int, baseline: int, color: RGBColor, text: str)` frozen dataclass; `font` is a key of `ScoreboardManager.FONT_MAPPING`
  - `Holiday(slug: str, rule: Callable[[int], date], effect: str, card_text: tuple[TextLine, ...], band_text: tuple[TextLine, ...], effect_colors: tuple[RGBColor, ...] = ())` frozen dataclass
  - `EFFECTS: tuple[str, ...] = ('snow', 'leaves', 'hearts', 'confetti', 'fireworks', 'twinkle', 'none')`
  - `HOLIDAYS: tuple[Holiday, ...]` (18 rows, slugs and rules from the spec table)
  - `HOLIDAYS_BY_SLUG: dict[str, Holiday]`
  - `holiday_on(day: datetime.date) -> Holiday | None`

- [ ] **Step 1: Write the failing tests**

```python
from datetime import date
import holiday_display as hd

def test_easter_dates():
    assert hd.easter_date(2026) == date(2026, 4, 5)
    assert hd.easter_date(2027) == date(2027, 3, 28)
    assert hd.easter_date(2028) == date(2028, 4, 16)

@pytest.mark.parametrize('day, slug', [
    (date(2026, 11, 26), 'thanksgiving'), (date(2027, 11, 25), 'thanksgiving'),
    (date(2027, 5, 9), 'mothers_day'), (date(2027, 6, 20), 'fathers_day'),
    (date(2027, 3, 21), 'palm_sunday'), (date(2027, 3, 26), 'good_friday'),
    (date(2026, 12, 24), 'christmas_eve'), (date(2026, 12, 25), 'christmas'),
    (date(2026, 12, 31), 'new_years_eve'), (date(2027, 1, 1), 'new_years_day'),
])
def test_holiday_on(day, slug):
    assert hd.holiday_on(day).slug == slug

def test_ordinary_day_is_none():
    assert hd.holiday_on(date(2026, 11, 27)) is None

def test_christian_day_wins_a_clash():
    assert hd.holiday_on(date(2029, 4, 1)).slug == 'easter'       # vs april_fools
    assert hd.holiday_on(date(2011, 4, 22)).slug == 'good_friday'  # vs earth_day

def test_table_is_complete():
    assert len(hd.HOLIDAYS) == 18
    assert len(hd.HOLIDAYS_BY_SLUG) == 18
    for h in hd.HOLIDAYS:
        assert h.effect in hd.EFFECTS
        assert h.card_text and h.band_text
    assert hd.HOLIDAYS_BY_SLUG['good_friday'].effect == 'none'
    assert hd.HOLIDAYS_BY_SLUG['palm_sunday'].effect == 'none'
```

- [ ] **Step 2: Run** `pytest tests/test_holiday_display.py -v` — expect import failure.
- [ ] **Step 3: Implement.** Easter by the anonymous Gregorian (Meeus/Jones/Butcher) algorithm. Fixed dates and nth-weekday rules as small helpers. Greetings per the spec table; text positions are first guesses here and get tuned against previews in Task 4.
- [ ] **Step 4: Run** the same command — expect all pass.
- [ ] **Step 5: Commit** `Add the holiday calendar for the holiday facts screen`.

### Task 2: Facts

**Files:**
- Create: `holiday_facts.json`
- Modify: `holiday_display.py`
- Test: `tests/test_holiday_display.py`

**Interfaces:**
- Consumes: `HOLIDAYS`
- Produces: `load_holiday_facts() -> dict[str, list[str]]`, reading `holiday_facts.json` through `teams.data_path_candidates`; returns `{}` when no file is readable.

- [ ] **Step 1: Write the failing test**

```python
def test_every_holiday_has_facts():
    facts = hd.load_holiday_facts()
    for h in hd.HOLIDAYS:
        deck = facts[h.slug]
        assert len(deck) >= 15, h.slug
        assert len(set(deck)) == len(deck), h.slug
        for fact in deck:
            assert fact == fact.upper() and fact.isascii(), fact
            assert 0 < len(fact) <= 100, fact
    assert not any('!' in f for f in facts['good_friday'])
    assert set(facts) == {h.slug for h in hd.HOLIDAYS}
```

- [ ] **Step 2: Run** — expect failure.
- [ ] **Step 3: Write the facts and the loader.** Shape `{"<slug>": ["FACT", ...]}`. Follow the spec's content rules: Christian calendar days in the register of `bible_facts.json`; Easter covers both the resurrection and the traditions; nothing doubtful, no statistics that go stale.
- [ ] **Step 4: Run** — expect pass.
- [ ] **Step 5: Commit** `Add facts for the 18 holidays`.

### Task 3: Art

**Files:**
- Create: `dev/draw_holiday_art.py`, `holidays/<slug>_card.png` and `holidays/<slug>_band.png` for all 18 slugs
- Test: `tests/test_holiday_display.py`

**Interfaces:**
- Consumes: `HOLIDAYS`
- Produces: `holiday_display.ART_DIR = 'holidays'`; files named `<slug>_card.png` (96x48) and `<slug>_band.png` (96x30).

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.parametrize('slug', [h.slug for h in hd.HOLIDAYS])
def test_art_exists_at_exact_size(slug):
    for suffix, size in (('card', (96, 48)), ('band', (96, 30))):
        with Image.open(f'{hd.ART_DIR}/{slug}_{suffix}.png') as im:
            assert im.size == size and im.mode == 'RGB'
```

- [ ] **Step 2: Run** — expect failure.
- [ ] **Step 3: Write `dev/draw_holiday_art.py`** and run it from the repo root. One drawing function per holiday producing both PNGs, subjects from the spec table, no lettering, room left for the text. The module docstring warns that re-running overwrites hand edits.
- [ ] **Step 4: Run** the test — expect pass. Look at every PNG at 8x and fix anything unreadable before moving on.
- [ ] **Step 5: Commit** `Add pixel art for the 18 holidays`.

### Task 4: Display, effects and previews

**Files:**
- Modify: `holiday_display.py`, `scoreboard_config.py` (`GameConfig`), `.gitignore`
- Create: `tools/render_holiday_previews.py`
- Test: `tests/test_holiday_display.py`

**Interfaces:**
- Consumes: Tasks 1–3; `ScoreboardManager.set_image/draw_pixel/draw_text/clear_canvas/swap_canvas`; `load_user_config`, `get_scroll_delay`
- Produces:
  - `GameConfig.HOLIDAY_FACTS_DURATION: int = 2`, `GameConfig.HOLIDAY_CARD_SECONDS: int = 8`
  - `draw_effect(manager, effect: str, tick: float, height: int, colors: tuple[RGBColor, ...] = ()) -> None` — a pure function of `tick`, like `CelebrationDisplay._draw_confetti`, drawing only on rows `< height`
  - `class HolidayDisplay(manager)` with `current_holiday(today: date | None = None) -> Holiday | None`, `draw_card(holiday, tick: float) -> None`, `draw_band(holiday, tick: float, fact: str, scroll_x: int) -> None` (neither swaps the canvas), and `display_holiday(duration: int = 120) -> bool`

- [ ] **Step 1: Write the failing tests** (a `MagicMock` manager records calls)

```python
def test_effects_stay_inside_the_band(effect in hd.EFFECTS, tick in (0.0, 3.7, 61.2)):
    hd.draw_effect(manager, effect, tick, 30)
    assert all(0 <= x < 96 and 0 <= y < 30 for x, y, *_ in pixel_calls(manager))

def test_none_effect_draws_nothing():           # draw_pixel never called

def test_preview_key_forces_a_holiday(monkeypatch):
    # load_user_config -> {'holiday_preview': 'halloween'}
    assert display.current_holiday(date(2026, 3, 3)).slug == 'halloween'

def test_bad_preview_slug_falls_back_to_the_date(monkeypatch):
    # {'holiday_preview': 'haloween'}
    assert display.current_holiday(date(2026, 3, 3)) is None
    assert display.current_holiday(date(2026, 12, 25)).slug == 'christmas'

def test_not_a_holiday_returns_false_without_drawing():
    # current_holiday -> None; display_holiday(1) is False; swap_canvas not called

def test_missing_facts_returns_false(monkeypatch):
    # load_holiday_facts -> {}; today forced to christmas; display_holiday(1) is False

def test_deck_follows_the_holiday(monkeypatch):
    # show new_years_eve, then new_years_day: the fact handed to draw_band
    # comes from the new_years_day deck

def test_band_draws_fact_at_baseline_45():
    # draw_band(...) calls draw_text('medium_bold', scroll_x, 45, <color>, fact)
```

- [ ] **Step 2: Run** — expect failures.
- [ ] **Step 3: Implement.** Card: card PNG, effect over 48 rows, `card_text`. Band: band PNG at (0, 0), effect over 30 rows, `band_text`, fact in `medium_bold` at baseline 45. `display_holiday` shows the card for `HOLIDAY_CARD_SECONDS`, then scrolls facts 1 px per frame for the rest of `duration`, sleeping `get_scroll_delay(config.get('scroll_speed_holiday_facts', 5))`. The deck is shuffled when the holiday being shown changes and wraps without re-shuffling. PNGs are loaded on first use and cached. Snow uses the weather screen's look (white pixel, soft neighbours). A missing PNG or empty deck prints one line and returns `False`.
- [ ] **Step 4: Write `tools/render_holiday_previews.py`** on the pattern of `tools/render_ncaab_previews.py`: for each holiday save `<slug>_card` and `<slug>_band` (with that holiday's first fact part-way across) at 1x and 8x into `holiday_previews/`, plus `contact_sheet.png` of all 36. Add `holiday_previews/` to `.gitignore`.
- [ ] **Step 5: Run** the tests, then `python3 tools/render_holiday_previews.py`. Read the contact sheet and tune each holiday's `card_text` / `band_text` until no text runs off the panel or over the art's subject.
- [ ] **Step 6: Commit** `Add the holiday facts display and preview renderer`.

### Task 5: Rotation and pre-game loop

**Files:**
- Modify: `off_season_handler.py` (import and construct `HolidayDisplay`; `rotation_schedule['holiday_facts']`; default config; slot after the celebration slot near line 1002), `game_state_handler.py` (`display_no_game`, non-cycling path near line 403)
- Test: `tests/test_holiday_display.py`; update the segment and toggle lists in `tests/test_bugfixes.py` (`_make_handler`, `_all_off`)

**Interfaces:**
- Consumes: `HolidayDisplay.display_holiday`
- Produces: `OffSeasonHandler.display_holiday_facts() -> bool` — `False` when `enable_holiday_facts` is off or nothing showed; never raises (logs and returns `False`).

- [ ] **Step 1: Write the failing tests**

```python
def test_rotation_slot_runs_when_enabled():      # holiday_display.display_holiday called once with 0*60
def test_rotation_slot_skipped_when_toggle_off():  # not called
def test_tick_only_fires_when_the_holiday_showed():
    # display_holiday -> False: between_callback not called for that slot
def test_display_holiday_facts_swallows_errors():  # display_holiday raises -> returns False
def test_pre_game_loop_shows_holiday_on_non_cycling_path():
    # display_no_game, game_type 'R', cycle_content False, one trip:
    # off_season_handler.display_holiday_facts called once
def test_pre_game_loop_skips_holiday_when_cycling_or_spring():
    # cycle_content True -> not called; game_type 'S' -> not called
```

- [ ] **Step 2: Run** — expect failures.
- [ ] **Step 3: Implement.** The rotation slot copies the celebration slot's shape. In `display_no_game`, call `other.display_holiday_facts()` after the standings / playoff screens and before the status check, guarded by the same `getattr(self, 'off_season_handler', None)` the loop already uses.
- [ ] **Step 4: Run** `pytest tests -q` — expect all pass.
- [ ] **Step 5: Commit** `Show holiday facts in the rotation and before games`.

### Task 6: Admin

**Files:**
- Modify: `wifi_config_server.py` — `APPLIES_LIVE_KEYS`, `DEFAULT_CONFIG`, the "Faith & fun" toggles, the speed sliders, the load script (toggle line and `speedFields`), the save script (toggle and slider)
- Test: `tests/test_admin_config.py`

**Interfaces:**
- Produces: config keys `enable_holiday_facts`, `scroll_speed_holiday_facts`.

- [ ] **Step 1: Write the failing tests**

```python
def test_admin_page_has_holiday_facts_controls(client):
    html = client.get('/admin').data.decode()
    assert 'id="enable_holiday_facts"' in html
    assert 'Holiday fun facts' in html
    assert 'id="scroll_speed_holiday_facts"' in html

def test_holiday_facts_defaults(client):
    cfg = wcs.load_config()
    assert cfg['enable_holiday_facts'] is True
    assert cfg['scroll_speed_holiday_facts'] == 5

def test_holiday_facts_round_trip(client, tmp_path):
    client.post('/save_config', json={'enable_holiday_facts': False,
                                       'scroll_speed_holiday_facts': 8})
    saved = json.loads((tmp_path / 'config.json').read_text())
    assert saved['enable_holiday_facts'] is False
    assert saved['scroll_speed_holiday_facts'] == 8
```

- [ ] **Step 2: Run** — expect failures.
- [ ] **Step 3: Implement.** Toggle label **Holiday fun facts**, description "On holidays like Christmas, Easter and Thanksgiving, shows a themed picture and fun facts about the day. Only appears on the holiday itself." Slider label "Holiday fun facts". Place both after their Bible-facts neighbours.
- [ ] **Step 4: Run** `pytest tests -q` — expect all pass (`tests/test_reboot_prompt.py` confirms both keys are classified).
- [ ] **Step 5: Commit** `Add the holiday facts toggle and speed slider to the admin`.

### Task 7: Docs and final check

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1:** Add `holiday_display.py`, `holiday_facts.json`, `holidays/`, `dev/draw_holiday_art.py` and `tools/render_holiday_previews.py` to the tables; document the three config keys, the one-per-day rule, the pre-game loop pass and the preview command.
- [ ] **Step 2:** Run `pytest tests -q` (expect 703 existing plus the new tests, all passing) and `python3 -m py_compile` over the changed modules.
- [ ] **Step 3:** Re-render the previews and send Ryan the contact sheet.
- [ ] **Step 4: Commit** `Document the holiday facts screen`.

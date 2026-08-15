# NFL Preseason + MLB/NFL Precedence Design

**Date:** 2026-08-15
**Status:** Approved by user (approach A, all sections)

## Goal

Make the NFL package show preseason games the same way it shows regular
season games, and give the user control over which sport owns the screen
when both have something on. Today the NFL package is strictly subordinate
to MLB: it exists only as a timed slot inside the off-season rotation, and
a month gate hides it entirely during August.

## Problem

Three separate things block the desired behavior:

1. **`_is_football_season()` excludes August.** The gate at
   `off_season_handler.py:415` is `month >= 9 or month <= 2`, so the whole
   NFL package is skipped during preseason. ESPN needs no change — the
   schedule endpoint already returns preseason events with
   `seasonType: 1` (verified 2026-08-15: `CLE @ CHI`, today).
2. **NFL can never take the screen.** `display_bears_info(duration=180)`
   is duration-bounded; only MLB's `display_game_on()` loops until final.
3. **There is no precedence control.** Nothing in config expresses "I want
   football to win."

## Decisions made during brainstorming

- **NFL stays out of the live MLB loop.** `display_game_on()` is a
  `while True` that owns the screen for the whole game; it is not modified.
  The NFL scheduled card appears only in rotation contexts.
- **Preempt is a true role reversal.** With `nfl_preempt_mlb` on and an NFL
  game live, NFL takes over and loops until final, mirroring MLB's live
  behavior; MLB drops to its scheduled card.
- **Season is schedule-driven, not month-driven.** The month gate is
  replaced by a window query against the ESPN schedule.
- **Demotion condition is narrow, by explicit user choice.** The NFL slot
  falls back to the scheduled card only while MLB is *in progress* — not
  merely scheduled that day.
- **Structure: approach A (named predicates, used inline).** Rejected a
  central `resolve_owner()` resolver (would require restructuring
  `route_by_status` and destabilizing working MLB paths) and a generalized
  package priority list (speculative generality for a two-package choice).

### Known scope limitation (accepted)

The rotation only runs from four call sites: `main.py:403` (off-season
hybrid, non-live statuses only), `main.py:423` (spring training),
`live_game_handler.py:933` (post-game), and `off_season_handler.py:468`
(pure off-season / `no_games`). Three of the four run only when MLB is
*not* in progress. Combined with the narrow demotion condition above,
**section 3 is reachable only in `display_mode: no_games`.** This was
raised during brainstorming and the user chose to keep it.

## 1. Season detection (`bears_display.py`, `off_season_handler.py`)

```python
def has_game_within(self, days_back: int = 3, days_ahead: int = 14) -> bool:
    """True when the schedule holds a game in the recent past or near future."""
```

Reads the already-cached `self.bears_data` (fetching if stale via the
existing `_should_update_schedule()`), and compares each `events[].date`
against the window in `America/Chicago`.

`OffSeasonHandler._is_football_season()` becomes a delegation to it.

**Failure mode:** if the schedule is unavailable, fall back to an extended
month gate (`month >= 8 or month <= 2`) rather than returning `False`. A
network blip must degrade to "August counts", never to silently hiding all
NFL content.

The window intentionally goes quiet March–July. It opens roughly two weeks
before the preseason opener, which is the desired behavior — ESPN publishes
next season's schedule months early, and a bare `len(events) > 0` check
would put NFL content on the board in spring.

## 2. NFL live takeover (`bears_display.py`, `main.py`)

New config key `nfl_preempt_mlb`, default `false`. Existing boards are
unchanged.

```python
def live_game(self) -> dict | None:
    """Today's game when ESPN reports status.type.state == 'in', else None."""
```

ESPN exposes `pre` / `in` / `post`, so live detection is a single field and
needs no time arithmetic.

`_display_game_day()` gains `loop_until_final: bool = False`. When set, it
keeps refreshing on the existing `live_update_interval` until the state
leaves `'in'` or shutdown is requested, instead of returning at `duration`
(which is then ignored). This reuses the current drawing code rather than
duplicating it.

`display_bears_info()` is the public entry point and forwards both new
keyword arguments — `loop_until_final` (section 2) and `force_scheduled`
(section 3) — to the right branch. Its signature becomes:

```python
def display_bears_info(self, duration=180, loop_until_final=False,
                       force_scheduled=False):
```

`main.py` `run()` gains one guard, placed **after** the `no_games` check and
**before** `is_off_season()`, so preempt applies on both the in-season and
off-season paths while `no_games` still wins:

```python
if self._nfl_preempts():          # config on AND bears_display.live_game()
    self.off_season_handler.bears_display.display_bears_info(
        loop_until_final=True)
    continue
```

Shutdown handling follows the existing pattern: the loop checks
`is_shutdown_requested()` between refreshes.

## 3. Default demotion (`off_season_handler.py`)

At the NFL rotation slot (`off_season_handler.py:566`):

```python
force_scheduled = not nfl_preempt and self._mlb_in_progress()
self.bears_display.display_bears_info(
    duration=self.rotation_schedule['bears'] * 60,
    force_scheduled=force_scheduled)
```

`display_bears_info(force_scheduled=True)` renders today's game through
`_display_next_game(todays_game, duration)` — the scheduled card — instead
of `_display_game_day()`.

`_mlb_in_progress()` must do its own lookup. `manager.current_status` is set
only by `route_by_status()`, which never runs in `no_games` mode, so that
field is stale exactly where this check matters. It calls
`manager.get_schedule()` behind a ~120s TTL cache (the today path is
uncached upstream, and the rotation loops continuously in `no_games`), and
returns `False` on any error so a schedule outage cannot suppress NFL
content.

## 4. Admin panel (`wifi_config_server.py`)

`nfl_preempt_mlb` checkbox beside the existing Bears toggles, wired through
the five places every other key touches: defaults dict (~line 146), HTML
(~763), JS load (~1239), JS save (~1505), POST handler (~2201).

Label: "NFL preempts MLB", help text explaining that football games take
over the display when both sports are on.

## 5. Testing

New `tests/test_nfl_preempt.py` (no NFL display test file exists today —
only `test_teams.py` covers the packs), with ESPN and statsapi payloads
faked the way `test_weather_openmeteo.py` fakes its sources:

- `has_game_within`: game today / 10 days out / 30 days out / empty
- month-gate fallback when the schedule fetch raises
- `live_game()` across `pre` / `in` / `post`
- `force_scheduled=True` routes to the scheduled card, not live scores
- `_mlb_in_progress()` returns `False` on schedule error
- the `main.py` preempt guard both ways (config on + NFL live → takeover;
  config off → normal MLB routing)
- `no_games` still wins over preempt

Plus admin round-trip of `nfl_preempt_mlb` in `test_admin_config.py`.

## Out of scope

- Modifying `display_game_on()` or any live MLB path
- NFL news slot behavior (unchanged)
- A split-screen or ticker treatment for simultaneous games
- Any package beyond MLB and NFL

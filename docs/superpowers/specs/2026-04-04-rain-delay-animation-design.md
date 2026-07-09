# Rain Delay Animation & Status Handling

## Problem

Currently `game_state_handler.display_delayed` and `display_postponed` show a plain solid-color screen with static "DELAYED"/"POSTPONED" text. It's flat and doesn't convey what's actually happening.

Separately, `live_game_handler.display_game_on` only exits its loop on `Game Over`/`Final`. If an in-progress game transitions to `Delayed: Rain`, `Suspended`, `Postponed`, or `Cancelled` mid-play, the live scoreboard keeps rendering stale data with no indication of the delay.

## Solution

### Part 1 — Animated rain delay screen

Add `_display_delay_animated` to `GameStateHandler`. It replaces the solid bg_color pregame screen for delays/postponements/suspensions/cancellations with:

- Dark stormy-blue gradient background (top `(5, 15, 40)` → bottom `(10, 25, 60)`)
- ~12 animated rain drops (2-pixel streaks, light-blue) — pattern ported from `weather_display.py:812`
- Centered status label ("RAIN DELAY" / "POSTPONED" / "SUSPENDED" / "CANCELLED")
- "START TIME" + time line (preserved)
- Scrolling lineup at bottom (preserved)

Rain drop state lives on `GameStateHandler` as instance attributes (initialized lazily).

`display_delayed` and `display_postponed` become thin wrappers that call `_display_delay_animated` with a label. New methods `display_suspended` and `display_cancelled` do the same. `display_warmup` keeps using existing `_display_pregame_base` (solid green) — no change.

### Part 2 — Mid-game status change detection

In `live_game_handler.display_game_on`, after fetching schedule at the top of each loop iteration, add checks:

- `status.startswith('Delayed')` → `return`
- `status.startswith('Suspend')` → `return`
- `status.startswith('Postpon')` → `return`
- `status == 'Cancelled'` → `return`
- `status.startswith('Completed Early')` → treat as Final

Returning lets `route_by_status` in `main.py` pick the right handler on the next cycle.

### Part 3 — Routing update

Add to `main.py` `route_by_status`:
- `status.startswith('Suspend')` → `display_suspended` (retries on next cycle like delayed)
- `status == 'Cancelled'` → `display_cancelled` (displays once, falls through)

## Out of scope

- Config toggles
- Per-status differentiated animations
- Changes to warmup display
- New tests

## Files Modified

- `game_state_handler.py` — new animated method, 4 public delay/pause handlers
- `live_game_handler.py` — status check additions in main loop
- `main.py` — 2 new routing cases

# Scrolling Full Last-Play Description — Design

**Date:** 2026-07-10
**Status:** Approved

## Problem

The live game screen's "last play" line shows a compact abbreviation
(`LAST: K HOERNER +1`) that alternates with the batter name every 8
seconds on the bottom strip. The abbreviations (K, GDP, FC, ...) are
hard to interpret at a glance. Replace them with the full play
description from the MLB feed, scrolled horizontally across the
bottom strip.

## Decisions (user-approved)

- **Direction:** horizontal ticker, right-to-left, matching the
  existing flight/Bible tickers.
- **Rotation (revised after on-marquee review):** each completed
  play scrolls its description across exactly once, right after the
  play; the static batter line shows the rest of the time, until the
  next play. (The original ~8s alternation re-scrolled the same play
  repeatedly and was rejected on hardware.)
- **Clean strip:** the batter line is erased from the frame snapshot
  (batter strip gradient repainted) before scrolling, so the
  description never overlaps the at-bat text.

## Data

Use `play['result']['description']` from the MLB live feed — the full
sentence, e.g. "Nico Hoerner singles on a line drive to left fielder
Ian Happ. Dansby Swanson scores." — with no prefix or title (a
`LAST: ` prefix was tried and removed after on-marquee review).

- New method `_get_last_play_description()` in `LiveGameHandler`
  returns the description of the most recent *completed* play (skip
  plays with no `result.event`, same as today), or `None` on
  missing/malformed data.
- The old `_get_last_play_text()` method and the
  `PLAY_EVENT_ABBREVIATIONS` dict are removed — nothing else uses
  them.

## Rendering

The live game loop redraws the whole frame every ~5s
(`GAME_CHECK_DELAY`), and `swap_canvas()` swaps double buffers, so a
smooth scroll needs a per-frame animation sub-loop that repaints the
full frame each step.

**Approach: snapshot + blit.** `ScoreboardManager` already mirrors
every draw into a full-frame PIL image (`_frame`) for the web
preview. Add a small public method:

```python
def get_frame_copy(self) -> Image.Image:
    """Copy of the current composed frame (for animation overlays)"""
    return self._frame.copy()
```

The scroll pass in `LiveGameHandler`:

1. After the static frame is fully drawn (batter line included) and
   swapped, take `snapshot = manager.get_frame_copy()`.
2. Loop from `scroll_x = 96` until the text has fully exited left
   (`scroll_x + text_width < 0`, text width = `len(text) *
   Fonts.CHAR_WIDTH_MICRO`):
   - `set_image(snapshot)` (restores everything, including the
     batter strip background)
   - `draw_text('micro', scroll_x, 45, Colors.CUBS_BLUE, text)`
   - `swap_canvas()`
   - sleep the scroll delay; `scroll_x -= 1`
3. One pass only, then return to the normal loop.

Rejected alternative: re-running the base composite + gradient pixel
loops (~1,500 `draw_pixel` calls) per scroll frame, as the
Bible/flight tickers do with their lighter frames — too heavy for
smooth scrolling on the Pi and a larger refactor.

Note: the scrolling text overdraws the batter line region of the
snapshot as it passes; the strip background in the snapshot is the
gradient, so each frame starts clean.

## Rotation / loop integration

- `_draw_game_info_improved()` always draws the static batter line;
  the `int(time.time() / 8) % 2` alternation is removed.
- `LiveGameHandler` tracks `self._last_scrolled_description`
  (init None). In the main `display_game_on` loop, after
  `swap_canvas()`, `_maybe_scroll_last_play(play_data,
  banner_active)` runs one scroll pass only when the current
  description differs from the last one scrolled, then records it.
  While a review/challenge banner occupies the strip, the scroll is
  deferred until the banner clears.

## Scroll speed

Use the shared `get_scroll_delay()` helper with the default speed 5,
same as the other tickers. No new config key.

## Safety / edge cases

- The scroll sub-loop checks `is_shutdown_requested()` every frame
  and returns immediately if set.
- If `split_squad_indicator` is active and `split_squad_switch_time`
  passes mid-scroll, the pass aborts so the game switch isn't
  delayed.
- Missing/absent description (API gap, no completed plays yet):
  `_get_last_play_description()` returns `None` and the row simply
  keeps showing the batter name.
- Game data is not refreshed during a pass (~8–15s); this matches
  the existing between-innings flight interlude behavior.

## Testing

- Unit tests for `_get_last_play_description()`:
  - Normal completed play → `LAST: <description>`.
  - In-progress at-bat (no `result.event`) skipped in favor of the
    previous completed play.
  - Empty `allPlays` / missing keys → `None`.
- Scroll animation verified manually on the Pi (project standard for
  display work).

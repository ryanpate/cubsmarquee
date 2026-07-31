# Anti-Aliased Text on Flight Screens

**Date:** 2026-07-31
**Status:** Approved

## Problem

Text on the FlightWall flight screens looks pixelated on the 96x48 LED wall.
The screens draw everything with hard-edged BDF bitmap fonts (`small` = 6x9,
`micro` = 4x6), and the fallback airline monogram badge uses PIL's crunchy
`ImageFont.load_default()`. On an LED matrix the only real way to soften
staircase edges is anti-aliasing: render text from a vector font at high
resolution, downsample, and use partial LED brightness on edge pixels so the
eye blends them into smooth curves at viewing distance.

## Decision

Anti-alias the text that is tall enough to benefit — the `'small'` (9px) rows
and the monogram badge — and keep the dense `micro`/`tiny` data rows as crisp
bitmap fonts, where anti-aliasing at 6px height would smear into mush.

## Design

### 1. AA rendering path in `ScoreboardManager`

- At init, load a TrueType font. Try DejaVu Sans **Bold** first
  (`/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf`, preinstalled on
  Raspberry Pi OS). Bold is deliberate: at ~9px cap height, regular-weight
  anti-aliased strokes render dim on LEDs; bold keeps them bright.
- If no TTF is found (e.g., a dev machine), `draw_text_aa` falls back to the
  existing bitmap `draw_text` and logs the fallback once.
- `draw_text_aa(x, baseline, color_tuple, text, size)`:
  1. Render the string with PIL at 4x scale into a grayscale (`L`) image.
  2. Downsample with LANCZOS to target size.
  3. Write pixels to the canvas with the color scaled by the anti-aliasing
     alpha (edge pixels become dimmer LEDs); skip near-zero pixels.
  4. Mirror the same pixels into the admin-preview frame so the preview
     matches the wall.
- `measure_text_aa(text, size) -> int` returns rendered pixel width so
  callers can center / right-align / truncate.
- Cache rendered (downsampled grayscale bitmap, width) per `(text, size)`.
  Flight screens redraw identical strings every 0.25s frame; each string
  should be rasterized once.

### 2. Flight display uses AA for its `'small'` text

Call sites in `flight_display.py` that switch from `draw_text('small', ...)`
to `draw_text_aa(...)`:

1. Detail card airline / route / aircraft-type lines (currently x=26,
   baselines 9/18/27).
2. Detail card page B: `Flying to` + city, and `Registration` + tail number.
3. `_display_no_flights`: the centered "No flights" / "overhead" lines
   (centering uses `measure_text_aa`).
4. `_display_summary_view`: the "N aircraft" headline.

Because the TTF is proportional, character-count truncation (`text[:11]`)
becomes width-based truncation: trim trailing characters until
`measure_text_aa` fits the available width (70px for the detail card lines).

The `micro` and `tiny` rows (metrics, radar labels, counters, scroll
messages) stay bitmap. AA font size lives as a constant in
`flight_display.py` so it can be tuned during on-hardware iteration.

### 3. Monogram badge rendered at 4x

`_monogram_badge` builds the whole badge at 80x80 — rounded rectangle plus
the two-letter code drawn with the TTF — then downsamples LANCZOS to 20x20.
Smooth letters and smoother corners; `ImageFont.load_default()` goes away.
If the TTF is unavailable, keep the current `load_default()` rendering as
the fallback.

## Out of Scope

- Other displays (game, weather, Bears, PGA) keep their bitmap fonts.
- No changes to `micro`/`tiny` rendering.
- No new BDF fonts.

## Error Handling

- Missing TTF → bitmap fallback, logged once, everything still renders.
- `draw_text_aa` clips pixels outside the 96x48 canvas bounds.

## Testing

- Unit tests (rgbmatrix is already mocked off-Pi): AA renderer produces
  expected width/height and caches; bitmap fallback path when no TTF;
  width-based truncation helper trims to fit.
- Visual verification on the Pi after deploy (user sign-off), including the
  admin preview mirror.

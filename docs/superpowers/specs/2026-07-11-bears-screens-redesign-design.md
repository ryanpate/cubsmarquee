# Bears Screens Redesign

**Date:** 2026-07-11
**Files:** `bears_display.py`, `off_season_handler.py` (Bears news screen only), `tests/test_core_logic.py`

## Problem

The Bears screens are the least developed displays on the marquee. The "sweater
header" occupies 25 of 48 rows, leaving a small strip for content. The live game
screen shows only the two scores and the clock, even though the ESPN scoreboard
endpoint we already poll provides possession, down & distance, red zone status,
and last-play text. The next-game screen is a single scrolling line. Other
screens (PGA, weather) use compact headers, structured layouts, countdowns, and
animation.

## Shared Compact Sweater Header (y0–11)

Replaces the 25-row sweater header on every Bears screen, keeping the sweater
identity in the style of the PGA 12-row header:

- y0–1: orange stripe (`Colors.BEARS_ORANGE`)
- y2–9: navy band (`Colors.BEARS_NAVY`) with `CHICAGO BEARS` in `tiny_bold`
  white, centered (13 chars × 5 px = 65 px; x = 15, baseline y = 9)
- y10–11: orange stripe

Rendered from a cached background image (same pattern as today's
`_create_bears_sweater_background`). The duplicate header code in
`off_season_handler.py` (`_create_bears_sweater_background`,
`_draw_sweater_header`) is updated to the same compact layout so the Bears news
screen matches; its scrolling headline moves to the vertical center of the
content area (baseline ~y32).

Content area for all Bears screens: y12–47 (36 rows).

## Live Game Screen

Layout (top to bottom):

1. **Score row** (`small_bold`, baseline ~y24, so the 13 px glyphs start at
   y12, just below the header): `CHI 24` left-aligned at x=8,
   opponent `GB 17` right side at x=52 (as today). A 3×3 orange possession dot
   renders beside the abbreviation of the team with the ball (left of `CHI`,
   right of the opponent score) when `situation.possession` matches that team's
   id.
2. **Situation line** (`tiny`, centered, baseline ~y31): built from
   `situation.shortDownDistanceText` and `situation.possessionText`
   (e.g. `2ND & 8 CHI 34`). If `situation.isRedZone` is true, the line renders
   red (255, 60, 60) and blinks (on 0.5 s / off 0.5 s, driven by the existing
   0.5 s frame loop). If the fields are absent (between plays, halftime), the
   line is omitted.
3. **Clock line** (`micro`, centered, baseline ~y38, orange): the existing
   `shortDetail` text (e.g. `8:42 - 3rd`).
4. **Last-play strip** (y~40–47): each new `situation.lastPlay.text` scrolls
   across once over a clean navy strip, mirroring the Cubs last-play behavior
   (track last seen play id/text; when it changes, scroll the new text once at
   the configured Bears scroll speed; strip is blank when idle).

**Scoring celebration:** the 60 s live poll already compares scores. When the
Bears score increases, show a ~4 s celebration before returning to the live
layout: message chosen by delta (6–8 → `TOUCHDOWN!`, 3 → `FIELD GOAL!`,
2 → `SAFETY!`, else `BEARS SCORE!`) flashing alternating orange and white,
centered in the content area, on the navy background with the compact header
still visible. Opponent scoring gets no celebration.

## Pregame Screen (game today, not started)

1. `TODAY` + `vs`/`at` + opponent name (`tiny`, orange), centered. Opponent
   uses ESPN `shortDisplayName` (nickname; always fits 96 px), falling back
   to `displayName`.
2. Kickoff time in Central (`h:mm A`), as today.
3. **Countdown line**: `KICKOFF IN 3H 22M` (`micro`), recomputed each frame
   from the parsed game date. Under 1 hour: `KICKOFF IN 22M`. Color shifts as
   kickoff nears (white → yellow under 3 h → orange under 1 h), like the PGA
   countdown.
4. **Week + TV line** (`micro`, gray-white): `WK 15 · FOX`, from the event's
   `week` and broadcast fields. Either part is omitted if missing.

## Final Screen

Scores as today. Result logic unchanged (compare int scores).

- **Loss:** red `LOSS` label, as today.
- **Win:** `BEARS WIN!` (`tiny_bold`, centered in the strip below the scores)
  alternating orange/white each second for the remainder of the display slot,
  replacing the small static green `WIN`.

## Next-Game Card (no game today)

Replaces the scrolling one-liner with a fixed card in the PGA "UP NEXT" style:

1. `UP NEXT` label (`ultra_micro`, gray, centered, ~y17)
2. Opponent (`tiny_bold`, white, centered), with `vs`/`at` prefix (e.g.
   `AT PACKERS`), ~y25. Opponent uses ESPN `shortDisplayName` (nickname;
   always fits 96 px), falling back to `displayName`.
3. Date + time (`tiny`, white, centered): `SUN DEC 14 · NOON` (12:00 PM renders
   as `NOON`; otherwise `h:mm A`), ~y33
4. `WK 15 · FOX` (`micro`, gray-white, centered), ~y40
5. Countdown (`micro`, centered, ~y47): `IN 2D 14H`; under 1 day `IN 14H 22M`.
   Same color shift as the pregame countdown (white → yellow < 24 h → orange
   < 3 h).

## Data Extraction

`_get_current_scores` additionally returns (all optional, `None` when absent):

- `possession`: resolved inside `extract_situation` to `'bears'` / `'opponent'`
  / `None` by matching `situation.possession` against `competitors[].team.id`;
  no team-id keys are returned
- `down_distance`: `shortDownDistanceText` + `' '` + `possessionText`
- `is_red_zone`: bool from `situation.isRedZone`
- `last_play`: `situation.lastPlay.text`

Week comes from `event['week']['number']` (both schedule and scoreboard forms).
Broadcast comes from `competitions[0].broadcasts`: scoreboard form
`broadcasts[0].names[0]`, schedule form `broadcasts[0].media.shortName`; a
helper tries both. All new fields degrade to omission — no screen errors when
ESPN omits them.

## Error Handling

Unchanged philosophy: every fetch/parse wrapped as today; missing new fields
never raise (use `.get` chains); screens render without the optional lines.

## Testing

Extend `tests/test_core_logic.py` (pure-logic tests, no matrix):

- Situation extraction: possession resolution to CHI/opponent, down & distance
  string assembly, red zone flag, last-play text, and all-absent case.
- Broadcast/week extraction from both scoreboard and schedule shapes.
- Countdown formatting: days+hours, hours+minutes, minutes-only boundaries.
- Celebration message selection by score delta (3, 6, 7, 8, 2, other).

Visual verification on the Pi (deploy to `/home/pi/`, `sudo reboot`).

## Out of Scope

- NFL team logos (no new assets)
- Team records display (declined)
- NFC North standings
- Changes to Bears news fetching/rotation logic (header/layout only)

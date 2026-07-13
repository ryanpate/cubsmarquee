# All-Star Break Screens

**Date:** 2026-07-13
**Status:** Approved

## Goal

Show All-Star break content on the 96x48 marquee: a Home Run Derby promo
screen (Derby night), an All-Star Game pregame countdown, a live AL vs NL
score screen during the game, and a brief final screen. The Cubs angle
leads: Cubs all-stars are named on the pregame screen and celebrated when
they bat. Generic across seasons — no hardcoded player names except the
Derby field (no public API exists for the Derby).

## Data sources (verified 2026-07-13)

- **ASG discovery:** `GET statsapi.mlb.com/api/v1/schedule?sportId=1&gameTypes=A&startDate=<jul1>&endDate=<jul31>`
  returns the All-Star Game (2026: gamePk 823443, 2026-07-15T00:00Z,
  Citizens Bank Park). Cached ~1 hour.
- **Live data:** `GET statsapi.mlb.com/api/v1.1/game/{gamePk}/feed/live` —
  standard game feed: linescore (runs, inning, half, outs), offense
  (bases, batter), boxscore players with `parentTeamId`. Cubs all-stars =
  players where `parentTeamId == TeamConfig` Cubs id (112). Polled ~30 s
  while live.
- **Derby:** not in the public Stats API (schedule omits it; the
  `homeRunDerby/{gamePk}` pk is not discoverable). Derby screen is
  data-free: one module-level constant `DERBY_INFO` holding local
  date, start time (CT), venue, and the 8-player field with team
  abbreviations. Updated by hand each July.

## Architecture

New module `allstar_display.py` with class `AllStarDisplay(DisplayHandler)`,
following the handler pattern (`bears_display.py`, `spring_training_display.py`).
`LiveGameHandler` is NOT modified — it is Cubs-specific (W flag, logo
images, next-game routing) and changing it mid-season risks regressions.
The live ASG screen is self-contained but visually matches the live-game
layout.

### AllStarDisplay public surface

- `fetch_asg_info() -> dict | None` — cached schedule lookup:
  `{game_pk, game_date (pendulum), venue, status}`. None outside July or
  on API failure.
- `is_allstar_window() -> bool` — today (America/Chicago) is ASG day or
  the day before (Derby day).
- `asg_is_live() -> bool` — status is in-progress.
- `display_promo(duration)` — rotation segment: Derby promo on Derby day
  (until ~11 PM CT), otherwise ASG pregame countdown.
- `display_live_game(display_time)` — one timed pass of the live screen
  (caller loops while live).
- `display_final(duration)` — final score screen.

### Screens

1. **Derby promo** (Derby day only): gold "HOME RUN DERBY" header on a
   dark field, countdown to start (reuse the Bears pregame countdown
   pattern: `Xh Ym` / `STARTING SOON`), venue line, scrolling 8-player
   field ("SCHWARBER PHI * HARPER PHI * ...").
2. **ASG pregame** (Derby day and ASG day until first pitch): star header
   "ALL-STAR GAME", "AL VS NL", kickoff-style countdown, venue, and a
   "CUBS ALL-STARS:" line listing feed-roster players with
   `parentTeamId == 112` (scrolls if long, omitted if lookup fails).
3. **ASG live**: existing live-game layout with the 16 px logo column
   replaced by drawn 16x15 "AL" (red `(191,13,62)`-family) and "NL"
   (blue) letter tiles with a small star; right panel shows score,
   TOP/BOT + inning, outs dots, base diamond, batter line. When the
   current batter's `parentTeamId` is 112, flash a Cubs-blue/yellow
   "CUBS STAR AT BAT: <NAME>" banner for ~3 s (generic for all seasons).
4. **ASG final**: "FINAL" + "AL x - NL y" (winner's row brighter), shown
   briefly, then normal content resumes. No MVP line (not reliably in
   the feed).

## Integration

- **Rotation segment:** `off_season_handler._display_rotation_cycle()`
  gains an `allstar` segment (pattern: `spring_training`), gated by
  `is_allstar_window()` and config toggle `enable_allstar`
  (default true, read from `/home/pi/config.json` like other toggles).
  Duration ~2 min via `rotation_schedule['allstar']`.
- **Live takeover:** at the top of `main.process_game_cycle()`, before
  Cubs schedule routing: if `asg_is_live()`, loop the live screen until
  the feed reports Final (checking `is_shutdown_requested()`), show the
  final screen once, then return. Mirrors how a Cubs game takes over.
- **Config:** `GameConfig` gains cache/poll intervals and the rotation
  duration; colors go in `Colors` (AL red, NL blue reuse/extend existing
  tuples).

## Error handling

- Schedule/feed failures: log, return None/False; the marquee falls
  through to normal content. Never crash the cycle.
- Missing feed fields (no batter between innings, empty rosters):
  render without that line.
- Derby constant stale (future year, nobody updated it): Derby screen is
  skipped unless `DERBY_INFO['date']` matches ASG date − 1 day from the
  live schedule lookup — a wrong-year constant silently disables the
  Derby screen rather than showing 2026 players in 2027.

## Testing

pytest with mocked manager (existing pattern in `tests/test_features.py`):

- ASG schedule parse from fixture (pk/date/venue/status).
- `is_allstar_window()` on Derby day, ASG day, day after, random day.
- Cubs all-star detection from a boxscore fixture via `parentTeamId`.
- Countdown text formatting at several offsets.
- Derby screen gating: field shown only when constant date == ASG − 1.
- Live-screen routing: `asg_is_live()` true/false paths in
  `process_game_cycle` (mocked).

Visual verification on the Pi (deploy + reboot per usual workflow).

## Addendum (2026-07-13): Live Derby tracker

The "no Derby API" finding was wrong in a useful way. `GET
statsapi.mlb.com/api/v1/homeRunDerby/{pk}` works when `pk` is the Derby's
*event id*, discoverable via `schedule?gameTypes=D` (games) and
`schedule?scheduleTypes=events` (July events named "Home Run Derby").
MLB publishes the bracket around event time — the endpoint 404s before
that. The API also serves rehearsal events ("Home Run Derby Test #N")
with junk data; payloads are validated (not named test, eventDate ==
ASG − 1) before use.

`AllStarDisplay` additions:
- `_derby_event_candidates()` — candidate pks from both discovery paths,
  excluding batting-practice and test events.
- `fetch_derby_data()` — polls candidates (15 s data cache, 2 min
  discovery backoff), locks onto the first validated pk, returns None
  while unpublished.
- `_parse_derby()` — flattens `rounds[].matchups[]`
  (`numHomeRuns`/`isStarted`/`isComplete`/`isWinner` per seed, `status`
  clock/round) into: active matchup, current batter, completed-results
  strings, champion.
- `_display_derby_live(duration)` — header + round tag, current matchup
  rows (blinking `>` on the active hitter, gold HR count), round clock,
  scrolling results ticker, CHAMPION screen when Final.

Routing: on Derby evening `display_promo` shows the live tracker when
data is published (segment extended to ≥5 min), otherwise the promo.
Falls back to the promo automatically if MLB never publishes.

## Out of scope

- MVP display, play-by-play scroll on the ASG screen.
- Admin-panel UI for the toggle (config key only, UI can come later).
- Derby takeover mode (it stays a rotation segment; the ASG still takes
  over fully when live).

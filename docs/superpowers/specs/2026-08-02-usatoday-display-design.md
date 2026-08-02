# USA Today News Display — Design

**Date:** 2026-08-02
**Status:** Approved (Approach A — mirror module)

## Goal

Add a rotation screen that scrolls USA Today headlines and breaking news,
following the existing Newsmax display pattern.

## Decisions

- **Content:** USA Today Top Stories RSS only —
  `http://rssfeeds.usatoday.com/usatoday-NewsTopStories`. The feed mixes
  breaking national news with top headlines; no section feeds.
- **Look:** USA Today branding — white background, blue-circle logo with
  "USA TODAY" wordmark at top, blue separator rule, scrolling `large_bold`
  headlines in USA Today navy below. Same geometry as the Newsmax screen.
- **Structure:** Approach A — standalone `usatoday_display.py` mirroring
  `newsmax_display.py`. No shared-class refactor; extract only if a third
  branded news source appears (rule of three).

## Components

### `usatoday_display.py` (new)

`UsaTodayDisplay` class mirroring `NewsmaxDisplay`:

- Colors: white background; brand blue `(0, 155, 255)` for the circle/rule;
  navy `(20, 40, 80)` for scrolling text (readable on white LEDs; tune on
  hardware).
- `_fetch_usatoday_rss()` — via `rss_fetch.fetch_feed` (10s timeout), top 15
  entries, title + first-sentence summary composition when the summary adds
  information, HTML cleaned, `"USA TODAY: "` prefix, uppercase, prefix-dedupe,
  max 12 items.
- 30-minute cache via `GameConfig.NEWS_UPDATE_INTERVAL`.
- Fallback when feed is empty/down: `"USA TODAY: CHECK BACK FOR THE LATEST
  NEWS UPDATES!"`.
- `display_usatoday_news(duration)` — same scroll loop as Newsmax
  (`large_bold`, baseline 44, 10px advance, per-headline reset, refresh after
  a full cycle, scroll speed from config each frame).

### `usatoday.png` (new asset)

Generated logo: brand-blue filled circle + "USA TODAY" in DejaVu Bold,
supersampled then LANCZOS-downscaled to roughly 72x14 px (must fit the
96px-wide header band with the separator rule below, mirroring the Newsmax
header layout: logo centered, top at y=4). Generator script committed under `tools/`. Load paths mirror
Newsmax (`./usatoday.png`, `/home/pi/usatoday.png`, `logos/` variants) with
text-header fallback if missing.

### Integration points

- `off_season_handler.py`: import + instantiate; rotation slot immediately
  after Newsmax with the same guard/log/`_tick()` shape;
  `rotation_schedule['usatoday'] = 2` (minutes); config default
  `enable_usatoday: True`.
- `wifi_config_server.py`: `enable_usatoday` default + checkbox,
  `scroll_speed_usatoday` default (5) + slider, both save paths.

## Error handling

Same posture as Newsmax: feed errors log and fall back to the placeholder
headline; display loop catches per-frame exceptions and continues; `fetch_feed`
enforces the socket timeout so a stalled host cannot hang the display thread.

## Testing

- Feed parsing/formatting: mocked feed → prefixed uppercase headlines,
  title+summary composition, dedupe, 12-item cap, empty-feed fallback.
- Config: `enable_usatoday` / `scroll_speed_usatoday` defaults present in both
  `off_season_handler` and `wifi_config_server` default dicts.
- Existing suite stays green (443 tests at time of writing).

## Out of scope

Section feeds, breaking-news push/alerts, Newsmax refactor, per-headline
timestamps.

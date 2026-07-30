# NFL Team Support Design (Bears + Chiefs)

**Date:** 2026-07-29
**Status:** Approved by user (all four sections)

## Goal

Make the NFL screens team-selectable, starting with the Kansas City Chiefs
alongside the existing Chicago Bears. The user picks an NFL team in the
admin panel (independent of the MLB team); all NFL screens — game info,
live scores, next-game card, breaking news — re-theme to that team's
colors, name, data source, and news. Team logos are added to the NFL
screens (they are currently text-only).

## Decisions made during brainstorming

- **Selectable, not replacement:** new `nfl_team` config key with an admin
  picker; default `bears` so existing boards are unchanged.
- **Logos:** add team logos to the NFL screens for the selected team AND
  opponents — all 32 NFL logos fetched once from ESPN's CDN by a committed
  dev script, resized for the LED matrix, stored in `logos/nfl/`.
- **Defaults change:** NFL content is now first-class for any board.
  `enable_bears` and `enable_bears_news` leave `NON_DEFAULT_OFF_KEYS`
  (only `enable_clock` remains); the admin team-change JS listener stops
  unchecking them.
- **Structure:** NFL packs live in `teams.py` next to the MLB packs (one
  module owns team identity/selection).
- **Naming:** `bears_display.py` keeps its filename and its config keys
  (`enable_bears`, `enable_bears_news`, `scroll_speed_bears`,
  `scroll_speed_bears_news`) — frozen schema, same rule as the MLB
  feature. Only UI labels and rendered text become team-generic.

## 1. NFL team packs (`teams.py`)

```python
@dataclass(frozen=True)
class NFLTeamPack:
    slug: str              # 'bears', 'chiefs'
    espn_slug: str         # 'chi', 'kc' (ESPN API path segment)
    abbrev: str            # 'CHI', 'KC' (ESPN competitor abbreviation)
    name: str              # 'Kansas City Chiefs'
    short_name: str        # 'Chiefs'
    header_name: str       # 'CHICAGO BEARS' / 'KANSAS CITY CHIEFS'
    primary_color: RGBColor    # Bears navy (11,22,42) / Chiefs red (227,24,55)
    accent_color: RGBColor     # Bears orange (200,56,3) / Chiefs gold (255,184,28)
    logo_path: str         # './logos/nfl/CHI.png' / './logos/nfl/KC.png'
    news_rss_url: str      # https://www.chicagobears.com/rss/news / https://www.chiefs.com/rss/news
    news_keywords: tuple[str, ...]
```

`NFL_TEAMS: dict[str, NFLTeamPack]` holds both packs.
`DEFAULT_NFL_TEAM_SLUG = 'bears'`.
`get_active_nfl_team(config: dict | None = None) -> NFLTeamPack` mirrors
`get_active_team()`: reads the `"nfl_team"` key, missing/unknown → bears.

Bears pack values reference the same RGB values as `Colors.BEARS_NAVY` /
`Colors.BEARS_ORANGE` (constants stay; the pack is the themed source).
Chiefs news keywords are authored under the same verify-or-omit accuracy
rule as the Cardinals list (team-name variants, confident current players,
legends, coach/front office, stadium: ARROWHEAD).

`NON_DEFAULT_OFF_KEYS` shrinks to `('enable_clock',)`. `apply_team_defaults`
behavior otherwise unchanged; its tests update accordingly.

## 2. NFL screens migration + logos

### `bears_display.py` (filename and class internals keep their names)

- `self.nfl_team = get_active_nfl_team()` in `__init__`.
- ESPN URL built from the pack: `f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{self.nfl_team.espn_slug}/schedule"`.
- Every `== 'CHI'` abbreviation check → `== self.nfl_team.abbrev`.
- Sweater background: pack `primary_color` field + `accent_color` stripes;
  header text from `header_name`. Internal attribute names are renamed to
  team-neutral (`self.PRIMARY`, `self.ACCENT`, `self.TEXT_WHITE`,
  `self.TEXT_GRAY`) — they are private to the file.
- `'BEARS WIN!'`, `'BEARS SCORE!'`, `'CHI {score}'` →
  `f'{short_name.upper()} WIN!'`, `f'{short_name.upper()} SCORE!'`,
  `f'{abbrev} {score}'` — byte-identical for Bears.
- **Logos:** live-score screen shows a small logo beside each team's score
  row (selected team and opponent, looked up by ESPN abbreviation in
  `logos/nfl/`); the next-game card shows both logos around the VS/AT
  line. Missing logo file → text-only fallback (no placeholder box), so a
  logo-less opponent renders exactly as today. Exact pixel sizes/positions
  are a starting point for on-hardware iteration.

### NFL news (`off_season_handler.py`)

- RSS: pack `news_rss_url` primary (fallback feeds unchanged).
- Keyword filter: pack `news_keywords`.
- Loading/news screens + the handler's own sweater background: pack colors
  and `header_name`; news prefix becomes
  `f'{short_name.upper()} NEWS: '` (byte-identical for Bears).

### Logo assets

`dev/fetch_nfl_logos.py` (committed): downloads
`https://a.espncdn.com/i/teamlogos/nfl/500/{espn_slug}.png` for all 32 NFL
teams, resizes to 20x20 (LANCZOS, RGBA preserved), writes
`logos/nfl/{ABBREV}.png`. On-screen render sizes start at 14x14 on the
live-score rows and 18x18 on the next-game card (resized from the 20x20
source at draw time; iterate on hardware). All 32 output files are committed. The
script is rerunnable (source of truth for regeneration). Logo art is
ESPN's own CDN content, used only on the user's private display.

## 3. Admin changes (`wifi_config_server.py`)

- Team section gains an **NFL Team** sub-block below the MLB picker: radio
  cards (logo + color swatch) rendered from `NFL_TEAMS`; logo served by a
  new `/nfl_logo/<slug>` route (404 unknown).
- `nfl_team` round-trips all four layers (HTML, saveConfig JS, page-load
  restore with `window._loadedNflTeam`, server defaults `'bears'`), with
  the same stale-page guard as `team` (`data.get('nfl_team',
  current_config.get('nfl_team', DEFAULT_NFL_TEAM_SLUG))`) and the same
  null-radio fallback.
- Changing `nfl_team` triggers the same "REBOOT required" save notice
  (extend the teamChanged check).
- The team-change JS listener no longer touches `enable_bears` /
  `enable_bears_news` (only `enable_clock` + custom message logic remain).
- Checkbox labels: "Enable NFL team game display", "Enable NFL breaking
  news"; scroll-speed labels "NFL Game:", "NFL News:".

## 4. Testing

- `get_active_nfl_team()` resolution: default, explicit chiefs, unknown →
  bears.
- Pack completeness: both packs' logo paths exist; all 32
  `logos/nfl/*.png` files present and PIL-openable.
- Chiefs keyword sanity (contains 'CHIEFS' and 'ARROWHEAD'; no 'BEARS').
- BearsDisplay construction under each pack: Bears output strings
  byte-identical to today; Chiefs strings correct.
- Admin: `/admin` offers both NFL radios; `nfl_team` save round-trip;
  POST without the key preserves an existing 'chiefs' value;
  `/nfl_logo/<slug>` 200/404.
- `apply_team_defaults`: bears keys no longer forced off for non-Cubs;
  clock still is.
- Gates: full pytest suite green; `python3 -m py_compile` on changed files.

## Out of scope

- NFL team packs beyond Bears and Chiefs (architecture supports adding
  more; selector shows only packs that exist)
- Renaming `bears_display.py`, its class, or any config keys
- MLB-side changes beyond the `NON_DEFAULT_OFF_KEYS` shrink
- Live theme switching without reboot

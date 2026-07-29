# Multi-Team Support Design (Cubs + Cardinals)

**Date:** 2026-07-29
**Status:** Approved by user (all four sections)

## Goal

Make the LED marquee scoreboard usable for MLB teams other than the Cubs,
starting with the St. Louis Cardinals. The user picks a team in the admin
panel; the board follows that team's games and rebrands to that team's
colors, logos, text, and content. Also clean up the admin Display Config
tab, which has grown into one flat scroll of ~40 controls.

## Decisions made during brainstorming

- **Content depth:** Full Cardinals content parity — facts, history, news,
  win celebration, and marquee image (not just colors/schedule).
- **Architecture:** Per-team "team pack" designed for all 30 MLB teams;
  ship complete Cubs and Cardinals packs now. The team selector lists only
  teams that have packs.
- **Pack format:** Python module (`teams.py`) with a `TeamPack` dataclass
  and `TEAMS` dict — not JSON folders. Facts/history stay as JSON data files.
- **Admin layout:** Keep one Display Config tab, reorganized into
  collapsible sections. Team section first, expanded by default.
- **Control audit:** Every existing slider/checkbox must be verified to map
  to a config key that the scoreboard actually reads; dead controls get
  fixed or removed (findings reported before removal).
- **Bears & Wrigley clock:** Remain available as toggles for every team;
  they default to off when a non-Cubs pack is selected. No new code paths.
- **Apply semantics:** Team change takes effect after reboot, matching the
  established "always reboot after config change" workflow.

## 1. Team pack core (`teams.py`)

New module `teams.py`:

```python
@dataclass(frozen=True)
class TeamPack:
    slug: str              # 'cubs', 'cardinals'
    mlb_team_id: int       # Cubs 112, Cardinals 138
    name: str              # 'St. Louis Cardinals'
    short_name: str        # 'Cardinals'
    abbrev: str            # 'STL'
    matchup_name: str      # 'ST LOUIS CARDINALS' (pre-game "X VS Y" text)
    primary_color: RGBColor    # Cubs (0,51,102) / Cardinals (196,30,58)
    secondary_color: RGBColor  # Cardinals navy (12,35,64)
    logo_path: str         # './logos/cubs.png' / './logos/STL.png'
    marquee_path: str      # './marquee.png' / './cardinals_marquee.png'
    celebration_path: str  # './W.gif' / './cards_win.gif'
    facts_path: str        # 'cubs_facts.json' / 'cardinals_facts.json'
    history_path: str      # 'cubs_history.json' / 'cardinals_history.json'
    # facts/history hold basenames; consumers resolve them the way they do
    # today (try ./ then /home/pi/), preserving existing lookup behavior
    news_rss_url: str      # team MLB.com RSS feed
```

`TEAMS: dict[str, TeamPack]` holds both packs. `get_active_team() ->
TeamPack` reads the new `"team"` key from `/home/pi/config.json` via the
existing cached `load_user_config()`, defaulting to `"cubs"` (unknown
values also fall back to cubs). Existing boards without the key behave
exactly as today.

Yellow (`Colors.YELLOW`) remains the shared scoreboard accent color.

### Call-site migration

All hardcoded Cubs references switch to the active pack:

- `TeamConfig.CUBS_TEAM_ID` (main.py, scoreboard_manager.py,
  live_game_handler.py, game_state_handler.py, playoff_race_display.py,
  spring_training_display.py, allstar_display.py, cubs_history_display.py,
  setup_display.py) → `get_active_team().mlb_team_id`
- `Colors.CUBS_BLUE` themed uses → `primary_color` (per-file review; some
  uses are genuinely "Cubs blue as a palette color" in neutral displays and
  will be judged case by case)
- `'./logos/cubs.png'` (scoreboard_manager.py:207) → `logo_path`
- `'./marquee.png'` (scoreboard_manager.py:231, off_season_handler.py:124)
  → `marquee_path`
- `'./W.gif'` (live_game_handler.py:795) → `celebration_path`
- `"CHICAGO CUBS VS {opponent}"` (game_state_handler.py:70) →
  `f"{matchup_name} VS {opponent}"`
- `'Cubs Pitcher:'` strings (scoreboard_manager.py:314-317) → short_name
- Cubs facts path (off_season_handler.py:203), history paths
  (cubs_history_display.py:16), and Cubs RSS feed list
  (off_season_handler.py:237-241) → pack paths/URL (ESPN + CBS MLB
  fallback feeds stay for all teams)

`TeamConfig.CUBS_TEAM_ID` is removed once no call sites remain; tests
updated accordingly.

## 2. Cardinals content pack

- **`cardinals_facts.json`** — ~200+ Cardinals trivia facts, same
  `{"facts": [...]}` format as `cubs_facts.json`.
- **`cardinals_history.json`** — "Today in Cardinals History", same
  `{"MM-DD": [{"year": N, "text": "..."}]}` format as `cubs_history.json`.
- **News RSS** — `https://www.mlb.com/cardinals/feeds/news/rss.xml`
  primary, existing ESPN/CBS MLB feeds as fallback.
- **`cardinals_marquee.png`** — pixel-art Cardinals marquee (Cardinals red,
  birds-on-bat styling), same dimensions as `marquee.png`. Expect visual
  iteration on the Pi.
- **`cards_win.gif`** — "CARDS WIN!" animated celebration in team colors
  (Cardinals have no W-flag tradition). Same frame-animation mechanism as
  `W.gif`. Expect visual iteration on the Pi.
- **Logo** — `logos/STL.png` already exists.

Display names shown in the UI follow the team (e.g. "Today in Cardinals
History", "Cardinals facts").

## 3. Admin Display Config redesign

Rebuild the Display Config tab content (wifi_config_server.py, lines
~572-930) as collapsible sections using styled `<details>`/`<summary>`:

1. **Team** — open by default. Team picker (cards or radio list) showing
   each pack's logo and color swatch. Saves as `"team"` slug.
2. **Brightness & Auto-Dim** — collapsed
3. **Display Mode** — collapsed
4. **Content Displays** — collapsed; checkboxes grouped by category
   (Baseball, Other Sports, News & Info, Sky & Flight, Faith, Fun)
5. **Scroll Speeds** — collapsed
6. **Flight Tracking** — collapsed
7. **Weather & Location** — collapsed
8. **Custom Message** — collapsed

Single Save button as today. The save response reminds the user to reboot
for a team change to take effect.

**Control audit:** trace every control → config key → Python consumer.
Fix or remove dead controls; report findings before removal. Verify the
save/load JS round-trips every key (including the new `team` key).

## 4. Testing & rollout

New pytest coverage (rgbmatrix mocked, as existing tests do):

- `get_active_team()` resolution: explicit cubs, explicit cardinals,
  missing key → cubs, unknown slug → cubs
- Pack completeness: every `TeamPack` path field points at an existing file
- Cardinals data files parse and match the expected schema
- Config validator accepts the `team` key
- Per-team admin defaults (Bears/clock default off for cardinals)
- Existing tests updated where they assume Cubs constants

Verification: `pytest tests/ -v` plus `python3 -m py_compile` on changed
files (the auto-updater's gate). Manual display verification on the Pi.

Rollout: normal flow — git push; Pis pick it up via nightly auto-update or
manual sync to `/home/pi/` root; reboot. Existing configs keep working
unchanged (team defaults to cubs).

## Out of scope

- Packs for the other 28 MLB teams (architecture supports them; content
  not authored)
- NFL team selection / non-Chicago football content
- Renaming the repo, service names, hostnames, or log paths
- Live theme switching without reboot

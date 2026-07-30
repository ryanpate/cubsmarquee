# NFL Team Support (Bears + Chiefs) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the NFL screens team-selectable (Bears or Chiefs) via a new `nfl_team` config key with an admin picker, and add team logos to the NFL screens.

**Architecture:** `NFLTeamPack` frozen dataclass in `teams.py` (mirroring the MLB `TeamPack`), consumed by `bears_display.py` and the NFL-news portion of `off_season_handler.py`. All 32 NFL logos are fetched once by a committed dev script into `logos/nfl/` and rendered on the score rows and next-game card. Admin panel gets an NFL Team radio picker with the same four-layer round-trip and reboot-notice semantics as the MLB picker.

**Tech Stack:** Python 3.9+ (`from __future__ import annotations`), PIL, Flask, pytest (rgbmatrix mocked in `tests/conftest.py`).

**Spec:** `docs/superpowers/specs/2026-07-29-nfl-team-support-design.md`

## Global Constraints

- **Frozen config keys — never rename:** `enable_bears`, `enable_bears_news`, `scroll_speed_bears`, `scroll_speed_bears_news`. Only UI labels and rendered text change. The one NEW key is `nfl_team` (default `'bears'`).
- **`bears_display.py` keeps its filename and its `BearsDisplay` class name.** Internal attribute names may be renamed.
- **Bears rendered strings must be byte-identical to today** when `nfl_team` is missing or `'bears'`: `'BEARS WIN!'`, `'BEARS SCORE!'`, `'CHICAGO BEARS'`, news prefix `'BEARS NEWS - '`.
- Bears colors: navy `(11, 22, 42)`, orange `(200, 56, 3)`. Chiefs colors: red `(227, 24, 55)`, gold `(255, 184, 28)`.
- ESPN slugs: Bears `chi`/`CHI`, Chiefs `kc`/`KC`. Logo CDN: `https://a.espncdn.com/i/teamlogos/nfl/500/{slug}.png`.
- Every task ends with: `python3 -m py_compile` on each changed `.py` file, the task's tests passing, and a commit. Run the FULL suite (`python3 -m pytest tests/ -v`) in Task 6.
- Do NOT `git push` (pushing = deploying to the Pi fleet; user's call).
- Work happens on a feature branch off local `main` (created at execution time via superpowers:using-git-worktrees; note `origin/main` is behind local `main` — branch from `HEAD`, not `origin/main`).

---

### Task 1: NFL team packs in `teams.py` + `NON_DEFAULT_OFF_KEYS` shrink

**Files:**
- Modify: `teams.py` (add `NFLTeamPack`, `NFL_TEAMS`, `DEFAULT_NFL_TEAM_SLUG`, `get_active_nfl_team`; shrink `NON_DEFAULT_OFF_KEYS` at lines 18-19)
- Modify: `tests/test_teams.py` (update `test_cardinals_turns_off_chicago_content` ~line 86; add new test classes)
- Modify: `tests/test_team_data.py` (update `test_cardinals_defaults_disable_bears` ~line 194 and `test_cubs_defaults_keep_bears` ~line 199)
- Modify: `tests/test_admin_config.py` (update `test_load_config_cardinals_disables_bears_by_default` ~line 37)
- Modify: `CLAUDE.md` (the `teams.py` row in the Core Application table)

**Interfaces:**
- Produces: `NFLTeamPack` dataclass with fields `slug, espn_slug, abbrev, name, short_name, header_name, primary_color, accent_color, logo_path, news_rss_url, news_keywords`; `NFL_TEAMS: dict[str, NFLTeamPack]` with keys `'bears'`, `'chiefs'`; `DEFAULT_NFL_TEAM_SLUG = 'bears'`; `get_active_nfl_team(config: dict | None = None) -> NFLTeamPack`. Tasks 3, 4, 5 import these from `teams`.
- Produces: `NON_DEFAULT_OFF_KEYS == ('enable_clock',)` — the admin JS team-change listener consumes this via template injection (`non_default_off_keys=NON_DEFAULT_OFF_KEYS` at `wifi_config_server.py:1738`), so it automatically stops unchecking the bears keys with **no admin code change** in this task.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_teams.py`:

```python
from teams import (
    NFL_TEAMS, DEFAULT_NFL_TEAM_SLUG, get_active_nfl_team)


class TestGetActiveNflTeam:
    def test_default_is_bears_when_config_empty(self):
        assert get_active_nfl_team({}).slug == 'bears'

    def test_explicit_bears(self):
        assert get_active_nfl_team({'nfl_team': 'bears'}).slug == 'bears'

    def test_explicit_chiefs(self):
        pack = get_active_nfl_team({'nfl_team': 'chiefs'})
        assert pack.slug == 'chiefs'
        assert pack.abbrev == 'KC'

    def test_unknown_slug_falls_back_to_bears(self):
        assert get_active_nfl_team({'nfl_team': 'packers'}).slug == 'bears'

    def test_none_config_uses_load_user_config(self, monkeypatch):
        import teams
        monkeypatch.setattr(
            teams, 'load_user_config', lambda: {'nfl_team': 'chiefs'})
        assert get_active_nfl_team().slug == 'chiefs'


class TestNflPackValues:
    def test_both_packs_present(self):
        assert set(NFL_TEAMS) == {'bears', 'chiefs'}
        assert DEFAULT_NFL_TEAM_SLUG == 'bears'

    def test_slug_matches_dict_key(self):
        for slug, pack in NFL_TEAMS.items():
            assert pack.slug == slug

    def test_bears_pack_values(self):
        b = NFL_TEAMS['bears']
        assert b.espn_slug == 'chi'
        assert b.abbrev == 'CHI'
        assert b.header_name == 'CHICAGO BEARS'
        assert b.primary_color == (11, 22, 42)
        assert b.accent_color == (200, 56, 3)
        assert b.logo_path == './logos/nfl/CHI.png'
        assert b.news_rss_url == 'https://www.chicagobears.com/rss/news'

    def test_chiefs_pack_values(self):
        c = NFL_TEAMS['chiefs']
        assert c.espn_slug == 'kc'
        assert c.abbrev == 'KC'
        assert c.header_name == 'KANSAS CITY CHIEFS'
        assert c.primary_color == (227, 24, 55)
        assert c.accent_color == (255, 184, 28)
        assert c.logo_path == './logos/nfl/KC.png'
        assert c.news_rss_url == 'https://www.chiefs.com/rss/news'

    def test_chiefs_keywords_sanity(self):
        kw = NFL_TEAMS['chiefs'].news_keywords
        assert 'CHIEFS' in kw
        assert 'ARROWHEAD' in kw
        assert not any('BEARS' in k for k in kw)

    def test_bears_keywords_sanity(self):
        kw = NFL_TEAMS['bears'].news_keywords
        assert 'BEARS' in kw
        assert 'SOLDIER FIELD' in kw
        assert not any('CHIEFS' in k for k in kw)


class TestNonDefaultOffKeysShrink:
    def test_only_clock_remains(self):
        from teams import NON_DEFAULT_OFF_KEYS
        assert NON_DEFAULT_OFF_KEYS == ('enable_clock',)

    def test_cardinals_keeps_bears_content_on(self):
        from teams import apply_team_defaults
        defaults = {'enable_bears': True, 'enable_bears_news': True,
                    'enable_clock': True}
        adjusted = apply_team_defaults(defaults, {'team': 'cardinals'})
        assert adjusted['enable_bears'] is True
        assert adjusted['enable_bears_news'] is True
        assert adjusted['enable_clock'] is False
```

Then update the three existing tests that assert bears keys are forced off for non-Cubs teams so they now assert only the clock is:

- `tests/test_teams.py::test_cardinals_turns_off_chicago_content` (~line 86): keep the assert that `enable_clock` becomes `False`; change the `enable_bears`/`enable_bears_news` asserts to expect the defaults to pass through unchanged (`True`).
- `tests/test_team_data.py::test_cardinals_defaults_disable_bears` (~line 194): rename to `test_cardinals_defaults_disable_clock_only` and assert `enable_bears is True`, `enable_bears_news is True`, `enable_clock is False`.
- `tests/test_team_data.py::test_cubs_defaults_keep_bears` (~line 199): unchanged behavior for Cubs; just confirm it still passes.
- `tests/test_admin_config.py::test_load_config_cardinals_disables_bears_by_default` (~line 37): rename to `test_load_config_cardinals_keeps_bears_by_default` and flip the assertion at line 42 to `assert cfg['enable_bears'] is True`; add `assert cfg['enable_clock'] is False`.

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `python3 -m pytest tests/test_teams.py tests/test_team_data.py tests/test_admin_config.py -v`
Expected: new `TestGetActiveNflTeam`/`TestNflPackValues` tests FAIL with `ImportError: cannot import name 'NFL_TEAMS'`; the updated shrink tests FAIL because `NON_DEFAULT_OFF_KEYS` still contains the bears keys.

- [ ] **Step 3: Implement in `teams.py`**

Change `NON_DEFAULT_OFF_KEYS` (lines 16-19) — update the comment too:

```python
# Content that only makes sense for a Chicago board; defaults to off for
# other teams unless the user explicitly re-enables it in the admin panel.
# NFL content is first-class for any board (see NFL_TEAMS below), so only
# the Wrigley clock remains here.
NON_DEFAULT_OFF_KEYS: tuple[str, ...] = ('enable_clock',)
```

Add below the `DEFAULT_CUSTOM_MESSAGES` block (keep the MLB section intact):

```python
DEFAULT_NFL_TEAM_SLUG = 'bears'


@dataclass(frozen=True)
class NFLTeamPack:
    """Everything the NFL screens need to brand themselves for one team"""
    slug: str
    espn_slug: str             # ESPN API path segment ('chi', 'kc')
    abbrev: str                # ESPN competitor abbreviation ('CHI', 'KC')
    name: str
    short_name: str
    header_name: str           # sweater-header text, e.g. 'CHICAGO BEARS'
    primary_color: RGBColor    # sweater background
    accent_color: RGBColor     # sweater stripes, highlights
    logo_path: str             # 20x20 RGBA PNG in logos/nfl/
    news_rss_url: str
    news_keywords: tuple[str, ...]  # RSS headline filter for team news


NFL_TEAMS: dict[str, NFLTeamPack] = {
    'bears': NFLTeamPack(
        slug='bears',
        espn_slug='chi',
        abbrev='CHI',
        name='Chicago Bears',
        short_name='Bears',
        header_name='CHICAGO BEARS',
        primary_color=(11, 22, 42),
        accent_color=(200, 56, 3),
        logo_path='./logos/nfl/CHI.png',
        news_rss_url='https://www.chicagobears.com/rss/news',
        news_keywords=(
            'BEARS', 'CHICAGO BEARS', 'CHI BEARS', 'DA BEARS',
            'CALEB WILLIAMS', 'DJ MOORE', 'D.J. MOORE',
            'KEENAN ALLEN', 'ROME ODUNZE', 'COLE KMET',
            'MONTEZ SWEAT', 'TREMAINE EDMUNDS', 'JAYLON JOHNSON',
            "D'ANDRE SWIFT", 'KYLER GORDON', 'JAQUAN BRISKER',
            'BEN JOHNSON', 'RYAN POLES',
            'SOLDIER FIELD', 'HALAS HALL',
        ),
    ),
    'chiefs': NFLTeamPack(
        slug='chiefs',
        espn_slug='kc',
        abbrev='KC',
        name='Kansas City Chiefs',
        short_name='Chiefs',
        header_name='KANSAS CITY CHIEFS',
        primary_color=(227, 24, 55),
        accent_color=(255, 184, 28),
        logo_path='./logos/nfl/KC.png',
        news_rss_url='https://www.chiefs.com/rss/news',
        news_keywords=(
            # Team names and variations
            'CHIEFS', 'KANSAS CITY CHIEFS', 'KC CHIEFS', 'CHIEFS KINGDOM',

            # Current players (verified on KC roster; ambiguous bare
            # surnames like KELCE/RICE/WORTHY/JONES are full-name only)
            'PATRICK MAHOMES', 'MAHOMES',
            'TRAVIS KELCE',
            'CHRIS JONES',
            'ISIAH PACHECO', 'PACHECO',
            'RASHEE RICE',
            'XAVIER WORTHY',
            'TRENT MCDUFFIE', 'MCDUFFIE',
            'NICK BOLTON',
            'CREED HUMPHREY',
            'GEORGE KARLAFTIS', 'KARLAFTIS',
            'HARRISON BUTKER', 'BUTKER',

            # Coaches and front office
            'ANDY REID',
            'STEVE SPAGNUOLO', 'SPAGNUOLO',
            'BRETT VEACH',

            # Retired Chiefs legends
            'LEN DAWSON',
            'DERRICK THOMAS',
            'JAMAAL CHARLES',
            'PRIEST HOLMES',
            'WILLIE LANIER',
            'BOBBY BELL',

            # Stadium
            'ARROWHEAD', 'GEHA FIELD',
        ),
    ),
}


def get_active_nfl_team(config: dict | None = None) -> NFLTeamPack:
    """Resolve the active NFL pack from config (or the user config file)"""
    if config is None:
        config = load_user_config()
    slug = config.get('nfl_team', DEFAULT_NFL_TEAM_SLUG)
    return NFL_TEAMS.get(slug, NFL_TEAMS[DEFAULT_NFL_TEAM_SLUG])
```

The Bears keyword tuple is copied verbatim from the local `bears_keywords` list in `off_season_handler.py:350-358` (Task 4 switches that code to read from the pack).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_teams.py tests/test_team_data.py tests/test_admin_config.py -v`
Expected: ALL PASS (including the flipped admin default test — `load_config` merges via `apply_team_defaults`, which now leaves the bears keys alone).

- [ ] **Step 5: Update `CLAUDE.md`**

In the Core Application table, change the `teams.py` row description to:
`Team packs — MLB (Cubs, Cardinals) and NFL (Bears, Chiefs): identity, colors, assets, content sources incl. news keywords`

- [ ] **Step 6: Compile-check and commit**

Run: `python3 -m py_compile teams.py`
```bash
git add teams.py tests/test_teams.py tests/test_team_data.py tests/test_admin_config.py CLAUDE.md
git commit -m "feat: add NFL team packs (Bears, Chiefs); NFL content on by default for all boards"
```

---

### Task 2: NFL logo fetch script + 32 committed logos

**Files:**
- Create: `dev/fetch_nfl_logos.py`
- Create: `logos/nfl/*.png` (32 files, generated by the script, committed)
- Modify: `tests/test_pack_completeness.py` (append NFL logo tests)

**Interfaces:**
- Consumes: `NFL_TEAMS` from Task 1 (for the logo-path existence test).
- Produces: `logos/nfl/{ABBREV}.png` for all 32 ESPN abbreviations — 20x20 RGBA PNGs. Task 3 loads them by ESPN competitor abbreviation: `./logos/nfl/{abbrev}.png`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pack_completeness.py`:

```python
import os
from PIL import Image

from teams import NFL_TEAMS

# ESPN competitor abbreviations for all 32 NFL teams (uppercase of the
# CDN slug used by dev/fetch_nfl_logos.py)
NFL_ABBREVS = [
    'ARI', 'ATL', 'BAL', 'BUF', 'CAR', 'CHI', 'CIN', 'CLE',
    'DAL', 'DEN', 'DET', 'GB', 'HOU', 'IND', 'JAX', 'KC',
    'LAC', 'LAR', 'LV', 'MIA', 'MIN', 'NE', 'NO', 'NYG',
    'NYJ', 'PHI', 'PIT', 'SEA', 'SF', 'TB', 'TEN', 'WSH',
]


class TestNflLogos:
    def test_all_32_logos_exist_and_open(self):
        for abbrev in NFL_ABBREVS:
            path = f'./logos/nfl/{abbrev}.png'
            assert os.path.exists(path), f'missing {path}'
            with Image.open(path) as img:
                assert img.size == (20, 20), f'{path} is {img.size}'
                assert img.mode == 'RGBA', f'{path} is {img.mode}'

    def test_pack_logo_paths_exist(self):
        for pack in NFL_TEAMS.values():
            assert os.path.exists(pack.logo_path)
            assert pack.abbrev in {
                os.path.splitext(f)[0] for f in os.listdir('./logos/nfl')}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_pack_completeness.py -v`
Expected: FAIL — `logos/nfl/` does not exist yet.

- [ ] **Step 3: Write the fetch script**

Create `dev/fetch_nfl_logos.py`:

```python
"""Fetch all 32 NFL team logos from ESPN's CDN for the LED matrix.

Downloads https://a.espncdn.com/i/teamlogos/nfl/500/{slug}.png for every
team, resizes to 20x20 (LANCZOS, RGBA preserved), and writes
logos/nfl/{ABBREV}.png. Rerunnable; this script is the source of truth
for regenerating the committed logo files.

Usage (from the repo root): python3 dev/fetch_nfl_logos.py
"""

from __future__ import annotations

import io
import os

import requests
from PIL import Image

# ESPN CDN slug for each team; output filename is slug.upper() which
# matches the abbreviation ESPN's API uses for competitors.
CDN_SLUGS = [
    'ari', 'atl', 'bal', 'buf', 'car', 'chi', 'cin', 'cle',
    'dal', 'den', 'det', 'gb', 'hou', 'ind', 'jax', 'kc',
    'lac', 'lar', 'lv', 'mia', 'min', 'ne', 'no', 'nyg',
    'nyj', 'phi', 'pit', 'sea', 'sf', 'tb', 'ten', 'wsh',
]

OUT_DIR = './logos/nfl'
SIZE = (20, 20)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    for slug in CDN_SLUGS:
        url = f'https://a.espncdn.com/i/teamlogos/nfl/500/{slug}.png'
        out_path = f'{OUT_DIR}/{slug.upper()}.png'
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        img = Image.open(io.BytesIO(response.content)).convert('RGBA')
        img = img.resize(SIZE, Image.LANCZOS)
        img.save(out_path)
        print(f'{out_path} written ({len(response.content)} bytes source)')
    print(f'Done: {len(CDN_SLUGS)} logos in {OUT_DIR}')


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Run the script from the repo root**

Run: `python3 dev/fetch_nfl_logos.py`
Expected: 32 lines of `./logos/nfl/XXX.png written`, no exceptions. (Network required; if the CDN blocks a request, retry once before investigating.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_pack_completeness.py -v`
Expected: PASS.

- [ ] **Step 6: Visually sanity-check two logos**

Run: `python3 -c "from PIL import Image; [print(p, Image.open(p).size, Image.open(p).mode) for p in ['./logos/nfl/CHI.png', './logos/nfl/KC.png']]"`
Expected: both `(20, 20) RGBA`.

- [ ] **Step 7: Compile-check and commit**

Run: `python3 -m py_compile dev/fetch_nfl_logos.py`
```bash
git add dev/fetch_nfl_logos.py logos/nfl tests/test_pack_completeness.py
git commit -m "feat: add NFL logo fetch script and all 32 team logos (20x20)"
```

---

### Task 3: `bears_display.py` pack migration + logos on the NFL screens

**Files:**
- Modify: `bears_display.py`
- Modify: `tests/test_core_logic.py` (`extract_situation` tests ~lines 507-546, `celebration_message` test ~line 606)
- Test: `tests/test_teams.py` (append a `TestBearsDisplayTheming` class)

**Interfaces:**
- Consumes: `get_active_nfl_team` from `teams` (Task 1); `logos/nfl/{abbrev}.png` files (Task 2).
- Produces: `BearsDisplay` instances now carry `self.nfl_team` (an `NFLTeamPack`), `self.PRIMARY`, `self.ACCENT`, `self.TEXT_WHITE`, `self.TEXT_GRAY`, and `self.schedule_url`. Module functions gain parameters: `extract_situation(competition: dict, team_abbrev: str = 'CHI') -> dict` (its `possession` value is now `'team'`/`'opponent'`/None — **not** `'bears'`), and `celebration_message(delta: int, team_name: str = 'BEARS') -> str`. Task 4's handler constructs `BearsDisplay` unchanged (no signature change).

- [ ] **Step 1: Write the failing tests**

In `tests/test_core_logic.py`, update the situation tests (~lines 507-546): everywhere a test asserts `['possession'] == 'bears'`, change to `== 'team'`; add one new test to the same class:

```python
    def test_possession_with_custom_team_abbrev(self) -> None:
        from bears_display import extract_situation
        competition = self._competition_with_situation({'possession': '3'})
        # abbreviation 'CHI' belongs to team id 3 in this fixture; asking
        # for KC means neither side matches the selected team's abbrev
        result = extract_situation(competition, team_abbrev='KC')
        assert result['possession'] == 'opponent'
```

(Check the fixture `_competition_with_situation` first: possession id `'3'` maps to the competitor whose abbreviation is `'CHI'`. The point is that `team_abbrev` decides which side is `'team'`.)

Update the celebration test (~line 606) and add the parameterized case:

```python
    def test_celebration_messages(self) -> None:
        from bears_display import celebration_message
        assert celebration_message(7) == 'TOUCHDOWN!'
        assert celebration_message(3) == 'FIELD GOAL!'
        assert celebration_message(2) == 'SAFETY!'
        assert celebration_message(1) == 'BEARS SCORE!'
        assert celebration_message(1, 'CHIEFS') == 'CHIEFS SCORE!'
```

(Keep any existing delta assertions in that test that already pass — only add the default/team_name cases shown.)

Append to `tests/test_teams.py`:

```python
class TestBearsDisplayTheming:
    def _make_display(self, monkeypatch, config):
        from unittest.mock import MagicMock
        import teams
        import bears_display
        monkeypatch.setattr(teams, 'load_user_config', lambda: config)
        return bears_display.BearsDisplay(MagicMock())

    def test_bears_default_theming(self, monkeypatch):
        d = self._make_display(monkeypatch, {})
        assert d.nfl_team.slug == 'bears'
        assert '/teams/chi/schedule' in d.schedule_url
        assert d.PRIMARY == (11, 22, 42)
        assert d.ACCENT == (200, 56, 3)

    def test_chiefs_theming(self, monkeypatch):
        d = self._make_display(monkeypatch, {'nfl_team': 'chiefs'})
        assert d.nfl_team.slug == 'chiefs'
        assert '/teams/kc/schedule' in d.schedule_url
        assert d.PRIMARY == (227, 24, 55)
        assert d.ACCENT == (255, 184, 28)

    def test_win_message_strings(self, monkeypatch):
        from unittest.mock import MagicMock
        for config, expected in (
                ({}, 'BEARS WIN!'),
                ({'nfl_team': 'chiefs'}, 'CHIEFS WIN!')):
            d = self._make_display(monkeypatch, config)
            d.manager = MagicMock()
            d._draw_final_content(
                {'bears_score': '21', 'opp_score': '14',
                 'opponent_abbr': 'GB'}, frame_count=0)
            drawn = [call.args[4] for call in
                     d.manager.draw_text.call_args_list]
            assert expected in drawn
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_core_logic.py tests/test_teams.py -v`
Expected: the updated situation tests FAIL (`'bears' != 'team'`), the celebration `team_name` case FAILS (`TypeError`), and `TestBearsDisplayTheming` FAILS (`AttributeError: nfl_team`).

- [ ] **Step 3: Migrate `bears_display.py` to the pack**

All edits below; line numbers refer to the pre-edit file.

1. Import (line 11-13 block): add `from teams import get_active_nfl_team`.

2. `extract_situation` (line 19): signature becomes `def extract_situation(competition: dict, team_abbrev: str = 'CHI') -> dict:`; line 40 becomes `if team.get('abbreviation') == team_abbrev:` and line 41 becomes `result['possession'] = 'team'`.

3. `celebration_message` (line 98): signature becomes `def celebration_message(delta: int, team_name: str = 'BEARS') -> str:`; last return becomes `return f'{team_name} SCORE!'`.

4. `__init__` (lines 119-134): replace the color block with:

```python
        # Team pack drives all theming; default (missing/unknown key) is
        # the Bears, so existing boards render exactly as before.
        self.nfl_team = get_active_nfl_team()
        self.schedule_url = (
            'https://site.api.espn.com/apis/site/v2/sports/football/nfl/'
            f'teams/{self.nfl_team.espn_slug}/schedule')

        self.PRIMARY: RGBColor = self.nfl_team.primary_color
        self.ACCENT: RGBColor = self.nfl_team.accent_color
        self.TEXT_WHITE: RGBColor = Colors.WHITE
        self.TEXT_GRAY: RGBColor = (170, 170, 170)

        # Team logos keyed by (abbrev, size); None = file missing
        self._logo_cache: dict[tuple[str, int], Image.Image | None] = {}
```

Then rename every remaining `self.BEARS_NAVY` → `self.PRIMARY`, `self.BEARS_ORANGE` → `self.ACCENT`, `self.BEARS_WHITE` → `self.TEXT_WHITE`, `self.BEARS_GRAY` → `self.TEXT_GRAY` throughout the file (`grep -n 'BEARS_' bears_display.py` must come back empty afterwards).

5. `_fetch_bears_schedule` (line 183): `url = self.schedule_url` (drop the hardcoded string and the "team ID: 3" comment); log line becomes `print(f"{self.nfl_team.short_name} schedule updated")`.

6. Abbreviation checks: lines 262, 295, 547, 640 — `== 'CHI'` becomes `== self.nfl_team.abbrev`. Keep local variable names (`bears`, `bears_home`, `bears_score`) — internal only.

7. `_get_current_scores` situation call (line 330): `situation = extract_situation(competition, self.nfl_team.abbrev)`.

8. `_draw_live_content` possession checks (lines 472-475): `possession == 'bears'` becomes `possession == 'team'`.

9. `_play_scoring_celebration` (line 531): `message = celebration_message(delta, self.nfl_team.short_name.upper())`.

10. `_draw_sweater_header` (lines 351-357): compute the header from the pack:

```python
    def _draw_sweater_header(self):
        """Draw the compact sweater header using the cached background"""
        self.manager.set_image(self._bears_sweater_bg, 0, 0)
        header = self.nfl_team.header_name
        x = max(0, (96 - len(header) * Fonts.CHAR_WIDTH_TINY) // 2)
        self.manager.draw_text('tiny_bold', x, 9, self.TEXT_WHITE, header)
```

(Verify `Fonts.CHAR_WIDTH_TINY == 5` in `scoreboard_config.py`; for `'CHICAGO BEARS'` this computes x=15, matching today exactly. `'KANSAS CITY CHIEFS'` is 18 chars → x=3.)

11. `'BEARS WIN!'` (line 615): `message = f'{self.nfl_team.short_name.upper()} WIN!'`.

12. Add the logo helper (place after `_draw_sweater_header`):

```python
    def _get_team_logo(self, abbrev: str, size: int) -> Image.Image | None:
        """Team logo flattened onto the sweater color, or None if missing"""
        key = (abbrev, size)
        if key not in self._logo_cache:
            try:
                logo = Image.open(f'./logos/nfl/{abbrev}.png').convert(
                    'RGBA').resize((size, size), Image.LANCZOS)
                flat = Image.new('RGB', (size, size), self.PRIMARY)
                flat.paste(logo, (0, 0), logo)
                self._logo_cache[key] = flat
            except OSError:
                self._logo_cache[key] = None
        return self._logo_cache[key]
```

13. Add a shared score row with logos and use it from both live and final screens. New method:

```python
    def _draw_score_row(self, score_data):
        """Both scores on one row, each side with a 14x14 logo when the
        file exists; a missing logo falls back to today's text-only row
        for that side. Positions are a starting point for on-hardware
        iteration."""
        team_score = score_data['bears_score']
        opp_score = score_data['opp_score']
        opp_abbr = score_data['opponent_abbr']

        team_logo = self._get_team_logo(self.nfl_team.abbrev, 14)
        if team_logo is not None:
            self.manager.set_image(team_logo, 7, 13)
            self.manager.draw_text('small_bold', 24, 24,
                                   self.TEXT_WHITE, f'{team_score}')
        else:
            self.manager.draw_text(
                'small_bold', 8, 24, self.TEXT_WHITE,
                f'{self.nfl_team.abbrev} {team_score}')

        opp_logo = self._get_team_logo(opp_abbr, 14)
        if opp_logo is not None:
            self.manager.draw_text('small_bold', 56, 24,
                                   self.TEXT_WHITE, f'{opp_score}')
            self.manager.set_image(opp_logo, 75, 13)
        else:
            self.manager.draw_text('small_bold', 52, 24, self.TEXT_WHITE,
                                   f'{opp_abbr} {opp_score}')
```

In `_draw_live_content` (lines 460-468) and `_draw_final_content` (lines 596-603): delete the two hardcoded `draw_text('small_bold', 8/52, 24, ...)` pairs and call `self._draw_score_row(score_data)` instead. The possession dots (x=3 and x=91, y=18-20) stay where they are — they don't collide with the 14x14 logos at x=7-20 / x=75-88.

14. Next-game card logos in `_display_next_game` (lines 632-690). Before the `while` loop, after computing `opp_name`/`opp_line`, add:

```python
            team_logo = self._get_team_logo(self.nfl_team.abbrev, 18)
            opp_logo = self._get_team_logo(
                opponent['team'].get('abbreviation', ''), 18)
            use_logos = team_logo is not None and opp_logo is not None
```

Inside the loop, branch: when `use_logos` is False, draw **exactly today's card** (the existing draw calls, unchanged). When True, draw the logo layout — selected team left, opponent right, `VS`/`AT` between; week and countdown share the bottom line:

```python
                self.manager.draw_text('ultra_micro', 36, 17,
                                       (150, 150, 150), 'UP NEXT')
                self.manager.set_image(team_logo, 12, 19)
                self.manager.draw_text(
                    'tiny_bold', 43, 30, self.TEXT_WHITE, vs_at)
                self.manager.set_image(opp_logo, 66, 19)

                x = max(0, (96 - len(date_line) * Fonts.CHAR_WIDTH_TINY) // 2)
                self.manager.draw_text('tiny', x, 42,
                                       self.TEXT_WHITE, date_line)

                seconds = (kickoff
                           - pendulum.now('America/Chicago')).total_seconds()
                parts = [week_line] if week_line else []
                if seconds > 0:
                    parts.append(f'IN {format_countdown(seconds)}')
                    color = countdown_color(seconds, yellow_under=24 * 3600,
                                            orange_under=3 * 3600)
                else:
                    color = self.TEXT_GRAY
                if parts:
                    line = ' '.join(parts)
                    x = max(0, (96 - len(line) * Fonts.CHAR_WIDTH_MICRO) // 2)
                    self.manager.draw_text('micro', x, 47, color, line)
```

15. Update the module docstring (line 1) to `"""NFL team game display - Classic sweater style, themed by the active NFL pack"""` and the class docstring (line 117) to `"""Handles NFL game information display for the configured team"""`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_core_logic.py tests/test_teams.py tests/test_bugfixes.py -v`
Expected: ALL PASS. Also run `grep -n "BEARS_\|'CHI'\|\"CHI\"\|BEARS WIN\|BEARS SCORE" bears_display.py` — the only permitted hits are the `team_abbrev: str = 'CHI'` and `team_name: str = 'BEARS'` defaults.

- [ ] **Step 5: Compile-check and commit**

Run: `python3 -m py_compile bears_display.py`
```bash
git add bears_display.py tests/test_core_logic.py tests/test_teams.py
git commit -m "feat: theme NFL game screens from the active NFL pack, add team logos"
```

---

### Task 4: NFL news migration in `off_season_handler.py`

**Files:**
- Modify: `off_season_handler.py` (lines 13, 76-84, 141-148, 304-392, 975-987, 1010-1025)
- Modify: `tests/test_bugfixes.py` (`test_bears_news_fetch_uses_timeout` ~line 225)
- Test: `tests/test_team_data.py` (append `TestNflNewsTheming`)

**Interfaces:**
- Consumes: `get_active_nfl_team`, `NFL_TEAMS` from Task 1. `BearsDisplay` construction at line 42 is unchanged.
- Produces: `OffSeasonHandler.nfl_team` (an `NFLTeamPack`), `self.NFL_PRIMARY`, `self.NFL_ACCENT` replacing `self.BEARS_NAVY`/`self.BEARS_ORANGE` (`self.BEARS_WHITE` refs become `Colors.WHITE`).

- [ ] **Step 1: Write the failing tests**

Update `tests/test_bugfixes.py::test_bears_news_fetch_uses_timeout` (~line 225) — the `__new__`-constructed handler now needs the pack attribute:

```python
    def test_bears_news_fetch_uses_timeout(self, monkeypatch) -> None:
        import off_season_handler as osh

        seen = self._patch_network(monkeypatch)
        handler = osh.OffSeasonHandler.__new__(osh.OffSeasonHandler)
        from teams import get_active_nfl_team
        handler.nfl_team = get_active_nfl_team({})

        result = handler._fetch_bears_news_rss()

        assert result == []
        assert seen, "expected RSS fetches to go through rss_fetch"
        assert all(t and t > 0 for t in seen.values())
```

Append to `tests/test_team_data.py`:

```python
class TestNflNewsTheming:
    def _make_handler(self, nfl_slug):
        import off_season_handler as osh
        from teams import get_active_nfl_team
        handler = osh.OffSeasonHandler.__new__(osh.OffSeasonHandler)
        handler.nfl_team = get_active_nfl_team({'nfl_team': nfl_slug})
        return handler

    def test_chiefs_news_uses_pack_feed_and_prefix(self, monkeypatch):
        import off_season_handler as osh

        fetched = []

        class FakeFeed:
            bozo = False

            class Entry:
                title = 'Patrick Mahomes throws for 300 yards'

            entries = [Entry()]

            def get(self, *args):
                return None

        def fake_fetch(url):
            fetched.append(url)
            return FakeFeed()

        monkeypatch.setattr(osh, 'fetch_feed', fake_fetch)
        handler = self._make_handler('chiefs')
        headlines = handler._fetch_bears_news_rss()

        assert fetched[0] == 'https://www.chiefs.com/rss/news'
        assert headlines
        assert headlines[0].startswith('CHIEFS NEWS - ')

    def test_bears_news_prefix_unchanged(self, monkeypatch):
        import off_season_handler as osh

        class FakeFeed:
            bozo = False

            class Entry:
                title = 'Caleb Williams named starter'

            entries = [Entry()]

            def get(self, *args):
                return None

        monkeypatch.setattr(osh, 'fetch_feed', lambda url: FakeFeed())
        handler = self._make_handler('bears')
        headlines = handler._fetch_bears_news_rss()
        assert headlines[0] == 'BEARS NEWS - CALEB WILLIAMS NAMED STARTER'
```

(Note: with only one headline the `< 5` fallback path also runs — the fake `fetch_feed` serves those calls too, and the keyword filter applies; `MAHOMES`/`CALEB WILLIAMS` match their packs, so no duplicates are added beyond the primary-feed entries.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_bugfixes.py::TestNetworkTimeouts tests/test_team_data.py -v` (adjust the class path to whatever class holds `test_bears_news_fetch_uses_timeout`)
Expected: `TestNflNewsTheming` FAILS — the handler still hardcodes the Bears feed and prefix.

- [ ] **Step 3: Migrate the handler**

1. Import (line 13): `from teams import get_active_team, get_active_nfl_team, apply_team_defaults, data_path_candidates`.

2. `__init__` color block (lines 76-84) becomes:

```python
        # RSS news caching for the NFL team
        self.bears_news: list[str] | None = None
        self.last_bears_news_update: float | None = None
        self.bears_news_update_interval: int = GameConfig.NEWS_UPDATE_INTERVAL

        # NFL pack drives the football news theming (colors, feed, prefix)
        self.nfl_team = get_active_nfl_team()
        self.NFL_PRIMARY: RGBColor = self.nfl_team.primary_color
        self.NFL_ACCENT: RGBColor = self.nfl_team.accent_color
```

Then rename in this file only: `self.BEARS_NAVY` → `self.NFL_PRIMARY`, `self.BEARS_ORANGE` → `self.NFL_ACCENT`, `self.BEARS_WHITE` → `Colors.WHITE` (lines 143, 147, 985, 1016, 1061). `grep -n 'BEARS_NAVY\|BEARS_ORANGE\|BEARS_WHITE' off_season_handler.py` must come back empty.

3. `_create_bears_sweater_background` (lines 141-148): keep name; body uses `self.NFL_PRIMARY` / `self.NFL_ACCENT`; print becomes `print("NFL sweater background cached")`.

4. `_fetch_bears_news_rss` (lines 304-392):
   - `official_feed = self.nfl_team.news_rss_url` (replaces line 312).
   - Add `news_prefix = f"{self.nfl_team.short_name.upper()} NEWS - "` at the top; both `formatted_headline = f"BEARS NEWS - {headline}"` sites (lines 324, 374) become `formatted_headline = f"{news_prefix}{headline}"`.
   - Delete the local `bears_keywords` list (lines 350-358); the filter (line 371) becomes `is_team_related = any(keyword in headline for keyword in self.nfl_team.news_keywords)` (rename the flag variable at line 373 to match).
   - Reword log strings that say "Bears" to use `self.nfl_team.short_name` (e.g. `print(f"Fetching {self.nfl_team.short_name} news from official source: {official_feed}")`). Keep method names unchanged.

5. `_draw_sweater_header` (lines 1010-1016):

```python
    def _draw_sweater_header(self):
        """Draw the compact sweater header using the cached image"""
        self.manager.set_image(self._bears_sweater_bg, 0, 0)
        header = self.nfl_team.header_name
        x = max(0, (96 - len(header) * 5) // 2)
        self.manager.draw_text('tiny_bold', x, 9, Colors.WHITE, header)
```

6. `display_bears_news` fallback (line 1025): `live_news = [f"BREAKING NEWS - STAY TUNED FOR THE LATEST {self.nfl_team.short_name.upper()} UPDATES!"]`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_bugfixes.py tests/test_team_data.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Compile-check and commit**

Run: `python3 -m py_compile off_season_handler.py`
```bash
git add off_season_handler.py tests/test_bugfixes.py tests/test_team_data.py
git commit -m "feat: theme NFL news screens from the active NFL pack"
```

---

### Task 5: Admin panel NFL team picker

**Files:**
- Modify: `wifi_config_server.py` (import ~line 15; defaults ~line 152; HTML ~lines 641, 751, 758, 879, 885; JS ~lines 1165-1170, 1455-1457, 1526-1531; render kwargs ~line 1735; new route after line 1747; save handler ~line 2021)
- Modify: `tests/test_admin_config.py` (append tests)
- Modify: `CLAUDE.md` (Configuration section — add the `nfl_team` key line)

**Interfaces:**
- Consumes: `NFL_TEAMS`, `DEFAULT_NFL_TEAM_SLUG` from Task 1; `logos/nfl/*.png` from Task 2.
- Produces: `nfl_team` config key round-tripped through all four layers; `/nfl_logo/<slug>` route; `window._loadedNflTeam` page-state.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_admin_config.py` (reuse the existing `client` fixture):

```python
def test_admin_page_offers_nfl_team_choices(client):
    html = client.get('/admin').data.decode()
    assert 'name="nfl_team"' in html
    assert 'value="bears"' in html
    assert 'value="chiefs"' in html
    assert '/nfl_logo/chiefs' in html


def test_admin_page_non_default_off_keys_is_clock_only(client):
    html = client.get('/admin').data.decode()
    assert 'const NON_DEFAULT_OFF_KEYS = ["enable_clock"];' in html


def test_nfl_logo_route(client):
    resp = client.get('/nfl_logo/chiefs')
    assert resp.status_code == 200
    assert resp.mimetype == 'image/png'
    assert client.get('/nfl_logo/packers').status_code == 404


def test_save_config_round_trips_nfl_team(client):
    resp = client.post('/save_config', json={'nfl_team': 'chiefs'})
    assert resp.status_code == 200
    import wifi_config_server as wcs
    assert wcs.load_config()['nfl_team'] == 'chiefs'


def test_load_config_defaults_nfl_team_to_bears(client):
    import wifi_config_server as wcs
    assert wcs.load_config()['nfl_team'] == 'bears'


def test_save_config_without_nfl_key_preserves_existing(client):
    client.post('/save_config', json={'nfl_team': 'chiefs'})
    resp = client.post('/save_config', json={'custom_message': 'HI'})
    assert resp.status_code == 200
    import wifi_config_server as wcs
    assert wcs.load_config()['nfl_team'] == 'chiefs'


def test_admin_page_relabels_bears_controls(client):
    html = client.get('/admin').data.decode()
    assert 'Enable NFL team game display' in html
    assert 'Enable NFL breaking news display' in html
    assert 'Enable Chicago Bears display' not in html
```

(Mirror the exact style of the existing `test_save_config_round_trips_team` at line 24 — if it reads the config file directly instead of via `wcs.load_config()`, do the same here.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_admin_config.py -v`
Expected: all new tests FAIL except `test_admin_page_non_default_off_keys_is_clock_only`, which already passes via Task 1's shrink (it pins that behavior against regressions).

- [ ] **Step 3: Implement**

1. Import (lines 15-17): add `NFL_TEAMS, DEFAULT_NFL_TEAM_SLUG` to the `from teams import (...)` list.

2. Server defaults (near line 145, next to `'team': DEFAULT_TEAM_SLUG`): add `'nfl_team': DEFAULT_NFL_TEAM_SLUG,`.

3. HTML — inside the Team `<details>` section, after the MLB `{% endfor %}` (line 641), add:

```html
                    <hr style="border: none; border-top: 1px solid #444; margin: 12px 0;">
                    <p class="help-text">Pick the NFL team for the football screens (game info and breaking news). Reboot required after changing.</p>
                    {% for slug, t in nfl_teams.items() %}
                    <label class="team-option">
                        <input type="radio" name="nfl_team" value="{{ slug }}">
                        <img src="/nfl_logo/{{ slug }}" alt="{{ t.name }}">
                        <span>{{ t.name }}</span>
                        <span class="team-swatch" style="background: rgb({{ t.primary_color[0] }},{{ t.primary_color[1] }},{{ t.primary_color[2] }})"></span>
                    </label>
                    {% endfor %}
```

4. Labels: line 751 `Enable Chicago Bears display (football season)` → `Enable NFL team game display (football season)`; line 758 `Enable Bears breaking news display` → `Enable NFL breaking news display`; line 879 `<label>Bears:</label>` → `<label>NFL Game:</label>`; line 885 `<label>Bears News:</label>` → `<label>NFL News:</label>`. Do NOT touch the `id=` attributes.

5. Page-load restore JS — after the MLB team block (after line 1169 `window._loadedTeam = teamSlug;`), add:

```javascript
            const nflSlug = config.nfl_team || 'bears';
            const nflRadio = document.querySelector(
                `input[name="nfl_team"][value="${nflSlug}"]`);
            if (nflRadio) nflRadio.checked = true;
            window._loadedNflTeam = nflSlug;
```

(The MLB team-change listener needs no edits — it iterates the injected `NON_DEFAULT_OFF_KEYS`, which Task 1 shrank to the clock.)

6. saveConfig JS (near line 1455): next to `checkedTeamRadio`, add:

```javascript
            const checkedNflRadio = document.querySelector('input[name="nfl_team"]:checked');
```

and in the posted object, next to `team:`, add:

```javascript
                nfl_team: checkedNflRadio ? checkedNflRadio.value : 'bears',
```

7. Reboot notice (lines 1526-1531):

```javascript
                    const teamChanged =
                        config.team !== window._loadedTeam;
                    const nflTeamChanged =
                        config.nfl_team !== window._loadedNflTeam;
                    window._loadedTeam = config.team;
                    window._loadedNflTeam = config.nfl_team;
                    showStatus('config-status',
                        (teamChanged || nflTeamChanged)
                            ? 'Configuration saved! REBOOT the Pi for the team change to take effect (System tab).'
```

(keep the existing else-branch text unchanged).

8. Render kwargs (line 1735 area): add `nfl_teams=NFL_TEAMS,`.

9. New route after `team_logo` (line 1747):

```python
@app.route('/nfl_logo/<slug>')
def nfl_logo(slug):
    pack = NFL_TEAMS.get(slug)
    if pack is None:
        return ('Not found', 404)
    return send_file(pack.logo_path, mimetype='image/png')
```

10. Save handler (line 2020-2021 area), next to the `'team'` entry — same stale-page guard shape:

```python
            'nfl_team': data.get(
                'nfl_team', current_config.get('nfl_team', DEFAULT_NFL_TEAM_SLUG)),
```

11. `CLAUDE.md` Configuration section: after the `team` bullet, add:
`- \`nfl_team\` — active NFL team pack slug (\`bears\` default, \`chiefs\`)`

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_admin_config.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Compile-check and commit**

Run: `python3 -m py_compile wifi_config_server.py`
```bash
git add wifi_config_server.py tests/test_admin_config.py CLAUDE.md
git commit -m "feat: admin NFL team picker with nfl_team config round-trip"
```

---

### Task 6: Full-suite gate

**Files:**
- None expected (fixes only if the gate fails)

- [ ] **Step 1: Full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: ALL PASS (was 333 tests before this plan; now more). Fix any failures before proceeding — do not skip or xfail.

- [ ] **Step 2: Compile every changed file**

Run: `python3 -m py_compile teams.py bears_display.py off_season_handler.py wifi_config_server.py dev/fetch_nfl_logos.py`
Expected: silent success.

- [ ] **Step 3: Byte-identity spot-check for Bears boards**

Run:
```bash
python3 - <<'EOF'
from unittest.mock import MagicMock, patch
with patch('teams.load_user_config', lambda: {}):
    import bears_display
    d = bears_display.BearsDisplay(MagicMock())
    assert d.nfl_team.slug == 'bears'
    assert d.PRIMARY == (11, 22, 42) and d.ACCENT == (200, 56, 3)
    assert bears_display.celebration_message(1) == 'BEARS SCORE!'
    d.manager = MagicMock()
    d._draw_sweater_header()
    args = d.manager.draw_text.call_args.args
    assert args[1] == 15 and args[4] == 'CHICAGO BEARS', args
print('Bears defaults byte-identical: OK')
EOF
```
Expected: `Bears defaults byte-identical: OK`.

- [ ] **Step 4: Commit anything the gate fixed**

Only if Steps 1-3 required changes:
```bash
git add -A && git commit -m "fix: full-suite gate fixes for NFL team support"
```

---

## Self-Review Notes (already applied)

- Spec §1 → Task 1; §2 (`bears_display.py` + logos + fetch script) → Tasks 2-3; §2 (NFL news) → Task 4; §3 (admin) → Task 5; §4 (testing gates) → distributed per task + Task 6.
- The admin JS listener change required by the spec ("stops unchecking `enable_bears`/`enable_bears_news`") falls out of Task 1's `NON_DEFAULT_OFF_KEYS` shrink because the JS iterates the injected tuple; Task 5's `test_admin_page_non_default_off_keys_is_clock_only` pins it.
- `extract_situation`'s `possession` sentinel changes `'bears'` → `'team'`; the only consumer (`_draw_live_content`) and the only tests (`test_core_logic.py` ~507-515) are both updated in Task 3.
- Logo pixel positions (score row: 14x14 at x=7/x=75, score text at x=24/x=56; card: 18x18 at x=12/x=66) are starting points per the spec — expect on-hardware iteration with the user afterward.

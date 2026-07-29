# Multi-Team Support (Cubs + Cardinals) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user pick an MLB team (Cubs or Cardinals) in the admin panel and have the whole board — schedule, live games, colors, logos, text, facts, history, news, celebration — rebrand to that team, while reorganizing the bloated admin Display Config tab into collapsible sections.

**Architecture:** A new `teams.py` module holds a frozen `TeamPack` dataclass and a `TEAMS` dict with complete Cubs and Cardinals packs. `get_active_team()` resolves the `"team"` key from user config (default `cubs`). All hardcoded Cubs references (team ID 112, `CUBS_BLUE`, `cubs.png`, `marquee.png`, `W.gif`, "CHICAGO CUBS") migrate to the active pack. The admin page gains a Team section and collapsible `<details>` sections.

**Tech Stack:** Python 3.9+ (Raspberry Pi), Flask (admin panel, single-file HTML template in `wifi_config_server.py`), PIL/Pillow, MLB-StatsAPI, pytest with `rgbmatrix` mocked via `tests/conftest.py`.

**Spec:** `docs/superpowers/specs/2026-07-29-multi-team-support-design.md`

## Global Constraints

- Existing config keys KEEP their names (`enable_cubs_facts`, `enable_cubs_news`, `enable_cubs_history`, `scroll_speed_cubs_facts`, `scroll_speed_cubs_news`) — they now mean "team facts/news/history". Only UI labels become team-generic. Renaming keys would break every deployed board.
- Missing or unknown `"team"` value always falls back to the Cubs pack. Existing configs must behave exactly as today.
- Cardinals identity values (copy verbatim): MLB team ID `138`, name `St. Louis Cardinals`, abbrev `STL`, matchup text `ST LOUIS CARDINALS`, primary color `(196, 30, 58)`, secondary `(12, 35, 64)`. Cubs: ID `112`, abbrev `CHC`, matchup `CHICAGO CUBS`, primary `(0, 51, 102)`, secondary `(204, 52, 51)`.
- `Colors.YELLOW` stays the shared accent color everywhere.
- Never crash on missing assets: preserve the existing try/except + placeholder-image patterns.
- Match existing code style: `from __future__ import annotations`, type hints, module docstrings.
- No new pip dependencies.
- Every changed `.py` file must pass `python3 -m py_compile <file>` (the nightly auto-updater's deploy gate).
- Run `python3 -m pytest tests/ -v` before every commit; all tests green.
- Commit messages end with: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- Team change applies after reboot — do NOT add live theme switching.
- The Bears displays, Wrigley clock: stay available for all teams as toggles; they default OFF when the active team is not the Cubs (only when the user has not explicitly set them).

---

### Task 1: `teams.py` team pack module + config validator support

**Files:**
- Create: `teams.py`
- Create: `tests/test_teams.py`
- Modify: `config_validator.py:34-38` (OPTIONAL_FIELDS) and add a team check in `validate_optional_fields` or a new method wired into `validate_all`

**Interfaces:**
- Consumes: `scoreboard_config.RGBColor`, `scoreboard_config.load_user_config`
- Produces (later tasks rely on these exact names):
  - `teams.TeamPack` — frozen dataclass, fields listed below
  - `teams.TEAMS: dict[str, TeamPack]` — keys `'cubs'`, `'cardinals'`
  - `teams.DEFAULT_TEAM_SLUG: str = 'cubs'`
  - `teams.NON_DEFAULT_OFF_KEYS: tuple[str, ...] = ('enable_bears', 'enable_bears_news', 'enable_clock')`
  - `teams.get_active_team(config: dict | None = None) -> TeamPack` — `config=None` means "read `load_user_config()`"
  - `teams.apply_team_defaults(defaults: dict, user_config: dict) -> dict` — returns a copy of `defaults` where each `NON_DEFAULT_OFF_KEYS` key is set `False` when `user_config` selects a non-Cubs team AND the user config does not explicitly set that key
  - `teams.data_path_candidates(basename: str) -> list[str]` — `['./<basename>', '/home/pi/<basename>']`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_teams.py`:

```python
"""Tests for the team pack module"""

from teams import (
    TEAMS, DEFAULT_TEAM_SLUG, NON_DEFAULT_OFF_KEYS,
    get_active_team, apply_team_defaults, data_path_candidates,
)


class TestTeamResolution:
    def test_default_is_cubs_when_config_empty(self):
        assert get_active_team({}).slug == 'cubs'

    def test_explicit_cubs(self):
        assert get_active_team({'team': 'cubs'}).mlb_team_id == 112

    def test_explicit_cardinals(self):
        pack = get_active_team({'team': 'cardinals'})
        assert pack.mlb_team_id == 138
        assert pack.abbrev == 'STL'

    def test_unknown_slug_falls_back_to_cubs(self):
        assert get_active_team({'team': 'yankees'}).slug == 'cubs'

    def test_none_config_uses_load_user_config(self, monkeypatch):
        import teams
        monkeypatch.setattr(teams, 'load_user_config',
                            lambda: {'team': 'cardinals'})
        assert get_active_team().slug == 'cardinals'


class TestPackContents:
    def test_both_packs_present(self):
        assert set(TEAMS) == {'cubs', 'cardinals'}

    def test_cubs_pack_values(self):
        cubs = TEAMS['cubs']
        assert cubs.matchup_name == 'CHICAGO CUBS'
        assert cubs.primary_color == (0, 51, 102)
        assert cubs.logo_path == './logos/cubs.png'
        assert cubs.marquee_path == './marquee.png'
        assert cubs.celebration_path == './W.gif'

    def test_cardinals_pack_values(self):
        stl = TEAMS['cardinals']
        assert stl.name == 'St. Louis Cardinals'
        assert stl.matchup_name == 'ST LOUIS CARDINALS'
        assert stl.primary_color == (196, 30, 58)
        assert stl.secondary_color == (12, 35, 64)
        assert stl.news_rss_url == (
            'https://www.mlb.com/cardinals/feeds/news/rss.xml')

    def test_slug_matches_dict_key(self):
        for slug, pack in TEAMS.items():
            assert pack.slug == slug


class TestTeamDefaults:
    DEFAULTS = {'enable_bears': True, 'enable_bears_news': True,
                'enable_clock': True, 'enable_weather': True}

    def test_cubs_leaves_defaults_alone(self):
        out = apply_team_defaults(self.DEFAULTS, {'team': 'cubs'})
        assert out == self.DEFAULTS

    def test_missing_team_leaves_defaults_alone(self):
        out = apply_team_defaults(self.DEFAULTS, {})
        assert out == self.DEFAULTS

    def test_cardinals_turns_off_chicago_content(self):
        out = apply_team_defaults(self.DEFAULTS, {'team': 'cardinals'})
        assert out['enable_bears'] is False
        assert out['enable_bears_news'] is False
        assert out['enable_clock'] is False
        assert out['enable_weather'] is True

    def test_explicit_user_choice_wins(self):
        user = {'team': 'cardinals', 'enable_bears': True}
        out = apply_team_defaults(self.DEFAULTS, user)
        assert out['enable_bears'] is True

    def test_input_dict_not_mutated(self):
        snapshot = dict(self.DEFAULTS)
        apply_team_defaults(self.DEFAULTS, {'team': 'cardinals'})
        assert self.DEFAULTS == snapshot


def test_data_path_candidates():
    assert data_path_candidates('cubs_facts.json') == [
        './cubs_facts.json', '/home/pi/cubs_facts.json']
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_teams.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'teams'`

- [ ] **Step 3: Write `teams.py`**

```python
"""Team packs: per-team identity, colors, assets, and content sources.

The active team is selected by the "team" key in /home/pi/config.json
(written by the admin panel). Missing or unknown values fall back to the
Cubs so existing boards behave exactly as before.
"""

from __future__ import annotations

from dataclasses import dataclass

from scoreboard_config import RGBColor, load_user_config

DEFAULT_TEAM_SLUG = 'cubs'

# Content that only makes sense for a Chicago board; defaults to off for
# other teams unless the user explicitly re-enables it in the admin panel.
NON_DEFAULT_OFF_KEYS: tuple[str, ...] = (
    'enable_bears', 'enable_bears_news', 'enable_clock')


@dataclass(frozen=True)
class TeamPack:
    """Everything the display needs to brand itself for one MLB team"""
    slug: str
    mlb_team_id: int
    name: str
    short_name: str
    abbrev: str
    matchup_name: str          # "X VS OPPONENT" pre-game text
    primary_color: RGBColor
    secondary_color: RGBColor
    logo_path: str
    marquee_path: str
    celebration_path: str      # animated GIF shown after a win
    facts_basename: str        # resolved via data_path_candidates()
    history_basename: str      # resolved via data_path_candidates()
    news_rss_url: str


TEAMS: dict[str, TeamPack] = {
    'cubs': TeamPack(
        slug='cubs',
        mlb_team_id=112,
        name='Chicago Cubs',
        short_name='Cubs',
        abbrev='CHC',
        matchup_name='CHICAGO CUBS',
        primary_color=(0, 51, 102),
        secondary_color=(204, 52, 51),
        logo_path='./logos/cubs.png',
        marquee_path='./marquee.png',
        celebration_path='./W.gif',
        facts_basename='cubs_facts.json',
        history_basename='cubs_history.json',
        news_rss_url='https://www.mlb.com/cubs/feeds/news/rss.xml',
    ),
    'cardinals': TeamPack(
        slug='cardinals',
        mlb_team_id=138,
        name='St. Louis Cardinals',
        short_name='Cardinals',
        abbrev='STL',
        matchup_name='ST LOUIS CARDINALS',
        primary_color=(196, 30, 58),
        secondary_color=(12, 35, 64),
        logo_path='./logos/STL.png',
        marquee_path='./cardinals_marquee.png',
        celebration_path='./cards_win.gif',
        facts_basename='cardinals_facts.json',
        history_basename='cardinals_history.json',
        news_rss_url='https://www.mlb.com/cardinals/feeds/news/rss.xml',
    ),
}


def get_active_team(config: dict | None = None) -> TeamPack:
    """Resolve the active team pack from config (or the user config file)"""
    if config is None:
        config = load_user_config()
    slug = config.get('team', DEFAULT_TEAM_SLUG)
    return TEAMS.get(slug, TEAMS[DEFAULT_TEAM_SLUG])


def apply_team_defaults(defaults: dict, user_config: dict) -> dict:
    """Return a copy of defaults adjusted for the active team.

    Chicago-specific content defaults to off for non-Cubs teams, but an
    explicit user setting always wins.
    """
    adjusted = dict(defaults)
    if user_config.get('team', DEFAULT_TEAM_SLUG) != DEFAULT_TEAM_SLUG:
        for key in NON_DEFAULT_OFF_KEYS:
            if key not in user_config:
                adjusted[key] = False
    return adjusted


def data_path_candidates(basename: str) -> list[str]:
    """Lookup locations for team data files, repo dir first then Pi home"""
    return [f'./{basename}', f'/home/pi/{basename}']
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_teams.py -v`
Expected: all PASS

- [ ] **Step 5: Add `team` to the config validator**

In `config_validator.py`, add to `OPTIONAL_FIELDS`:

```python
    OPTIONAL_FIELDS: list[tuple[str, str]] = [
        ("zip_code", "ZIP code for weather display"),
        ("weather_api_key", "OpenWeatherMap API key for weather display"),
        ("team", "Active team pack slug (cubs, cardinals)"),
    ]
```

Then add this method to `ConfigValidator` and call it from `validate_all()` (append its result to the results list alongside the other checks):

```python
    def validate_team(self) -> ValidationResult:
        """Validate the team slug, if present, names a known team pack"""
        from teams import TEAMS, DEFAULT_TEAM_SLUG
        slug = self.config.get("team", DEFAULT_TEAM_SLUG)
        if slug in TEAMS:
            return ValidationResult(
                is_valid=True, field="team",
                message=f"Team pack: {slug}", is_required=False)
        return ValidationResult(
            is_valid=False, field="team",
            message=(f"Unknown team '{slug}' - will fall back to "
                     f"{DEFAULT_TEAM_SLUG}. Known: {', '.join(TEAMS)}"),
            is_required=False)
```

(Read `validate_all()` first to match how it aggregates results — follow the same pattern used for `validate_weather_config()`.)

- [ ] **Step 6: Add validator tests**

Append to `tests/test_teams.py`:

```python
class TestConfigValidatorTeam:
    def _validator_with(self, config):
        from config_validator import ConfigValidator
        v = ConfigValidator()
        v.config = config
        return v

    def test_known_team_valid(self):
        result = self._validator_with({'team': 'cardinals'}).validate_team()
        assert result.is_valid

    def test_missing_team_valid(self):
        result = self._validator_with({}).validate_team()
        assert result.is_valid

    def test_unknown_team_flagged_not_required(self):
        result = self._validator_with({'team': 'mets'}).validate_team()
        assert not result.is_valid
        assert not result.is_required
```

- [ ] **Step 7: Run full test suite and py_compile**

Run: `python3 -m pytest tests/ -v && python3 -m py_compile teams.py config_validator.py`
Expected: all PASS, no compile errors

- [ ] **Step 8: Commit**

```bash
git add teams.py tests/test_teams.py config_validator.py
git commit -m "Add team pack module with Cubs and Cardinals packs

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Cardinals facts and history data files

**Files:**
- Create: `cardinals_facts.json`
- Create: `cardinals_history.json`
- Create: `tests/test_team_data.py`

**Interfaces:**
- Consumes: `teams.TEAMS` (for basenames)
- Produces: the two JSON files that Task 6's loaders and Task 5's history display read. Formats must exactly match the Cubs files:
  - facts: `{"facts": ["FACT ONE", "FACT TWO", ...]}` — flat list of uppercase strings
  - history: `{"MM-DD": [{"year": 1964, "text": "UPPERCASE STORY"}], ...}`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_team_data.py`:

```python
"""Schema tests for per-team data files"""

import json
import re

import pytest

from teams import TEAMS


def _load(path):
    with open(path) as f:
        return json.load(f)


@pytest.mark.parametrize('slug', sorted(TEAMS))
class TestFactsFiles:
    def test_facts_parse_and_schema(self, slug):
        data = _load(f'./{TEAMS[slug].facts_basename}')
        assert isinstance(data['facts'], list)
        assert len(data['facts']) >= 150
        for fact in data['facts']:
            assert isinstance(fact, str) and fact.strip()

    def test_facts_display_safe(self, slug):
        # LED fonts are uppercase-friendly ASCII; keep facts scrollable
        for fact in _load(f'./{TEAMS[slug].facts_basename}')['facts']:
            assert fact == fact.upper()
            assert all(ord(c) < 128 for c in fact)


@pytest.mark.parametrize('slug', sorted(TEAMS))
class TestHistoryFiles:
    def test_history_parse_and_schema(self, slug):
        data = _load(f'./{TEAMS[slug].history_basename}')
        assert len(data) >= 25
        for date_key, entries in data.items():
            assert re.fullmatch(r'\d{2}-\d{2}', date_key)
            month, day = int(date_key[:2]), int(date_key[3:])
            assert 1 <= month <= 12 and 1 <= day <= 31
            for entry in entries:
                assert isinstance(entry['year'], int)
                assert 1876 <= entry['year'] <= 2026
                assert entry['text'] == entry['text'].upper()
                assert all(ord(c) < 128 for c in entry['text'])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_team_data.py -v`
Expected: cubs cases PASS (existing files), cardinals cases FAIL with `FileNotFoundError`. If any CUBS case fails, the test is stricter than the real data — loosen the test to match the existing Cubs files (they are the schema authority), then re-run.

- [ ] **Step 3: Author `cardinals_facts.json`**

Write `{"facts": [...]}` with **at least 200** Cardinals facts, all uppercase ASCII, one sentence each, in the same voice as `cubs_facts.json` (read it first for tone/length). Cover at minimum:

- Franchise: 11 World Series titles (most in the NL), founded 1882 as the Brown Stockings, "the birds on the bat," Busch Stadium I/II/III, Sportsman's Park
- Legends: Stan Musial, Bob Gibson, Lou Brock, Ozzie Smith, Red Schoendienst, Rogers Hornsby, Dizzy Dean, Enos Slaughter, Ken Boyer, Bruce Sutter, Whitey Herzog, Tony La Russa, Albert Pujols, Yadier Molina, Adam Wainwright, Jim Edmonds, Scott Rolen, Ted Simmons, Mark McGwire, Willie McGee, Vince Coleman, Curt Flood, Joe Medwick, Johnny Mize
- Moments: 1926/1931/1934 (Gashouse Gang)/1942/1944/1946/1964/1967/1982/2006/2011 World Series wins; Gibson's 1.12 ERA in 1968; Musial's 3,630 hits split evenly home/road; Brock's 938 steals; Ozzie's "Go crazy, folks!" 1985 NLCS homer; David Freese Game 6 2011; Slaughter's Mad Dash 1946; Whiteyball; Pujols' 700th HR; the 2004/2013 pennants
- Culture: "The Cardinal Way," the best fans in baseball, KMOX broadcasts, Jack Buck ("That's a winner!"), Mike Shannon, Fredbird, the Clydesdales, the Cubs-Cardinals rivalry, the Arch
- Example entries (use this exact style):

```json
{
  "facts": [
    "CARDINALS HAVE WON 11 WORLD SERIES - MOST IN THE NATIONAL LEAGUE",
    "STAN THE MAN MUSIAL COLLECTED 3,630 HITS - 1,815 AT HOME, 1,815 ON THE ROAD",
    "BOB GIBSON POSTED A 1.12 ERA IN 1968 - THE YEAR OF THE PITCHER",
    "OZZIE SMITH - THE WIZARD - WON 13 STRAIGHT GOLD GLOVES AT SHORTSTOP",
    "GO CRAZY FOLKS, GO CRAZY! - JACK BUCK, NLCS 1985",
    "DAVID FREESE'S GAME 6 WALK-OFF SAVED THE 2011 WORLD SERIES",
    "LOU BROCK STOLE 938 BASES AFTER ARRIVING FROM THE CUBS IN 1964",
    "THE GASHOUSE GANG WON THE 1934 WORLD SERIES",
    "YADIER MOLINA CAUGHT MORE GAMES THAN ANY CARDINAL IN HISTORY",
    "THAT'S A WINNER! - JACK BUCK'S SIGNATURE CALL"
  ]
}
```

Verify facts are accurate — do not invent statistics. If unsure of a number, phrase the fact without it.

- [ ] **Step 4: Author `cardinals_history.json`**

Write **at least 30 dated entries** in the `cubs_history.json` format (date-keyed, entries uppercase). Cover birthdays and deaths of the legends above, World Series clinchers (e.g., `10-28`: 2011 Game 7; `10-27`: 2006 clincher), Musial's five-homer doubleheader (`05-02`, 1954), Gibson's 17-strikeout World Series game (`10-02`, 1968), Brock trade (`06-15`, 1964 — the Cardinals' side of the Brock-for-Broglio deal), Pujols' 3,000th hit and 700th homer, Fernando Tatis' two grand slams in one inning (`04-23`, 1999), Mark Whiten's 4-homer game (`09-07`, 1993). Same accuracy rule: verify or omit.

Example format:

```json
{
  "05-02": [{"year": 1954, "text": "STAN MUSIAL HITS FIVE HOME RUNS IN A DOUBLEHEADER AT BUSCH STADIUM"}],
  "09-07": [{"year": 1993, "text": "MARK WHITEN CRUSHES FOUR HOME RUNS AND DRIVES IN 12 AGAINST THE REDS"}]
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_team_data.py -v`
Expected: all PASS (both teams)

- [ ] **Step 6: Commit**

```bash
git add cardinals_facts.json cardinals_history.json tests/test_team_data.py
git commit -m "Add Cardinals facts and history data files

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Cardinals art assets (marquee + win celebration)

**Files:**
- Create: `dev/generate_cardinals_assets.py` (generator script, committed for future iteration)
- Create: `cardinals_marquee.png` (96x35, matching `marquee.png` dimensions)
- Create: `cards_win.gif` (96x48 native, animated)
- Create: `tests/test_pack_completeness.py`

**Interfaces:**
- Consumes: `teams.TEAMS` path fields
- Produces: the two asset files referenced by the cardinals pack. `cards_win.gif` must be a multi-frame GIF (the display code iterates frames with `seek()` and reads `info['duration']`).

- [ ] **Step 1: Write the failing pack-completeness test**

Create `tests/test_pack_completeness.py`:

```python
"""Every path a team pack references must exist in the repo"""

import os

import pytest
from PIL import Image

from teams import TEAMS


@pytest.mark.parametrize('slug', sorted(TEAMS))
def test_all_pack_paths_exist(slug):
    pack = TEAMS[slug]
    for path in (pack.logo_path, pack.marquee_path, pack.celebration_path,
                 f'./{pack.facts_basename}', f'./{pack.history_basename}'):
        assert os.path.exists(path), f'{slug}: missing {path}'


@pytest.mark.parametrize('slug', sorted(TEAMS))
def test_celebration_gif_is_animated(slug):
    gif = Image.open(TEAMS[slug].celebration_path)
    assert getattr(gif, 'n_frames', 1) > 1
    assert gif.info.get('duration', 0) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_pack_completeness.py -v`
Expected: cubs PASSes, cardinals FAILs on `cardinals_marquee.png`

- [ ] **Step 3: Write the asset generator**

Create `dev/generate_cardinals_assets.py`:

```python
"""Generate Cardinals marquee and win-celebration assets.

Run from the repo root:  python3 dev/generate_cardinals_assets.py
Pixel art is expected to be iterated on against the real matrix; keep this
script as the source of truth and regenerate rather than hand-editing.
"""

from PIL import Image, ImageDraw

CARDINAL_RED = (196, 30, 58)
CARDINAL_NAVY = (12, 35, 64)
WHITE = (255, 255, 255)
YELLOW = (255, 223, 0)

# 3x5 pixel font for the letters we need (1 = lit pixel)
GLYPHS = {
    'A': ['010', '101', '111', '101', '101'],
    'C': ['011', '100', '100', '100', '011'],
    'D': ['110', '101', '101', '101', '110'],
    'I': ['111', '010', '010', '010', '111'],
    'L': ['100', '100', '100', '100', '111'],
    'N': ['101', '111', '111', '111', '101'],
    'R': ['110', '101', '110', '101', '101'],
    'S': ['011', '100', '010', '001', '110'],
    'T': ['111', '010', '010', '010', '010'],
    'U': ['101', '101', '101', '101', '111'],
    'W': ['101', '101', '111', '111', '101'],
    '!': ['010', '010', '010', '000', '010'],
    ' ': ['000', '000', '000', '000', '000'],
}


def draw_word(draw, word, x, y, color, scale=1):
    for ch in word:
        glyph = GLYPHS[ch]
        for row, bits in enumerate(glyph):
            for col, bit in enumerate(bits):
                if bit == '1':
                    x0 = x + col * scale
                    y0 = y + row * scale
                    draw.rectangle(
                        [x0, y0, x0 + scale - 1, y0 + scale - 1], fill=color)
        x += (3 + 1) * scale
    return x


def word_width(word, scale=1):
    return (len(word) * 4 - 1) * scale


def make_marquee():
    """96x35 marquee sign: navy field, red sign face, bulb border"""
    img = Image.new('RGBA', (96, 35), CARDINAL_NAVY + (255,))
    d = ImageDraw.Draw(img)
    # Sign face
    d.rectangle([4, 4, 91, 30], fill=CARDINAL_RED)
    d.rectangle([4, 4, 91, 30], outline=WHITE)
    # Bulbs around the border (every 4th pixel)
    for x in range(6, 90, 4):
        d.point((x, 2), fill=YELLOW)
        d.point((x, 32), fill=YELLOW)
    for y in range(6, 30, 4):
        d.point((2, y), fill=YELLOW)
        d.point((93, y), fill=YELLOW)
    # "ST LOUIS" over "CARDINALS", centered on the sign face
    top = 'ST LOUIS'
    bottom = 'CARDINALS'
    d_top_x = (96 - word_width(top)) // 2
    d_bot_x = (96 - word_width(bottom, 2)) // 2
    draw_word(d, top, d_top_x, 8, WHITE)
    draw_word(d, bottom, d_bot_x, 16, WHITE, scale=2)
    img.save('cardinals_marquee.png')


def make_celebration():
    """96x48 animated 'CARDS WIN!' with chasing border bulbs"""
    frames = []
    for phase in range(4):
        img = Image.new('RGB', (96, 48), CARDINAL_RED)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, 95, 47], outline=CARDINAL_NAVY)
        # Chasing bulbs: lit position rotates with the frame phase
        idx = 0
        for x in range(2, 94, 4):
            for y in (2, 45):
                d.point((x, y),
                        fill=YELLOW if idx % 4 == phase else CARDINAL_NAVY)
                idx += 1
        for y in range(6, 42, 4):
            for x in (2, 93):
                d.point((x, y),
                        fill=YELLOW if idx % 4 == phase else CARDINAL_NAVY)
                idx += 1
        cards = 'CARDS'
        win = 'WIN!'
        draw_word(d, cards, (96 - word_width(cards, 3)) // 2, 6, WHITE, 3)
        color = YELLOW if phase % 2 else WHITE
        draw_word(d, win, (96 - word_width(win, 3)) // 2, 26, color, 3)
        frames.append(img)
    frames[0].save('cards_win.gif', save_all=True,
                   append_images=frames[1:], duration=200, loop=0)


if __name__ == '__main__':
    make_marquee()
    make_celebration()
    print('Wrote cardinals_marquee.png and cards_win.gif')
```

- [ ] **Step 4: Generate the assets and eyeball them**

Run: `python3 dev/generate_cardinals_assets.py`
Then open both files (`open cardinals_marquee.png cards_win.gif` on macOS) and confirm: text legible, centered, no overflow past the canvas. Fix the script (spacing/scale), regenerate, re-check. These will still get pixel-level iteration on the real matrix later — legible and centered is the bar here.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_pack_completeness.py tests/ -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add dev/generate_cardinals_assets.py cardinals_marquee.png cards_win.gif tests/test_pack_completeness.py
git commit -m "Add Cardinals marquee and win celebration assets

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Migrate core game code to the active team pack

**Files:**
- Modify: `scoreboard_manager.py` (lines ~195-320: `opp_abv` CHC check, `cubs.png`, `marquee.png`, schedule team IDs, pitcher strings; also the `game_images['cubs']` dict key)
- Modify: `live_game_handler.py` (lines 51, 123, 265, 709, 741, 795: team ID checks, `game_images['cubs']` uses, `CUBS_BLUE`, `W.gif`)
- Modify: `game_state_handler.py` (lines 70, 496: matchup text, `CUBS_BLUE` fill)
- Modify: `scoreboard_config.py` (remove `TeamConfig.CUBS_TEAM_ID` only at the END of Task 5, once no call sites remain)
- Test: existing suite (`tests/test_core_logic.py`, `tests/test_features.py`, `tests/test_bugfixes.py` likely reference Cubs behavior — update as needed)

**Interfaces:**
- Consumes: `teams.get_active_team() -> TeamPack` (call it at each use site or store `self.team = get_active_team()` in `__init__`; prefer an instance attribute set once in each class's `__init__` — team only changes with a reboot)
- Produces: `game_images` dict key renamed `'cubs'` → `'team'` (Task 5 has no dependency on this, but any future code must use `'team'`)

- [ ] **Step 1: Survey every call site**

Run and read the output of:

```bash
grep -n "CUBS_TEAM_ID\|CUBS_BLUE\|'CHC'\|cubs.png\|marquee.png\|W.gif\|CHICAGO CUBS\|Cubs Pitcher\|game_images\['cubs'\]" scoreboard_manager.py live_game_handler.py game_state_handler.py
```

The migration below covers the known sites; if the grep reveals more, migrate them the same way.

- [ ] **Step 2: Migrate `scoreboard_manager.py`**

Add import and instance attribute:

```python
from teams import get_active_team
```

In `ScoreboardManager.__init__` (find it; add near other attribute setup):

```python
        self.team = get_active_team()
```

Then replace, using `self.team`:

- `if team_data['abbreviation'] != 'CHC':` → `if team_data['abbreviation'] != self.team.abbrev:`
- `cubs_logo_path = './logos/cubs.png'` → `team_logo_path = self.team.logo_path` (rename the local variable and the warning message text to "Team logo")
- `self.game_images['cubs'] = ...` → `self.game_images['team'] = ...` (both the load and the placeholder fallback, and in `_create_fallback_images()`)
- `marquee_path = './marquee.png'` → `marquee_path = self.team.marquee_path`
- both `team=TeamConfig.CUBS_TEAM_ID` schedule calls → `team=self.team.mlb_team_id`
- `if game_data[game_index]['home_id'] == TeamConfig.CUBS_TEAM_ID:` → `== self.team.mlb_team_id`
- `f'Cubs Pitcher: {home_pitcher}    {away_team} Pitcher: {away_pitcher}'` → `f'{self.team.short_name} Pitcher: {home_pitcher}    {away_team} Pitcher: {away_pitcher}'` (and the away-side twin below it)
- Remove the now-unused `TeamConfig` import ONLY if nothing else in the file uses it.

- [ ] **Step 3: Migrate `live_game_handler.py`**

Same import; in `LiveGameHandler.__init__` add `self.team = get_active_team()`. Replace:

- line 51 and 709: `== TeamConfig.CUBS_TEAM_ID` → `== self.team.mlb_team_id` (local variable names like `cubs_are_home` may stay — renaming them is optional; if renaming, do it consistently within the file)
- lines 123 and 741: `game_images['cubs']` → `game_images['team']`
- line 265: `Colors.CUBS_BLUE` → `self.team.primary_color`
- line 795: `w_flag = Image.open('./W.gif')` → `w_flag = Image.open(self.team.celebration_path)` and update the two error-message strings mentioning W.gif to use `self.team.celebration_path`

- [ ] **Step 4: Migrate `game_state_handler.py`**

Same import; `self.team = get_active_team()` in `__init__`. Replace:

- line 70: `matchup_text: str = f"CHICAGO CUBS VS {opponent_name.upper()}"` → `matchup_text: str = f"{self.team.matchup_name} VS {opponent_name.upper()}"`
- line 496: `self.manager.fill_canvas(*Colors.CUBS_BLUE)` → `self.manager.fill_canvas(*self.team.primary_color)`

- [ ] **Step 5: Run the test suite; fix fallout**

Run: `python3 -m pytest tests/ -v`

Expected: some existing tests may fail if they instantiate these classes (conftest mocks rgbmatrix, and `get_active_team()` reads `/home/pi/config.json` which won't exist on dev machines — `load_user_config()` returns `{}` then, resolving to cubs, so behavior is unchanged). Fix any test that asserts on the old `game_images['cubs']` key or 'CHC' literal. Do NOT weaken assertions — update them to the new names.

- [ ] **Step 6: py_compile and commit**

```bash
python3 -m py_compile scoreboard_manager.py live_game_handler.py game_state_handler.py
git add scoreboard_manager.py live_game_handler.py game_state_handler.py tests/
git commit -m "Migrate core game display to active team pack

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Migrate auxiliary displays + team-generic history display

**Files:**
- Modify: `cubs_history_display.py` → team-generic (keep the filename; rename the class)
- Modify: `playoff_race_display.py` (lines 56, 183, 260)
- Modify: `spring_training_display.py` (lines 28, 97, 175)
- Modify: `allstar_display.py` (lines 184, 215, 843, 846)
- Modify: `setup_display.py` (line 81)
- Modify: `main.py` (docstrings only if they say "Cubs" — leave; check for `TeamConfig` use)
- Modify: `off_season_handler.py` (import + instantiation of the history display, lines 25, 51)
- Modify: `scoreboard_config.py` (remove `TeamConfig.CUBS_TEAM_ID` once call sites are gone)
- Test: `tests/test_teams.py` (add history-display test), existing suites

**Interfaces:**
- Consumes: `teams.get_active_team`, `teams.data_path_candidates`
- Produces: `TeamHistoryDisplay` class in `cubs_history_display.py` with the same public API as before: `__init__(scoreboard_manager)`, `display_history(duration: int = 120) -> bool`

- [ ] **Step 1: Make the history display team-generic**

In `cubs_history_display.py`:

- Module docstring → `"""Today in team history - date-keyed moments from franchise history"""`
- Delete `HISTORY_PATHS` and `CUBS_BLUE` constants (`MARQUEE_RED` and `STORY_WHITE` stay)
- Rename class `CubsHistoryDisplay` → `TeamHistoryDisplay`
- `__init__` becomes:

```python
    def __init__(self, scoreboard_manager: ScoreboardManager) -> None:
        self.manager = scoreboard_manager
        self.team = get_active_team()
        self.history: dict[str, list[dict[str, Any]]] = self._load_history()

    def _load_history(self) -> dict[str, list[dict[str, Any]]]:
        for path in data_path_candidates(self.team.history_basename):
            try:
                with open(path) as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
        print(f"{self.team.history_basename} not found")
        return {}
```

(note: `_load_history` is no longer `@staticmethod`), with import `from teams import get_active_team, data_path_candidates`.

- In `_draw_entry_frame`: background color `CUBS_BLUE` → `self.team.primary_color`; title `'CUBS HISTORY'` → `f'{self.team.short_name.upper()} HISTORY'`
- In `display_history`: the two print strings "Cubs history" → f-strings using `self.team.short_name`

- [ ] **Step 2: Update the history display call sites**

In `off_season_handler.py`:
- line 25: `from cubs_history_display import CubsHistoryDisplay` → `from cubs_history_display import TeamHistoryDisplay`
- line 51: `self.cubs_history_display: CubsHistoryDisplay = CubsHistoryDisplay(scoreboard_manager)` → `self.cubs_history_display: TeamHistoryDisplay = TeamHistoryDisplay(scoreboard_manager)` (attribute name and the `enable_cubs_history` config key stay — Global Constraints)

Run `grep -rn "CubsHistoryDisplay" --include="*.py" .` to catch any other site (including tests).

- [ ] **Step 3: Migrate the aux displays**

Each file: add `from teams import get_active_team`, set `self.team = get_active_team()` in `__init__` (or a local `team = get_active_team()` where there's no class), then:

- `playoff_race_display.py:56`: `== TeamConfig.CUBS_TEAM_ID` → `== self.team.mlb_team_id`; lines 183, 260: `Colors.CUBS_BLUE` → `self.team.primary_color`
- `spring_training_display.py:28`: `self.CUBS_BLUE: RGBColor = Colors.CUBS_BLUE` → `self.CUBS_BLUE: RGBColor = self.team.primary_color` (then rename attribute `CUBS_BLUE` → `TEAM_COLOR` and update its uses, line 175 included); line 97 `team=TeamConfig.CUBS_TEAM_ID` → `team=self.team.mlb_team_id`
- `allstar_display.py:184, 215`: `== TeamConfig.CUBS_TEAM_ID` → `== self.team.mlb_team_id` (dict key `'batter_is_cub'` may stay); lines 843, 846: `Colors.CUBS_BLUE` → `self.team.primary_color`
- `setup_display.py:81`: `fill=Colors.CUBS_BLUE` → `fill=get_active_team().primary_color` (setup display has no game context; a module-level call is fine)

- [ ] **Step 4: Remove `TeamConfig.CUBS_TEAM_ID`**

Run: `grep -rn "CUBS_TEAM_ID" --include="*.py" .` — expect hits only in `scoreboard_config.py` and possibly tests. Remove the constant from `TeamConfig` (keep the class and league IDs), update any test that referenced it to use `TEAMS['cubs'].mlb_team_id`.

Keep `Colors.CUBS_BLUE` — remaining uses (if any) are deliberate palette choices; run `grep -rn "CUBS_BLUE" --include="*.py" .` and confirm each survivor is a neutral-palette use, not team theming. Weather/bible/newsmax/stock displays using it as a generic dark blue may keep it.

- [ ] **Step 5: Add a history display test**

Append to `tests/test_teams.py`:

```python
class TestTeamHistoryDisplay:
    def test_loads_active_team_history(self, monkeypatch):
        import teams
        monkeypatch.setattr(teams, 'load_user_config',
                            lambda: {'team': 'cardinals'})
        from cubs_history_display import TeamHistoryDisplay
        from unittest.mock import MagicMock
        display = TeamHistoryDisplay(MagicMock())
        assert display.team.slug == 'cardinals'
        assert display.history  # cardinals_history.json parsed
```

- [ ] **Step 6: Run everything, compile, commit**

```bash
python3 -m pytest tests/ -v
python3 -m py_compile cubs_history_display.py playoff_race_display.py spring_training_display.py allstar_display.py setup_display.py off_season_handler.py scoreboard_config.py
git add -A
git commit -m "Migrate auxiliary displays to active team pack

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Migrate off-season content (facts, news, marquee, team defaults)

**Files:**
- Modify: `off_season_handler.py` (`__init__` config defaults ~line 150-200, `_load_cubs_facts` ~line 202, `_fetch_cubs_news_rss` ~line 229, marquee load line 124, default facts list)
- Test: `tests/test_teams.py` additions

**Interfaces:**
- Consumes: `teams.get_active_team`, `teams.apply_team_defaults`, `teams.data_path_candidates`, `scoreboard_config.load_user_config`
- Produces: nothing new for later tasks (method names `_load_cubs_facts` / `_fetch_cubs_news_rss` keep their names — internal, and the config keys they honor are frozen by Global Constraints)

- [ ] **Step 1: Set the team and apply team defaults**

In `OffSeasonHandler.__init__`, add `self.team = get_active_team()` before the config defaults dict is built. Where the handler merges defaults with the user config (the `default_config.update(load_user_config())` pattern near line 199), change to:

```python
        user_config = load_user_config()
        default_config = apply_team_defaults(default_config, user_config)
        default_config.update(user_config)
        return default_config
```

with imports `from teams import get_active_team, apply_team_defaults, data_path_candidates`.

- [ ] **Step 2: Team-generic facts loading**

Rewrite `_load_cubs_facts` (keep the method name):

```python
    def _load_cubs_facts(self) -> list[str]:
        """Load team facts from the active team pack's JSON file"""
        default_facts: list[str] = [
            f"GO {self.team.short_name.upper()}!",
            f"{self.team.name.upper()} BASEBALL",
        ]
        for facts_path in data_path_candidates(self.team.facts_basename):
            try:
                with open(facts_path, 'r') as f:
                    facts = json.load(f).get('facts', [])
                if facts:
                    print(f"Loaded {len(facts)} {self.team.short_name} "
                          f"facts from {facts_path}")
                    return facts
            except (OSError, json.JSONDecodeError) as e:
                continue
        print(f"{self.team.facts_basename} not found, using defaults")
        return default_facts
```

(This also upgrades the old single-path lookup to the standard two-path lookup — the repo copy now works on dev machines too.)

- [ ] **Step 3: Team RSS feed**

In `_fetch_cubs_news_rss`, replace the hardcoded feed list:

```python
        rss_feeds = [
            'https://www.espn.com/espn/rss/mlb/news',
            self.team.news_rss_url,
            'https://www.cbssports.com/rss/headlines/mlb/'
        ]
```

Update the surrounding print statements that say "Cubs news" to use `self.team.short_name`.

- [ ] **Step 4: Marquee image**

Line ~124: `marquee = Image.open('./marquee.png')` → `marquee = Image.open(self.team.marquee_path)`, and the warning print → `print(f"Warning: {self.team.marquee_path} not found")`.

- [ ] **Step 5: Tests**

Append to `tests/test_teams.py`:

```python
class TestOffSeasonTeamContent:
    def _handler(self, monkeypatch, team_slug):
        import teams
        monkeypatch.setattr(teams, 'load_user_config',
                            lambda: {'team': team_slug})
        import off_season_handler as osh
        monkeypatch.setattr(osh, 'load_user_config',
                            lambda: {'team': team_slug})
        from unittest.mock import MagicMock
        return osh.OffSeasonHandler(MagicMock())

    def test_cardinals_facts_loaded(self, monkeypatch):
        handler = self._handler(monkeypatch, 'cardinals')
        facts = handler._load_cubs_facts()
        assert len(facts) >= 150
        assert not any('CUBS' in f and 'CARDINALS' not in f
                       for f in facts[:20])

    def test_cardinals_defaults_disable_bears(self, monkeypatch):
        handler = self._handler(monkeypatch, 'cardinals')
        assert handler.config['enable_bears'] is False
        assert handler.config['enable_clock'] is False

    def test_cubs_defaults_keep_bears(self, monkeypatch):
        handler = self._handler(monkeypatch, 'cubs')
        assert handler.config['enable_bears'] is True
```

If `OffSeasonHandler.__init__` does network or heavy work that breaks under `MagicMock()`, read its `__init__` and monkeypatch the offending fetches (follow patterns in `tests/test_features.py`).

- [ ] **Step 6: Run, compile, commit**

```bash
python3 -m pytest tests/ -v && python3 -m py_compile off_season_handler.py
git add off_season_handler.py tests/test_teams.py
git commit -m "Load off-season facts, news, and marquee from active team pack

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Admin control audit

**Files:**
- Create: `docs/admin-config-audit.md`
- Possibly modify: `wifi_config_server.py` (fixes only — removals wait for user sign-off)

**Interfaces:**
- Consumes: nothing from other tasks
- Produces: the audit table that Task 8's restructure relies on (it must not carry dead controls into the new layout)

- [ ] **Step 1: Extract the four key inventories**

From `wifi_config_server.py`, build four lists:

1. HTML control IDs in the config tab: `grep -n 'id="' wifi_config_server.py | sed -n '/config-tab/,/system-tab/p'` — or read lines 572-930 and list every `<input>`/`<select>`/`<textarea>` id
2. Keys sent by `saveConfig()` (lines ~1286-1338)
3. Keys restored by the page-load JS (lines ~1036-1126)
4. Keys in the server-side `load_config()` defaults dict (lines ~100-190)

- [ ] **Step 2: Find the consumer for every key**

For each config key, find where the scoreboard reads it:

```bash
for key in display_mode enable_weather enable_bears enable_bears_news enable_pga enable_pga_news enable_pga_facts enable_cubs_facts enable_cubs_news enable_bible enable_bible_facts enable_newsmax enable_stocks enable_spring_training enable_playoff_race enable_flights enable_flight_radar enable_clock enable_cubs_history enable_sky enable_iss enable_celebrations flights_between_displays scroll_speed_bears scroll_speed_bears_news scroll_speed_pga scroll_speed_pga_news scroll_speed_pga_facts scroll_speed_cubs_facts scroll_speed_cubs_news scroll_speed_bible scroll_speed_bible_facts scroll_speed_newsmax scroll_speed_stocks scroll_speed_spring_training scroll_speed_flights flight_tracking_latitude flight_tracking_longitude flight_tracking_address flight_source adsb_receiver_url flight_max_range_nm airlabs_api_key zip_code weather_api_key custom_message brightness dim_enabled dim_start dim_end dim_brightness; do
  hits=$(grep -rln "'$key'\|\"$key\"" --include="*.py" . | grep -v wifi_config_server | grep -v tests | grep -v __pycache__ | tr '\n' ' ')
  echo "$key: ${hits:-NO CONSUMER}"
done
```

- [ ] **Step 3: Write `docs/admin-config-audit.md`**

A table with one row per key: `key | in HTML | in saveConfig | restored on load | server default | consumer | verdict`. Verdicts: `OK`, `BROKEN (describe)`, `DEAD (no consumer)`.

- [ ] **Step 4: Fix BROKEN rows now**

A control that exists but doesn't round-trip (in HTML but missing from saveConfig, or saved but never restored on load, or missing a server default) is a bug — fix it in `wifi_config_server.py` so all four columns agree.

- [ ] **Step 5: STOP for user review of DEAD rows**

Commit the audit + fixes, then STOP and present the DEAD list to the user before deleting anything. Removal of dead controls happens in Task 8's restructure only for controls the user approved.

```bash
python3 -m pytest tests/ -v && python3 -m py_compile wifi_config_server.py
git add docs/admin-config-audit.md wifi_config_server.py
git commit -m "Audit admin config controls; fix round-trip bugs

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Admin redesign — collapsible sections + team selector

**Files:**
- Modify: `wifi_config_server.py`:
  - CSS block (~lines 155-540): add `details.config-section` styles
  - config tab HTML (lines ~572-930): restructure into 8 `<details>` sections
  - page-load JS (~1036-1126): restore `team` radio
  - `saveConfig()` (~1286-1338): send `team`, reboot-notice message
  - server `load_config()` defaults (~100-190): add `'team': 'cubs'` and apply team defaults
  - new route: `/team_logo/<slug>`
  - page `<title>`/`<h1>`: show active team name
- Test: `tests/test_admin_config.py` (new)

**Interfaces:**
- Consumes: `teams.TEAMS`, `teams.DEFAULT_TEAM_SLUG`, `teams.apply_team_defaults`, `teams.get_active_team`
- Produces: `"team"` key round-trips through `/save_config` and page load; this is the key `teams.get_active_team()` reads (Task 1)

- [ ] **Step 1: Write failing admin tests**

Create `tests/test_admin_config.py`:

```python
"""Admin panel team selection round-trip tests"""

import json

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    import wifi_config_server as wcs
    monkeypatch.setattr(wcs, 'CONFIG_PATH', str(tmp_path / 'config.json'))
    wcs.app.config['TESTING'] = True
    return wcs.app.test_client()


def test_admin_page_offers_team_choices(client):
    html = client.get('/admin').data.decode()
    assert 'name="team"' in html
    assert 'value="cubs"' in html
    assert 'value="cardinals"' in html
    assert '<details' in html


def test_save_config_round_trips_team(client, tmp_path, monkeypatch):
    import wifi_config_server as wcs
    resp = client.post('/save_config', json={'team': 'cardinals'})
    assert resp.get_json()['success']
    saved = json.loads((tmp_path / 'config.json').read_text())
    assert saved['team'] == 'cardinals'


def test_load_config_defaults_team_to_cubs(client, monkeypatch):
    import wifi_config_server as wcs
    assert wcs.load_config()['team'] == 'cubs'


def test_load_config_cardinals_disables_bears_by_default(
        client, tmp_path, monkeypatch):
    import wifi_config_server as wcs
    (tmp_path / 'config.json').write_text(json.dumps({'team': 'cardinals'}))
    cfg = wcs.load_config()
    assert cfg['enable_bears'] is False
    assert cfg['enable_clock'] is False


def test_team_logo_route(client):
    resp = client.get('/team_logo/cardinals')
    assert resp.status_code == 200
    assert resp.mimetype == 'image/png'
    assert client.get('/team_logo/mets').status_code == 404
```

First read the top of `wifi_config_server.py` to confirm the Flask object is named `app`, the config path constant is `CONFIG_PATH`, and the admin route path is `/admin` (adjust the test to what's actually there — the grep in Task 7 Step 1 will already have shown this). If importing the module has side effects (starting threads/server at import), guard the test with whatever pattern the module supports, or add a `if __name__ == '__main__'` guard if the module lacks one (that's a fix, not a redesign).

Run: `python3 -m pytest tests/test_admin_config.py -v` — expected: FAIL (no team controls, no route).

- [ ] **Step 2: Server-side changes**

In `wifi_config_server.py`:

1. Import: `from teams import TEAMS, DEFAULT_TEAM_SLUG, apply_team_defaults`
2. In `load_config()`, add `'team': DEFAULT_TEAM_SLUG,` to the defaults dict, and change the merge to:

```python
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                loaded = json.load(f)
                default_config = apply_team_defaults(default_config, loaded)
                default_config.update(loaded)
    except Exception as e:
        print(f"Error loading config: {e}")
```

3. Add the logo route (near the other routes):

```python
@app.route('/team_logo/<slug>')
def team_logo(slug):
    pack = TEAMS.get(slug)
    if pack is None:
        return ('Not found', 404)
    return send_file(pack.logo_path, mimetype='image/png')
```

(`from flask import send_file` — add to the existing flask import line.)

4. Wherever the admin template is rendered (`render_template_string(HTML_TEMPLATE, ...)`), pass `teams=TEAMS`.

- [ ] **Step 3: CSS for collapsible sections**

Add to the `<style>` block:

```css
        details.config-section {
            border: 1px solid #d0d7e2;
            border-radius: 8px;
            margin-bottom: 12px;
            background: #fafbfd;
        }
        details.config-section > summary {
            cursor: pointer;
            padding: 12px 15px;
            font-weight: bold;
            color: #0C2340;
            font-size: 1.05em;
            list-style-position: inside;
        }
        details.config-section[open] > summary {
            border-bottom: 1px solid #d0d7e2;
        }
        details.config-section > .section-body {
            padding: 15px;
        }
        .team-option {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px;
            border: 2px solid #d0d7e2;
            border-radius: 8px;
            margin-bottom: 8px;
            cursor: pointer;
        }
        .team-option:has(input:checked) {
            border-color: #CC3433;
            background: #fff5f5;
        }
        .team-option img { width: 28px; height: 28px; object-fit: contain; }
        .team-swatch {
            width: 18px; height: 18px; border-radius: 4px;
            border: 1px solid #999; margin-left: auto;
        }
        .checkbox-columns {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 4px 16px;
        }
```

- [ ] **Step 4: Restructure the config tab HTML**

Replace lines ~572-930 with 8 sections. Every EXISTING control keeps its element id, type, and attributes verbatim — this is a relocation, not a rewrite (the load/save JS addresses controls by id). Only controls the user approved for deletion in Task 7 are dropped. Layout:

```html
<div id="config-tab" class="tab-content">
    <h2>Display Configuration</h2>

    <details class="config-section" open>
        <summary>Team</summary>
        <div class="section-body">
            <p class="help-text">Pick the MLB team this board follows. The whole display re-themes to the team. Reboot required after changing.</p>
            {% for slug, t in teams.items() %}
            <label class="team-option">
                <input type="radio" name="team" value="{{ slug }}">
                <img src="/team_logo/{{ slug }}" alt="{{ t.name }}">
                <span>{{ t.name }}</span>
                <span class="team-swatch" style="background: rgb({{ t.primary_color[0] }},{{ t.primary_color[1] }},{{ t.primary_color[2] }})"></span>
            </label>
            {% endfor %}
        </div>
    </details>

    <details class="config-section">
        <summary>Brightness &amp; Auto-Dim</summary>
        <div class="section-body">
            <!-- MOVE HERE verbatim: brightness slider block, dim_enabled,
                 dim_start/dim_end, dim_brightness (old lines 575-599) -->
        </div>
    </details>

    <details class="config-section">
        <summary>Display Mode</summary>
        <div class="section-body">
            <!-- MOVE HERE: display_mode select (old lines 601-609) -->
        </div>
    </details>

    <details class="config-section">
        <summary>Content Displays</summary>
        <div class="section-body">
            <p class="help-text">Select which content to show in the rotation:</p>
            <h4>Baseball</h4>
            <div class="checkbox-columns">
                <!-- enable_cubs_facts (label: "Team facts & custom message"),
                     enable_cubs_news (label: "Team breaking news"),
                     enable_cubs_history (label: "Today in team history"),
                     enable_spring_training, enable_playoff_race,
                     enable_clock (label: "Wrigley scoreboard clock") -->
            </div>
            <h4>Other Sports</h4>
            <div class="checkbox-columns">
                <!-- enable_bears, enable_bears_news, enable_pga,
                     enable_pga_news, enable_pga_facts -->
            </div>
            <h4>News &amp; Info</h4>
            <div class="checkbox-columns">
                <!-- enable_weather, enable_newsmax, enable_stocks -->
            </div>
            <h4>Sky &amp; Flight</h4>
            <div class="checkbox-columns">
                <!-- enable_sky, enable_iss, enable_flights,
                     enable_flight_radar, flights_between_displays -->
            </div>
            <h4>Faith &amp; Fun</h4>
            <div class="checkbox-columns">
                <!-- enable_bible, enable_bible_facts, enable_celebrations -->
            </div>
        </div>
    </details>

    <details class="config-section">
        <summary>Scroll Speeds</summary>
        <div class="section-body">
            <!-- MOVE HERE: the 13 speed-control blocks (old lines 768-849),
                 relabel "Cubs Facts"->"Team Facts", "Cubs News"->"Team News" -->
        </div>
    </details>

    <details class="config-section">
        <summary>Flight Tracking</summary>
        <div class="section-body">
            <!-- MOVE HERE: lat/lon, address lookup, flight source radios,
                 adsb_receiver_url, flight_max_range_nm, airlabs_api_key
                 (old lines 851-909) -->
        </div>
    </details>

    <details class="config-section">
        <summary>Weather &amp; Location</summary>
        <div class="section-body">
            <!-- MOVE HERE: zip_code, weather_api_key (old lines 911-920) -->
        </div>
    </details>

    <details class="config-section">
        <summary>Custom Message</summary>
        <div class="section-body">
            <!-- MOVE HERE: custom_message textarea (old lines 922-926) -->
        </div>
    </details>

    <button onclick="saveConfig()">Save Configuration</button>
    <div id="config-status" class="status"></div>
</div>
```

Each `<!-- MOVE HERE -->` comment means: cut the existing HTML block and paste it there unchanged (only the checkbox labels named above change text). Remove the now-redundant inline `<h3>`/`<h4>` headers that the summaries replace.

- [ ] **Step 5: JS changes**

In the page-load JS (where `display_mode` is restored, ~line 1036), add:

```javascript
            const teamSlug = config.team || 'cubs';
            const teamRadio = document.querySelector(
                `input[name="team"][value="${teamSlug}"]`);
            if (teamRadio) teamRadio.checked = true;
            window._loadedTeam = teamSlug;
```

In `saveConfig()`, add to the config object:

```javascript
                team: document.querySelector('input[name="team"]:checked').value,
```

and change the success message logic:

```javascript
                if (data.success) {
                    const teamChanged =
                        config.team !== window._loadedTeam;
                    window._loadedTeam = config.team;
                    showStatus('config-status',
                        teamChanged
                            ? 'Configuration saved! REBOOT the Pi for the team change to take effect (System tab).'
                            : 'Configuration saved successfully! Restart the service for changes to take effect.',
                        true);
                }
```

- [ ] **Step 6: Page title reflects the active team**

Where the template is rendered, also pass `active_team=get_active_team(load_config())`. In the HTML, `<title>Cubs Scoreboard Admin</title>` → `<title>{{ active_team.short_name }} Scoreboard Admin</title>`, and the `<h1>` similarly if it names the Cubs.

- [ ] **Step 7: Run tests, compile, manual smoke**

```bash
python3 -m pytest tests/ -v && python3 -m py_compile wifi_config_server.py
```

Then run the Flask app locally (`python3 wifi_config_server.py`, or if it requires Pi-only resources, rely on the test client) and click through: sections collapse/expand, team radio persists across save + reload, no console errors.

- [ ] **Step 8: Commit**

```bash
git add wifi_config_server.py tests/test_admin_config.py
git commit -m "Rebuild admin Display Config as collapsible sections with team selector

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: Final verification sweep

**Files:**
- Modify: `CLAUDE.md` (brief: mention teams.py and the team config key in the project structure table and Configuration section)
- No other new code

- [ ] **Step 1: Full-repo Cubs-reference sweep**

```bash
grep -rn "CUBS_TEAM_ID\|CHICAGO CUBS\|'CHC'\|\"CHC\"\|'./W.gif'\|'./marquee.png'\|'./logos/cubs.png'" --include="*.py" . | grep -v tests/ | grep -v teams.py | grep -v __pycache__
```

Expected: no hits (teams.py holds the only literals). Any hit is an unmigrated site — fix it following the Task 4/5 patterns.

- [ ] **Step 2: Full test suite + compile gate**

```bash
python3 -m pytest tests/ -v
for f in teams.py config_validator.py scoreboard_manager.py live_game_handler.py game_state_handler.py cubs_history_display.py playoff_race_display.py spring_training_display.py allstar_display.py setup_display.py off_season_handler.py wifi_config_server.py; do python3 -m py_compile "$f" || echo "COMPILE FAIL: $f"; done
```

Expected: all tests pass, no compile failures.

- [ ] **Step 3: Cardinals smoke test on dev machine**

```bash
python3 - <<'EOF'
import teams
teams.load_user_config = lambda: {'team': 'cardinals'}
pack = teams.get_active_team()
assert pack.slug == 'cardinals'
import json, os
for p in (pack.logo_path, pack.marquee_path, pack.celebration_path):
    assert os.path.exists(p), p
print('Cardinals pack OK:', pack.name)
EOF
```

- [ ] **Step 4: Update CLAUDE.md**

Add `teams.py` to the Core Application table ("Team packs (Cubs, Cardinals): identity, colors, assets, content sources") and one line under Configuration: "`team` — active team pack slug (`cubs` default, `cardinals`)". Do not rewrite anything else.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "Document team pack architecture

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

**Deployment note (for the user, not this plan):** after pushing, each Pi needs the new files synced to `/home/pi/` root (or the nightly auto-updater picks them up) and a reboot. Existing boards keep Cubs behavior with zero config changes.

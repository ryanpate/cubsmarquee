# USA Today News Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a rotation screen that scrolls USA Today Top Stories headlines, mirroring the existing Newsmax display.

**Architecture:** Standalone `usatoday_display.py` module copied from the `newsmax_display.py` pattern (spec Approach A): RSS via the timeout-aware `rss_fetch.fetch_feed`, 30-minute cache, branded white header with a generated logo, scrolling `large_bold` ticker. Integration = one rotation slot in `off_season_handler.py` plus `enable_usatoday`/`scroll_speed_usatoday` in the admin panel.

**Tech Stack:** Python 3.9+ (`from __future__ import annotations`), feedparser via `rss_fetch`, PIL, pytest (rgbmatrix mocked in `tests/conftest.py`).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-02-usatoday-display-design.md`.
- Feed URL exactly: `http://rssfeeds.usatoday.com/usatoday-NewsTopStories`.
- Headline prefix exactly: `"USA TODAY: "`, headlines uppercased, max 12 items.
- Fallback headline exactly: `"USA TODAY: CHECK BACK FOR THE LATEST NEWS UPDATES!"`.
- Colors: background white; brand blue `(0, 155, 255)`; scroll text navy `(20, 40, 80)`.
- Do not modify `newsmax_display.py`.
- Match existing style: print-based logging in display modules, type hints, `Cls.__new__(Cls)` test construction.
- Run the full suite (`pytest tests/ -q`) before every commit; 443 tests must stay green (count grows as tasks add tests).

---

### Task 1: `usatoday_display.py` — fetch, format, and display module

**Files:**
- Create: `usatoday_display.py`
- Test: `tests/test_usatoday_display.py`

**Interfaces:**
- Consumes: `rss_fetch.fetch_feed(url)` (existing), `scoreboard_config` names: `Colors`, `GameConfig.NEWS_UPDATE_INTERVAL`, `DisplayConfig.MATRIX_COLS/MATRIX_ROWS`, `RGBColor`, `get_scroll_delay`, `load_user_config` (all existing).
- Produces: `UsaTodayDisplay(scoreboard_manager)` with `display_usatoday_news(duration: int = 180) -> None`, `_fetch_usatoday_rss() -> list[str]`, `_get_live_usatoday_news() -> list[str]`, `_load_scroll_config() -> dict`. Task 3 imports `UsaTodayDisplay` and calls `display_usatoday_news`; Task 4 reads config key `scroll_speed_usatoday`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_usatoday_display.py`:

```python
"""USA Today display: feed formatting, caching guards, timeout usage"""

from __future__ import annotations

import types
from unittest.mock import Mock


def _display():
    import usatoday_display as ud
    return ud.UsaTodayDisplay.__new__(ud.UsaTodayDisplay)


def _entry(title, summary=''):
    e = types.SimpleNamespace()
    e.title = title
    if summary:
        e.summary = summary
    return e


def _patch_feed(monkeypatch, entries, bozo=False):
    import usatoday_display as ud
    feed = types.SimpleNamespace(bozo=bozo, entries=entries)
    calls = {}

    def fake_fetch(url):
        calls['url'] = url
        return feed

    monkeypatch.setattr(ud, 'fetch_feed', fake_fetch)
    return calls


class TestUsaTodayFetch:
    def test_headlines_prefixed_and_uppercased(self, monkeypatch):
        _patch_feed(monkeypatch, [_entry('Storm slams Florida coast')])
        items = _display()._fetch_usatoday_rss()
        assert items == ['USA TODAY: STORM SLAMS FLORIDA COAST']

    def test_fetches_top_stories_feed(self, monkeypatch):
        calls = _patch_feed(monkeypatch, [_entry('A headline')])
        _display()._fetch_usatoday_rss()
        assert calls['url'] == (
            'http://rssfeeds.usatoday.com/usatoday-NewsTopStories')

    def test_summary_appended_when_it_adds_information(self, monkeypatch):
        _patch_feed(monkeypatch, [_entry(
            'Fed holds rates',
            'Central bank officials voted to keep interest rates steady '
            'citing cooling inflation data across sectors. More text here.')])
        items = _display()._fetch_usatoday_rss()
        assert len(items) == 1
        assert items[0].startswith('USA TODAY: FED HOLDS RATES - ')
        assert 'COOLING INFLATION' in items[0]

    def test_duplicate_headlines_dropped(self, monkeypatch):
        _patch_feed(monkeypatch, [
            _entry('Same breaking story about the election tonight'),
            _entry('Same breaking story about the election tonight'),
        ])
        assert len(_display()._fetch_usatoday_rss()) == 1

    def test_capped_at_twelve_items(self, monkeypatch):
        _patch_feed(monkeypatch, [
            _entry(f'Unique headline number {i} with words') for i in range(20)])
        assert len(_display()._fetch_usatoday_rss()) == 12

    def test_html_stripped_from_summaries(self, monkeypatch):
        _patch_feed(monkeypatch, [_entry(
            'Court rules',
            '<p>The&nbsp;justices issued a <b>major</b> opinion on the '
            'landmark case that reshapes federal policy nationwide.</p>')])
        items = _display()._fetch_usatoday_rss()
        assert '<' not in items[0] and '&NBSP;' not in items[0]

    def test_bozo_feed_with_no_entries_returns_empty(self, monkeypatch):
        _patch_feed(monkeypatch, [], bozo=True)
        assert _display()._fetch_usatoday_rss() == []


class TestUsaTodayCache:
    def test_empty_cache_triggers_update(self):
        d = _display()
        d.usatoday_news = None
        d.last_news_update = None
        assert d._should_update_news() is True

    def test_fresh_cache_skips_update(self, monkeypatch):
        import time
        d = _display()
        d.usatoday_news = ['USA TODAY: SOMETHING']
        d.news_update_interval = 1800
        d.last_news_update = time.time()
        assert d._should_update_news() is False


def test_usatoday_fetch_uses_timeout(monkeypatch):
    """Network goes through rss_fetch (timeout-enforced), like Newsmax"""
    import requests

    seen = {}
    real_get = requests.get

    def spy_get(url, *args, **kwargs):
        seen[url] = kwargs.get('timeout')
        raise requests.exceptions.ConnectionError('offline test')

    monkeypatch.setattr(requests, 'get', spy_get)
    import usatoday_display as ud
    display = ud.UsaTodayDisplay.__new__(ud.UsaTodayDisplay)

    result = display._fetch_usatoday_rss()

    assert result == []
    assert seen, 'expected RSS fetches to go through rss_fetch'
    assert all(t and t > 0 for t in seen.values())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_usatoday_display.py -v`
Expected: FAIL/ERROR on every test with `ModuleNotFoundError: No module named 'usatoday_display'`

- [ ] **Step 3: Write the module**

Create `usatoday_display.py` (mirror of `newsmax_display.py`; USA Today feed, names, and colors):

```python
"""USA Today news display - Top Stories RSS, white background, navy text"""

from __future__ import annotations

import time
import os
from PIL import Image
from typing import TYPE_CHECKING, Any

from scoreboard_config import Colors, GameConfig, DisplayConfig, RGBColor, get_scroll_delay, load_user_config
from rss_fetch import fetch_feed

if TYPE_CHECKING:
    from scoreboard_manager import ScoreboardManager


class UsaTodayDisplay:
    """Handles USA Today headlines display with RSS feed"""

    RSS_URL = 'http://rssfeeds.usatoday.com/usatoday-NewsTopStories'

    def __init__(self, scoreboard_manager: ScoreboardManager) -> None:
        """Initialize USA Today display"""
        self.manager = scoreboard_manager
        self.scroll_position: int = DisplayConfig.MATRIX_COLS

        # USA Today colors - white background, brand blue, navy text
        self.USATODAY_WHITE: RGBColor = Colors.WHITE
        self.USATODAY_BLUE: RGBColor = (0, 155, 255)   # brand circle blue
        self.USATODAY_NAVY: RGBColor = (20, 40, 80)    # headline text

        # Load USA Today logo
        self.usatoday_logo: Image.Image | None = self._load_usatoday_logo()

        # RSS news caching
        self.usatoday_news: list[str] | None = None
        self.last_news_update: float | None = None
        self.news_update_interval: int = GameConfig.NEWS_UPDATE_INTERVAL

        # Pre-generate cached background image for performance
        self._usatoday_bg: Image.Image = self._create_usatoday_background()

    def _create_usatoday_background(self) -> Image.Image:
        """Pre-generate white background image for performance"""
        img = Image.new("RGB", (DisplayConfig.MATRIX_COLS, DisplayConfig.MATRIX_ROWS), self.USATODAY_WHITE)
        print("USA Today background cached")
        return img

    def _load_usatoday_logo(self) -> Image.Image | None:
        """Load the USA Today logo"""
        logo_paths = [
            './usatoday.png',
            '/home/pi/usatoday.png',
            './logos/usatoday.png',
            '/home/pi/logos/usatoday.png'
        ]
        for path in logo_paths:
            if os.path.exists(path):
                try:
                    logo = Image.open(path).convert('RGBA')
                    print(f"Loaded USA Today logo from {path}")
                    return logo
                except Exception as e:
                    print(f"Error loading USA Today logo: {e}")
        print("USA Today logo not found")
        return None

    def _clean_html(self, text: str) -> str:
        """Remove HTML tags and clean up text"""
        import re
        clean = re.sub(r'<[^>]+>', '', text)
        clean = clean.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        clean = clean.replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean

    def _get_first_sentence(self, text: str, max_length: int = 150) -> str:
        """Extract first sentence or truncate to max length"""
        for ending in ['. ', '! ', '? ']:
            idx = text.find(ending)
            if idx > 0 and idx < max_length:
                return text[:idx + 1].strip()

        if len(text) > max_length:
            truncated = text[:max_length]
            last_space = truncated.rfind(' ')
            if last_space > max_length - 30:
                return truncated[:last_space] + '...'
            return truncated + '...'
        return text

    def _fetch_usatoday_rss(self) -> list[str]:
        """Fetch latest headlines from the USA Today Top Stories feed"""
        news_items: list[str] = []

        try:
            print(f"Fetching USA Today news from {self.RSS_URL}")
            feed = fetch_feed(self.RSS_URL)

            if feed.bozo and not feed.entries:
                print(f"Warning: Feed parsing issue for {self.RSS_URL}")
                return news_items

            print(f"Found {len(feed.entries)} entries from USA Today")

            for entry in feed.entries[:15]:
                try:
                    title = entry.title.strip() if hasattr(entry, 'title') else ''
                    if not title:
                        continue

                    summary = None
                    if hasattr(entry, 'summary') and entry.summary:
                        summary = self._clean_html(entry.summary)
                    elif hasattr(entry, 'description') and entry.description:
                        summary = self._clean_html(entry.description)

                    if summary and len(summary) > 30:
                        summary_short = self._get_first_sentence(summary, max_length=180)

                        title_words = set(title.lower().split())
                        summary_words = set(summary_short.lower().split())
                        new_words = summary_words - title_words

                        if len(new_words) > 5 and summary_short.lower() != title.lower():
                            title_short = title[:60] + '...' if len(title) > 60 else title
                            news_text = f"{title_short} - {summary_short}"
                        else:
                            news_text = summary_short
                    else:
                        news_text = title

                    formatted_news = f"USA TODAY: {news_text.upper()}"

                    is_duplicate = False
                    for existing in news_items:
                        if existing[:50] == formatted_news[:50]:
                            is_duplicate = True
                            break
                    if not is_duplicate:
                        news_items.append(formatted_news)

                except AttributeError as e:
                    print(f"Error parsing entry: {e}")
                    continue

            print(f"Got {len(news_items)} USA Today news items")

        except Exception as e:
            print(f"Error fetching from USA Today RSS: {e}")

        return news_items[:12]

    def _should_update_news(self) -> bool:
        """Check if news needs updating"""
        if not self.usatoday_news or not self.last_news_update:
            return True
        return (time.time() - self.last_news_update) > self.news_update_interval

    def _get_live_usatoday_news(self) -> list[str]:
        """Get cached or fetch fresh USA Today headlines"""
        if self._should_update_news():
            print("Fetching fresh USA Today news from RSS feed...")
            self.usatoday_news = self._fetch_usatoday_rss()
            self.last_news_update = time.time()

        return self.usatoday_news if self.usatoday_news else []

    def _draw_usatoday_header(self):
        """Draw USA Today header: white background, logo, blue rule"""
        self.manager.set_image(self._usatoday_bg, 0, 0)

        if self.usatoday_logo:
            logo_width = self.usatoday_logo.width
            logo_height = self.usatoday_logo.height
            logo_x = (DisplayConfig.MATRIX_COLS - logo_width) // 2
            logo_y = 4

            self._draw_logo(logo_x, logo_y, self.usatoday_logo)

            separator_y = logo_y + logo_height + 2
            for x in range(DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, separator_y, *self.USATODAY_BLUE)
                self.manager.draw_pixel(x, separator_y + 1, *self.USATODAY_BLUE)
        else:
            self.manager.draw_text('small_bold', 18, 16, self.USATODAY_NAVY, 'USA TODAY')
            for x in range(DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, 20, *self.USATODAY_BLUE)

    def _draw_logo(self, x: int, y: int, logo: Image.Image) -> None:
        """Draw the logo at the specified position"""
        try:
            for py in range(logo.height):
                for px in range(logo.width):
                    pixel = logo.getpixel((px, py))
                    if len(pixel) == 4:
                        r, g, b, a = pixel
                        if a > 128:
                            self.manager.draw_pixel(x + px, y + py, r, g, b)
                    else:
                        r, g, b = pixel[:3]
                        self.manager.draw_pixel(x + px, y + py, r, g, b)
        except Exception as e:
            print(f"Error drawing USA Today logo: {e}")

    def _load_scroll_config(self) -> dict:
        """Load scroll speed settings from config file"""
        return load_user_config()

    def display_usatoday_news(self, duration: int = 180) -> None:
        """Display scrolling USA Today headlines with header"""
        live_news = self._get_live_usatoday_news()

        if not live_news:
            live_news = ["USA TODAY: CHECK BACK FOR THE LATEST NEWS UPDATES!"]

        start_time = time.time()
        message_index = 0
        self.scroll_position = DisplayConfig.MATRIX_COLS

        while time.time() - start_time < duration:
            try:
                self.manager.clear_canvas()

                self._draw_usatoday_header()

                current_message = live_news[message_index]

                self.scroll_position -= 1
                text_length = len(current_message) * 10  # large_bold font width

                if self.scroll_position + text_length < 0:
                    self.scroll_position = DisplayConfig.MATRIX_COLS
                    message_index = (message_index + 1) % len(live_news)

                    if message_index == 0:
                        print("Refreshing USA Today news")
                        fresh_news = self._get_live_usatoday_news()
                        if fresh_news:
                            live_news = fresh_news

                self.manager.draw_text(
                    'large_bold', int(self.scroll_position), 44,
                    self.USATODAY_NAVY, current_message
                )

                self.manager.swap_canvas()
                config = self._load_scroll_config()
                scroll_delay = get_scroll_delay(config.get('scroll_speed_usatoday', 5))
                time.sleep(scroll_delay)

            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"Error in USA Today news display: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_usatoday_display.py -v`
Expected: all 10 tests PASS

- [ ] **Step 5: Run the full suite**

Run: `pytest tests/ -q`
Expected: all tests pass (443 existing + 10 new)

- [ ] **Step 6: Commit**

```bash
git add usatoday_display.py tests/test_usatoday_display.py
git commit -m "feat: USA Today headlines display module"
```

---

### Task 2: USA Today logo asset

**Files:**
- Create: `tools/gen_usatoday_logo.py`
- Create: `usatoday.png` (generated by the tool, committed)
- Test: `tests/test_usatoday_display.py` (append one test)

**Interfaces:**
- Consumes: `fonts/DejaVuSans-Bold.ttf` (bundled in repo).
- Produces: `usatoday.png` at repo root — RGBA, height exactly 14px, width ≤ 88px; the display module from Task 1 already looks for `./usatoday.png`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_usatoday_display.py`:

```python
def test_logo_asset_fits_header():
    """usatoday.png must fit the 96px header band (Newsmax-style layout)"""
    import os
    from PIL import Image
    path = os.path.join(os.path.dirname(__file__), '..', 'usatoday.png')
    assert os.path.exists(path), 'run tools/gen_usatoday_logo.py'
    img = Image.open(path)
    assert img.mode == 'RGBA'
    assert img.height == 14
    assert img.width <= 88
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_usatoday_display.py::test_logo_asset_fits_header -v`
Expected: FAIL with "run tools/gen_usatoday_logo.py"

- [ ] **Step 3: Write the generator and run it**

Create `tools/gen_usatoday_logo.py`:

```python
"""Generate usatoday.png: blue circle + USA TODAY wordmark, 14px tall.

Supersample 8x then LANCZOS-downscale, same pipeline as the airline
logos. Run from the repo root: python3 tools/gen_usatoday_logo.py
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

SS = 8                      # supersample factor
HEIGHT = 14                 # final logo height on the matrix
BLUE = (0, 155, 255, 255)   # USA Today brand circle
NAVY = (20, 40, 80, 255)    # wordmark
FONT_PATH = 'fonts/DejaVuSans-Bold.ttf'


def main() -> None:
    h = HEIGHT * SS
    font = ImageFont.truetype(FONT_PATH, int(h * 0.86))
    text = 'USA TODAY'
    text_w = int(font.getlength(text))
    gap = 3 * SS
    w = h + gap + text_w  # circle diameter == full height

    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((0, 0, h - 1, h - 1), fill=BLUE)
    ascent, descent = font.getmetrics()
    draw.text((h + gap, (h - ascent - descent) // 2), text, font=font, fill=NAVY)

    final_w = round(w * HEIGHT / h)
    small = img.resize((final_w, HEIGHT), Image.LANCZOS)
    if small.width > 88:
        small = small.resize((88, HEIGHT), Image.LANCZOS)
    small.save('usatoday.png')
    print(f'wrote usatoday.png ({small.width}x{small.height})')


if __name__ == '__main__':
    main()
```

Run: `python3 tools/gen_usatoday_logo.py` (from the repo root)
Expected: prints `wrote usatoday.png (...x14)`

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_usatoday_display.py::test_logo_asset_fits_header -v`
Expected: PASS

- [ ] **Step 5: Visual check of the asset**

Render an upscaled preview and confirm the circle is round, text legible, no stray fringe pixels:

```bash
python3 -c "
from PIL import Image
img = Image.open('usatoday.png')
bg = Image.new('RGB', img.size, (255, 255, 255))
bg.paste(img, (0, 0), img)
bg.resize((img.width * 8, img.height * 8), Image.NEAREST).save('/tmp/usatoday_check.png')
print(img.size)
"
```

View `/tmp/usatoday_check.png` (Read tool). If the wordmark is mushy at 14px, retry with `HEIGHT = 16` and cap width 88 — legibility on the matrix wins over exact spec dimensions; update the test's height assertion to match what ships.

- [ ] **Step 6: Commit**

```bash
git add tools/gen_usatoday_logo.py usatoday.png tests/test_usatoday_display.py
git commit -m "feat: generated USA Today logo asset"
```

---

### Task 3: Rotation integration in `off_season_handler.py`

**Files:**
- Modify: `off_season_handler.py` (import block ~line 19; `__init__` ~line 45; `rotation_schedule` dict ~line 87-100; `_load_config` defaults ~line 168; rotation sequence — insert after the Newsmax block that ends near line 881)
- Test: `tests/test_usatoday_display.py` (append), Modify: `tests/test_bugfixes.py` (~line 898 scroll-config module list)

**Interfaces:**
- Consumes: `UsaTodayDisplay(scoreboard_manager)` and `display_usatoday_news(duration)` from Task 1.
- Produces: config key `enable_usatoday` (default `True`) and `rotation_schedule['usatoday'] = 2` — Task 4's admin panel writes the same key names.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_usatoday_display.py`:

```python
class TestRotationIntegration:
    def test_off_season_handler_defaults_enable_usatoday(self):
        import off_season_handler as osh
        import inspect
        src = inspect.getsource(osh.OffSeasonHandler._load_config)
        assert "'enable_usatoday': True" in src

    def test_rotation_schedule_has_usatoday_slot(self):
        import off_season_handler as osh
        import inspect
        src = inspect.getsource(osh.OffSeasonHandler.__init__)
        assert "'usatoday'" in src

    def test_rotation_calls_usatoday_display(self):
        import off_season_handler as osh
        import inspect
        src = inspect.getsource(osh.OffSeasonHandler)
        assert 'display_usatoday_news' in src
        assert "self.config.get('enable_usatoday', True)" in src
```

In `tests/test_bugfixes.py`, find the scroll-config parity test near line 898 and add the new module to its list:

```python
        import bears_display
        import bible_display
        import flight_display
        import newsmax_display
        import pga_display
        import spring_training_display
        import usatoday_display

        for module, cls_name in [
            (spring_training_display, 'SpringTrainingDisplay'),
            (bears_display, 'BearsDisplay'),
            (pga_display, 'PGADisplay'),
            (newsmax_display, 'NewsmaxDisplay'),
            (bible_display, 'BibleDisplay'),
            (flight_display, 'FlightDisplay'),
            (usatoday_display, 'UsaTodayDisplay'),
        ]:
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `pytest tests/test_usatoday_display.py::TestRotationIntegration tests/test_bugfixes.py -v`
Expected: the three `TestRotationIntegration` tests FAIL; the modified scroll-config test PASSES already (the module exists and `_load_scroll_config` is implemented) — that's fine, it now guards the new module too.

- [ ] **Step 3: Wire the rotation**

In `off_season_handler.py`:

a. Import (next to the Newsmax import at line 19):

```python
from usatoday_display import UsaTodayDisplay
```

b. Instantiate in `__init__` (next to `self.newsmax_display` at line 45):

```python
self.usatoday_display: UsaTodayDisplay = UsaTodayDisplay(scoreboard_manager)
```

c. Rotation schedule entry (in the `rotation_schedule` dict near line 98, after the `'newsmax'` entry):

```python
'usatoday': 2,
```

d. Config default (in `_load_config` defaults after `'enable_newsmax': True,` at line 168):

```python
'enable_usatoday': True,  # Enable/disable USA Today news
```

e. Rotation block — insert immediately after the Newsmax block (after its `else: print("Skipping Newsmax news (disabled in config)")`, before the stocks block):

```python
        # Display USA Today news if enabled
        usatoday_enabled = self.config.get('enable_usatoday', True)
        if usatoday_enabled:
            print("Displaying USA Today news...")
            try:
                self.usatoday_display.display_usatoday_news(
                    duration=self.rotation_schedule['usatoday'] * 60
                )
                print("USA Today news display finished")
            except Exception as e:
                print(f"Error in USA Today news display: {e}")
                import traceback
                traceback.print_exc()
            if _tick():
                return
        else:
            print("Skipping USA Today news (disabled in config)")
```

- [ ] **Step 4: Run the full suite**

Run: `pytest tests/ -q`
Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add off_season_handler.py tests/test_usatoday_display.py tests/test_bugfixes.py
git commit -m "feat: USA Today slot in content rotation"
```

---

### Task 4: Admin panel wiring in `wifi_config_server.py`

**Files:**
- Modify: `wifi_config_server.py` — defaults dict in `load_config` (enable ~line 162, scroll ~line 183), settings checkbox HTML (~line 806), scroll slider HTML (~line 945), JS config load (~line 1233), JS slider id list (~line 1304), JS save payload (~lines 1498 and 1519), `save_config_route` (~lines 2098 and 2119)
- Test: `tests/test_admin_config.py`

**Interfaces:**
- Consumes: key names from Task 3: `enable_usatoday`, `scroll_speed_usatoday`.
- Produces: admin GUI toggle + slider persisted to `/home/pi/config.json`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_admin_config.py` (uses the existing `client`/`tmp_path` fixtures in this file):

```python
def test_load_config_defaults_usatoday(client, monkeypatch):
    import wifi_config_server as wcs
    cfg = wcs.load_config()
    assert cfg['enable_usatoday'] is True
    assert cfg['scroll_speed_usatoday'] == 5


def test_admin_page_has_usatoday_controls(client):
    resp = client.get('/admin')
    assert b'enable_usatoday' in resp.data
    assert b'scroll_speed_usatoday' in resp.data


def test_save_config_round_trips_usatoday(client, tmp_path, monkeypatch):
    import json
    resp = client.post('/save_config', json={
        'enable_usatoday': False, 'scroll_speed_usatoday': 8})
    assert resp.get_json()['success']
    saved = json.loads((tmp_path / 'config.json').read_text())
    assert saved['enable_usatoday'] is False
    assert saved['scroll_speed_usatoday'] == 8
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_admin_config.py -v -k usatoday`
Expected: 3 FAILs (missing keys / missing page elements)

- [ ] **Step 3: Wire the admin panel**

All edits in `wifi_config_server.py`, each anchored to its Newsmax twin:

a. Defaults in `load_config` — after `'enable_newsmax': True,` (line ~162):

```python
        'enable_usatoday': True,
```

and after `'scroll_speed_newsmax': 5,` (line ~183):

```python
        'scroll_speed_usatoday': 5,
```

b. Settings checkbox HTML — duplicate the `enable_newsmax` row (line ~806) with label text `USA Today News`:

```html
                            <div class="toggle-row">
                                <span class="toggle-label">USA Today News</span>
                                <input type="checkbox" id="enable_usatoday">
                            </div>
```

(Copy the exact surrounding markup of the Newsmax row — class names in the file win over this sketch.)

c. Scroll slider HTML — duplicate the Newsmax slider block (lines ~945-946):

```html
                            <label>USA Today News</label>
                            <input type="range" class="speed-slider" id="scroll_speed_usatoday" min="1" max="10" value="5">
                            <span class="speed-value" id="scroll_speed_usatoday_val">5</span>
```

d. JS config load — next to line ~1233:

```javascript
            document.getElementById('enable_usatoday').checked = config.enable_usatoday !== false;
```

e. JS slider id list (line ~1304) — add `'scroll_speed_usatoday',` to the array containing `'scroll_speed_newsmax'`.

f. JS save payload — next to lines ~1498 and ~1519:

```javascript
                enable_usatoday: document.getElementById('enable_usatoday').checked,
                scroll_speed_usatoday: parseInt(document.getElementById('scroll_speed_usatoday').value),
```

g. `save_config_route` — next to lines ~2098 and ~2119:

```python
            'enable_usatoday': data.get('enable_usatoday', True),
            'scroll_speed_usatoday': data.get('scroll_speed_usatoday', 5),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_admin_config.py -v`
Expected: all PASS (including `test_admin_page_non_default_off_keys_is_clock_only` — if it fails, the new enable key defaulted to something other than True somewhere; fix the default, not the test)

- [ ] **Step 5: Run the full suite**

Run: `pytest tests/ -q`
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add wifi_config_server.py tests/test_admin_config.py
git commit -m "feat: USA Today toggle and scroll speed in admin panel"
```

---

### Task 5: Live feed smoke check, preview render, push

**Files:**
- No new files (throwaway scripts in the session scratchpad only)

**Interfaces:**
- Consumes: everything above.
- Produces: verified deployable main.

- [ ] **Step 1: One-shot live feed check (network permitting)**

```bash
python3 -c "
from usatoday_display import UsaTodayDisplay
d = UsaTodayDisplay.__new__(UsaTodayDisplay)
items = d._fetch_usatoday_rss()
print(len(items), 'items')
for i in items[:5]: print('-', i[:90])
"
```

Expected: ~10-12 prefixed uppercase headlines. If the Gannett feed URL redirects or 404s (feed URLs rot), find the current Top Stories feed URL, update `RSS_URL` and the URL test, and note it in the commit message.

- [ ] **Step 2: Headless preview render of the screen**

The repo pattern for pixel review is a headless render via the PIL preview mirror (see `tools/render_flight_previews.py`). Quick equivalent: instantiate `ScoreboardManager` under the mocked `rgbmatrix` (import `tests/conftest.py` mock setup first), call `_draw_usatoday_header()` plus one `draw_text` frame, save `manager._frame` upscaled, and eyeball logo centering, rule position, and navy-on-white contrast.

- [ ] **Step 3: Full suite + push**

```bash
pytest tests/ -q && git push
```

Expected: green; push succeeds. The Pi's auto-updater converges overnight, or scp `usatoday_display.py`, `usatoday.png`, `off_season_handler.py`, `wifi_config_server.py`, `tools/gen_usatoday_logo.py` to `pi@cubsmarquee-one.local:/home/pi/` and `sudo reboot` for same-day hardware verification (then capture `http://cubsmarquee-one.local/preview.png` during the USA Today slot).

---

## Self-Review

- **Spec coverage:** feed/prefix/cap/fallback → Task 1; logo + header layout → Tasks 1-2; rotation slot after Newsmax at 2 min + `enable_usatoday` → Task 3; admin toggle + slider → Task 4; error posture (timeout, per-frame catch, fallback) → Task 1 code + timeout test; "existing suite stays green" → every task's full-suite step. No gaps.
- **Placeholder scan:** clean — all steps carry real code; Task 4b defers only to the file's existing markup classes, which is deliberate (the HTML template is 2000+ lines and the row structure must match its siblings exactly).
- **Type consistency:** `UsaTodayDisplay`, `display_usatoday_news(duration)`, `_fetch_usatoday_rss()`, `enable_usatoday`, `scroll_speed_usatoday`, `rotation_schedule['usatoday']` used identically across Tasks 1/3/4.

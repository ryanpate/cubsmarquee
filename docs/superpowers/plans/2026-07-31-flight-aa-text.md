# Anti-Aliased Flight-Screen Text Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the flight screens' `'small'` text rows and the fallback monogram badge with anti-aliased TrueType text so they look smooth on the 96x48 LED wall.

**Architecture:** A new pure-PIL module `aa_text.py` rasterizes strings with a bundled DejaVu Sans Bold TTF at 4x scale, downsamples with LANCZOS, and caches the grayscale result per string. `ScoreboardManager` gains `draw_text_aa` / `measure_text_aa` / `fit_text_aa` that composite those bitmaps onto the canvas with alpha-scaled LED brightness (and mirror into the admin preview). `flight_display.py` switches its four `'small'` call sites to the AA methods and its `_monogram_badge` to a 4x-supersampled render. `micro`/`tiny` bitmap text is untouched.

**Tech Stack:** Python 3.9+, Pillow (`ImageFont.truetype`, LANCZOS resize), rgbmatrix (mocked in tests), pytest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-31-flight-aa-text-design.md`.
- Only flight screens change; game/weather/Bears/PGA displays keep bitmap fonts.
- `micro` and `tiny` rows stay bitmap — do NOT anti-alias them.
- If no TTF is found anywhere, every AA method must fall back to the existing bitmap behavior (log once, never crash).
- AA compositing assumes a black background (true for all flight screens): pixel = color x alpha/255.
- Constants live in `scoreboard_config.py` per project convention (the spec said `flight_display.py`; config centralization wins — all other font constants live in `Fonts`).
- Match existing code style: `from __future__ import annotations`, type hints, module docstrings, 4-space indent.
- Run tests with: `python3 -m pytest tests/ -v` from the repo root (rgbmatrix is mocked in `tests/conftest.py`).
- End every commit message with:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_01Gq8oTa4HFqasLkPhEFT76v`

---

### Task 1: Bundle the TTF and add config constants

**Files:**
- Create: `fonts/DejaVuSans-Bold.ttf` (binary, downloaded)
- Create: `fonts/LICENSE-DejaVu.txt` (from the same release tarball)
- Modify: `scoreboard_config.py` (the `Fonts` class, near line 125-138)
- Test: `tests/test_aa_text.py` (new file, first test only)

**Interfaces:**
- Consumes: nothing.
- Produces: `Fonts.AA_TTF_CANDIDATES: tuple[str, ...]` and `Fonts.AA_TEXT_SIZE: int = 9`, plus the bundled TTF at `./fonts/DejaVuSans-Bold.ttf`. Later tasks reference both names exactly.

- [ ] **Step 1: Download the font and its license**

```bash
cd /Users/ryanpate/cubsmarquee
curl -L -o /tmp/dejavu.tar.bz2 https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37/dejavu-fonts-ttf-2.37.tar.bz2
tar -xjf /tmp/dejavu.tar.bz2 -C /tmp
cp /tmp/dejavu-fonts-ttf-2.37/ttf/DejaVuSans-Bold.ttf fonts/DejaVuSans-Bold.ttf
cp /tmp/dejavu-fonts-ttf-2.37/LICENSE fonts/LICENSE-DejaVu.txt
```

If the download fails (no network / URL moved), fall back to copying a system DejaVu Bold if one exists (`/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf` on Linux); if neither works, stop and report — later tasks need this file.

Verify: `python3 -c "from PIL import ImageFont; f = ImageFont.truetype('fonts/DejaVuSans-Bold.ttf', 36); print(f.getname())"` prints `('DejaVu Sans', 'Bold')`.

- [ ] **Step 2: Write the failing test**

Create `tests/test_aa_text.py`:

```python
"""Anti-aliased TTF text rendering for the flight screens"""

from __future__ import annotations

import os


class TestConfig:
    def test_bundled_ttf_and_constants(self) -> None:
        from scoreboard_config import Fonts

        assert Fonts.AA_TEXT_SIZE == 9
        assert Fonts.AA_TTF_CANDIDATES[0] == './fonts/DejaVuSans-Bold.ttf'
        assert os.path.exists(Fonts.AA_TTF_CANDIDATES[0])
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest tests/test_aa_text.py -v`
Expected: FAIL with `AttributeError: ... 'AA_TEXT_SIZE'`

- [ ] **Step 4: Add the constants**

In `scoreboard_config.py`, inside the `Fonts` class after `ULTRA_MICRO` (match the existing attribute style exactly):

```python
    # Anti-aliased TTF text (flight screens). First hit wins; the bundled
    # repo font makes rendering identical on the Pi and dev machines.
    AA_TTF_CANDIDATES: tuple[str, ...] = (
        "./fonts/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    )
    AA_TEXT_SIZE: int = 9
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_aa_text.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add fonts/DejaVuSans-Bold.ttf fonts/LICENSE-DejaVu.txt scoreboard_config.py tests/test_aa_text.py
git commit -m "Bundle DejaVu Sans Bold TTF for anti-aliased flight text"
```

---

### Task 2: `aa_text.py` renderer module

**Files:**
- Create: `aa_text.py`
- Test: `tests/test_aa_text.py` (extend)

**Interfaces:**
- Consumes: `Fonts.AA_TTF_CANDIDATES` from Task 1 (in tests only; the module itself takes plain paths).
- Produces (used verbatim by Tasks 3 and 5):
  - `aa_text.SCALE: int = 4`
  - `aa_text.find_ttf(candidates: Sequence[str]) -> str | None`
  - `aa_text.AATextRenderer(ttf_path: str, size: int)` with:
    - `.ascent: int` (property, 1x-scale pixels)
    - `.render(text: str) -> Image.Image` (mode `'L'`, 1x scale, cached per string)
    - `.measure(text: str) -> int` (rendered width in pixels)
    - `.fit(text: str, max_width: int) -> str` (trims trailing chars until it fits)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_aa_text.py`:

```python
class TestAATextRenderer:
    def _renderer(self, size: int = 9):
        from aa_text import AATextRenderer, find_ttf
        from scoreboard_config import Fonts

        path = find_ttf(Fonts.AA_TTF_CANDIDATES)
        assert path is not None  # Task 1 bundled the font
        return AATextRenderer(path, size)

    def test_find_ttf_returns_none_when_nothing_exists(self) -> None:
        from aa_text import find_ttf

        assert find_ttf(['/nope/a.ttf', '/nope/b.ttf']) is None

    def test_render_is_grayscale_at_1x_scale(self) -> None:
        r = self._renderer(size=9)
        img = r.render('United')

        assert img.mode == 'L'
        # 1x scale: a 9pt string is around 9-12px tall, nowhere near 4x
        assert 6 <= img.height <= 14
        assert img.width >= 20
        assert 0 < r.ascent <= img.height

    def test_render_is_antialiased(self) -> None:
        img = self._renderer().render('United')

        levels = set(img.getdata())
        # Hard bitmap text has 2 levels; AA produces many intermediates
        assert len(levels) > 10

    def test_render_caches_per_string(self) -> None:
        r = self._renderer()

        assert r.render('ORD-LAX') is r.render('ORD-LAX')

    def test_measure_matches_render_width(self) -> None:
        r = self._renderer()

        assert r.measure('A321neo') == r.render('A321neo').width
        assert r.measure('Los Angeles') > r.measure('LA')

    def test_fit_trims_to_width(self) -> None:
        r = self._renderer()
        fitted = r.fit('International Heavy Cargo', 68)

        assert r.measure(fitted) <= 68
        assert 0 < len(fitted) < len('International Heavy Cargo')
        assert 'International Heavy Cargo'.startswith(fitted.rstrip())

    def test_fit_keeps_short_text_unchanged(self) -> None:
        r = self._renderer()

        assert r.fit('United', 68) == 'United'

    def test_fit_zero_width_returns_empty(self) -> None:
        assert self._renderer().fit('United', 0) == ''
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_aa_text.py -v`
Expected: the new tests FAIL with `ModuleNotFoundError: No module named 'aa_text'`; the Task 1 test still passes.

- [ ] **Step 3: Implement `aa_text.py`**

```python
"""Anti-aliased TrueType text rendering for the LED matrix.

Strings are rasterized at SCALE-times the target size and downsampled
with LANCZOS, so edge pixels come out as intermediate gray levels. Drawn
onto the matrix as partial LED brightness, those soft edges read as
smooth curves at viewing distance.
"""

from __future__ import annotations

import os
from typing import Sequence

from PIL import Image, ImageDraw, ImageFont

# Supersampling factor: render at 4x, downsample to 1x
SCALE: int = 4


def find_ttf(candidates: Sequence[str]) -> str | None:
    """First existing path from candidates, or None if there is none"""
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


class AATextRenderer:
    """Renders strings to cached 1x-scale grayscale bitmaps"""

    def __init__(self, ttf_path: str, size: int) -> None:
        self._font = ImageFont.truetype(ttf_path, size * SCALE)
        ascent, descent = self._font.getmetrics()
        self.ascent: int = max(1, round(ascent / SCALE))
        self._height_4x = ascent + descent
        self._height = max(1, round(self._height_4x / SCALE))
        self._cache: dict[str, Image.Image] = {}

    def render(self, text: str) -> Image.Image:
        """Grayscale ('L') image of text at 1x scale; cached per string"""
        img = self._cache.get(text)
        if img is None:
            width_4x = max(1, int(self._font.getlength(text)))
            big = Image.new('L', (width_4x, self._height_4x), 0)
            ImageDraw.Draw(big).text((0, 0), text, font=self._font, fill=255)
            img = big.resize(
                (max(1, round(width_4x / SCALE)), self._height),
                Image.LANCZOS)
            self._cache[text] = img
        return img

    def measure(self, text: str) -> int:
        """Rendered width of text in 1x pixels"""
        return self.render(text).width

    def fit(self, text: str, max_width: int) -> str:
        """Trim trailing characters until text fits in max_width pixels"""
        if max_width <= 0:
            return ''
        while text and self.measure(text) > max_width:
            text = text[:-1].rstrip()
        return text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_aa_text.py -v`
Expected: all PASS. If `test_render_is_grayscale_at_1x_scale` fails on the height bound, print `img.height` — DejaVu Bold at 36pt has ascent+descent ~42px → ~10-11px at 1x; adjust nothing in the module, fix the test bound only if it's off by 1-2px.

- [ ] **Step 5: Commit**

```bash
git add aa_text.py tests/test_aa_text.py
git commit -m "Add supersampled AA text renderer module"
```

---

### Task 3: Manager `draw_text_aa` / `measure_text_aa` / `fit_text_aa`

**Files:**
- Modify: `scoreboard_manager.py` (imports near line 9-20; `__init__` near line 34-62; new methods after `draw_text`, near line 497)
- Test: `tests/test_aa_text.py` (extend)

**Interfaces:**
- Consumes: `aa_text.AATextRenderer`, `aa_text.find_ttf` (Task 2); `Fonts.AA_TTF_CANDIDATES`, `Fonts.AA_TEXT_SIZE` (Task 1); existing `self.draw_text(font_name, x, y, color_tuple, text)` and `self.draw_pixel(x, y, r, g, b)` (which already mirrors into the admin preview frame).
- Produces (used verbatim by Task 4):
  - `ScoreboardManager.draw_text_aa(x: int, baseline: int, color_tuple: RGBColor, text: str, size: int = Fonts.AA_TEXT_SIZE) -> None`
  - `ScoreboardManager.measure_text_aa(text: str, size: int = Fonts.AA_TEXT_SIZE) -> int`
  - `ScoreboardManager.fit_text_aa(text: str, max_width: int, size: int = Fonts.AA_TEXT_SIZE) -> str`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_aa_text.py`. `ScoreboardManager.__init__` touches hardware, so build the object with `__new__` and set only the attributes the AA path uses (same pattern as `FlightDisplay.__new__` in `tests/test_flightwall_style.py`):

```python
from unittest.mock import Mock


def _manager(ttf: str | None):
    """ScoreboardManager with only the AA-path attributes populated"""
    from scoreboard_manager import ScoreboardManager

    m = ScoreboardManager.__new__(ScoreboardManager)
    m._aa_ttf = ttf
    m._aa_renderers = {}
    m._aa_warned = False
    m.draw_text = Mock()
    m.draw_pixel = Mock()
    return m


def _real_ttf() -> str:
    from aa_text import find_ttf
    from scoreboard_config import Fonts

    path = find_ttf(Fonts.AA_TTF_CANDIDATES)
    assert path is not None
    return path


class TestManagerAAText:
    def test_draw_falls_back_to_bitmap_without_ttf(self) -> None:
        m = _manager(ttf=None)
        m.draw_text_aa(26, 9, (255, 255, 255), 'United')

        m.draw_text.assert_called_once_with(
            'small', 26, 9, (255, 255, 255), 'United')
        m.draw_pixel.assert_not_called()

    def test_measure_and_fit_fall_back_without_ttf(self) -> None:
        m = _manager(ttf=None)

        assert m.measure_text_aa('United') == 6 * 6  # CHAR_WIDTH_SMALL
        assert m.fit_text_aa('United Airlines', 68) == 'United Airl'  # 68//6

    def test_draw_writes_alpha_scaled_pixels_in_bounds(self) -> None:
        m = _manager(ttf=_real_ttf())
        m.draw_text_aa(80, 9, (200, 100, 50), 'United')  # spills past x=95

        m.draw_text.assert_not_called()
        assert m.draw_pixel.called
        for call in m.draw_pixel.call_args_list:
            x, y, r, g, b = call.args
            assert 0 <= x < 96 and 0 <= y < 48   # clipped to canvas
            assert 0 < r <= 200 and g <= 100 and b <= 50  # alpha-scaled

    def test_measure_uses_renderer_and_caches_it(self) -> None:
        from aa_text import AATextRenderer

        m = _manager(ttf=_real_ttf())
        w = m.measure_text_aa('ORD-LAX')

        assert w > 0
        assert isinstance(m._aa_renderers[9], AATextRenderer)
        assert m.fit_text_aa('United', 500) == 'United'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_aa_text.py::TestManagerAAText -v`
Expected: FAIL with `AttributeError: ... 'draw_text_aa'`

- [ ] **Step 3: Implement the manager methods**

In `scoreboard_manager.py`:

Add to the imports block (after the existing `from retry import ...` line, matching import ordering):

```python
from aa_text import AATextRenderer, find_ttf
```

In `__init__`, right after `self.fonts: dict[str, graphics.Font] = self._load_fonts()`:

```python
        # Anti-aliased TTF text (flight screens); None means bitmap fallback
        self._aa_ttf: str | None = find_ttf(Fonts.AA_TTF_CANDIDATES)
        self._aa_renderers: dict[int, AATextRenderer] = {}
        self._aa_warned: bool = False
```

After the existing `draw_text` method (line ~497), add:

```python
    def _aa_renderer(self, size: int) -> AATextRenderer | None:
        """Renderer for a font size, or None when no TTF is available"""
        if self._aa_ttf is None:
            if not self._aa_warned:
                _logger.warning(
                    "No TTF found for AA text; using bitmap fonts")
                self._aa_warned = True
            return None
        renderer = self._aa_renderers.get(size)
        if renderer is None:
            renderer = AATextRenderer(self._aa_ttf, size)
            self._aa_renderers[size] = renderer
        return renderer

    def draw_text_aa(
        self, x: int, baseline: int, color_tuple: RGBColor, text: str,
        size: int = Fonts.AA_TEXT_SIZE
    ) -> None:
        """Draw anti-aliased TTF text; edge pixels get partial brightness.

        Assumes a black background: each pixel is color scaled by the
        anti-aliasing alpha. Falls back to bitmap 'small' without a TTF.
        """
        renderer = self._aa_renderer(size)
        if renderer is None:
            self.draw_text('small', x, baseline, color_tuple, text)
            return
        img = renderer.render(text)
        top = baseline - renderer.ascent
        red, green, blue = color_tuple
        pixels = img.load()
        for yy in range(img.height):
            cy = top + yy
            if not 0 <= cy < DisplayConfig.MATRIX_ROWS:
                continue
            for xx in range(img.width):
                alpha = pixels[xx, yy]
                if alpha < 8:
                    continue
                cx = x + xx
                if not 0 <= cx < DisplayConfig.MATRIX_COLS:
                    continue
                self.draw_pixel(
                    cx, cy,
                    red * alpha // 255,
                    green * alpha // 255,
                    blue * alpha // 255)

    def measure_text_aa(
        self, text: str, size: int = Fonts.AA_TEXT_SIZE
    ) -> int:
        """Width in pixels of text drawn by draw_text_aa"""
        renderer = self._aa_renderer(size)
        if renderer is None:
            return len(text) * Fonts.CHAR_WIDTH_SMALL
        return renderer.measure(text)

    def fit_text_aa(
        self, text: str, max_width: int, size: int = Fonts.AA_TEXT_SIZE
    ) -> str:
        """Trim text so draw_text_aa fits within max_width pixels"""
        renderer = self._aa_renderer(size)
        if renderer is None:
            return text[:max(0, max_width // Fonts.CHAR_WIDTH_SMALL)]
        return renderer.fit(text, max_width)
```

Note: `draw_pixel` already writes both the LED canvas and the admin-preview frame, so the preview mirrors AA text with no extra work.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_aa_text.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add scoreboard_manager.py tests/test_aa_text.py
git commit -m "Add AA text drawing to ScoreboardManager with bitmap fallback"
```

---

### Task 4: Flight display uses AA for its `'small'` text

**Files:**
- Modify: `flight_display.py` (`_draw_detail_frame` ~line 1169-1226, `_display_no_flights` ~line 923-938, `_display_summary_view` ~line 964-979)
- Test: `tests/test_flightwall_style.py` (update helpers + assertions)

**Interfaces:**
- Consumes: `manager.draw_text_aa(x, baseline, color, text)`, `manager.measure_text_aa(text)`, `manager.fit_text_aa(text, max_width)` from Task 3 (all at default size).
- Produces: no new interfaces; `micro`/`tiny` call sites are unchanged.

- [ ] **Step 1: Update the tests (they must fail first)**

In `tests/test_flightwall_style.py`:

Replace the `_texts` helper (line ~93) so it also collects AA calls — note the different arg positions (`draw_text` is `(font, x, y, color, text)`; `draw_text_aa` is `(x, baseline, color, text)`):

```python
def _texts(manager):
    """(color, text) for every draw_text and draw_text_aa call"""
    calls = [(c.args[3], c.args[4])
             for c in manager.draw_text.call_args_list]
    calls += [(c.args[2], c.args[3])
              for c in manager.draw_text_aa.call_args_list]
    return calls
```

In `_card_display()` (line ~79), after `d.manager = Mock()` add pass-through stubs so proportional-width helpers behave under Mock:

```python
    d.manager.fit_text_aa.side_effect = lambda text, max_width: text
    d.manager.measure_text_aa.side_effect = lambda text: len(text) * 6
```

In `TestSummaryRestyle._render_one_frame` (line ~185), the `texts` dict in `test_headline_and_cyan_values` builds only from `draw_text`; change it to use the shared `_texts` helper:

```python
        texts = dict((t, c) for c, t in _texts(d.manager))
```

In `TestEmptyStateRestyle.test_no_flights_screen_is_headerless` (line ~217), after `d.manager = Mock()` add:

```python
        d.manager.measure_text_aa.side_effect = lambda text: len(text) * 6
```

and change the texts line to:

```python
        texts = [t for _, t in _texts(d.manager)]
```

Finally add a new test class pinning the switch:

```python
class TestAATextOnFlightScreens:
    def test_detail_card_id_lines_use_aa(self) -> None:
        d = _card_display()
        d._draw_detail_frame(dict(UAL_FLIGHT), '1/3', 0.0)

        aa_texts = [c.args[3]
                    for c in d.manager.draw_text_aa.call_args_list]
        assert 'United' in aa_texts
        assert 'ORD-LAX' in aa_texts
        assert 'A321neo' in aa_texts
        # Metric rows stay bitmap micro
        bitmap_fonts = set(
            c.args[0] for c in d.manager.draw_text.call_args_list)
        assert bitmap_fonts == {'micro'}

    def test_id_lines_are_width_truncated(self) -> None:
        d = _card_display()
        d._draw_detail_frame(dict(UAL_FLIGHT), '1/3', 0.0)

        fitted_widths = [c.args[1]
                         for c in d.manager.fit_text_aa.call_args_list]
        assert 68 in fitted_widths  # 96 - 26 - 2 beside the logo

    def test_page_b_city_uses_aa_and_fits_beside_counter(self) -> None:
        d = _card_display()
        d._draw_detail_frame(dict(UAL_FLIGHT), '1/3', 4.0)

        aa_texts = [c.args[3]
                    for c in d.manager.draw_text_aa.call_args_list]
        assert 'Flying to' in aa_texts
        assert 'Los Angeles' in aa_texts
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `python3 -m pytest tests/test_flightwall_style.py -v`
Expected: `TestAATextOnFlightScreens` FAILS (no `draw_text_aa` calls yet); the updated pre-existing tests still pass (the `_texts` helper addition is backward-compatible).

- [ ] **Step 3: Switch the four call sites**

In `flight_display.py`:

**Site 1 — detail card ID lines** (line ~1197-1201). Replace:

```python
        max_chars = (DisplayConfig.MATRIX_COLS - 26) // 6  # 11 chars
        for baseline, text in zip((9, 18, 27), (line1, line2, line3)):
            if text:
                self.manager.draw_text(
                    'small', 26, baseline, white, text[:max_chars])
```

with:

```python
        max_w = DisplayConfig.MATRIX_COLS - 26 - 2  # 68px beside the logo
        for baseline, text in zip((9, 18, 27), (line1, line2, line3)):
            if text:
                self.manager.draw_text_aa(
                    26, baseline, white,
                    self.manager.fit_text_aa(text, max_w))
```

**Site 2 — page B destination/registration** (line ~1208-1224). Replace the `else:` branch body with (note `counter_x` now computed first so the city can fit beside the counter):

```python
            dest_code = (flight.get('dest_iata')
                         or flight.get('destination', 'UNKNOWN'))
            city = self._get_airport_city(dest_code)
            counter_x = (DisplayConfig.MATRIX_COLS
                         - len(counter_text) * 4 - 2)
            if city and city != 'UNKNOWN':
                self.manager.draw_text_aa(2, 37, white, 'Flying to')
                self.manager.draw_text_aa(
                    2, 46, cyan,
                    self.manager.fit_text_aa(
                        self._display_case(city), counter_x - 6))
            elif flight.get('registration'):
                self.manager.draw_text_aa(2, 37, white, 'Registration')
                self.manager.draw_text_aa(
                    2, 46, cyan, flight['registration'])
            self.manager.draw_text(
                'micro', counter_x, 46, Colors.FLIGHT_DIM, counter_text)
```

**Site 3 — no-flights screen** (line ~931-935). Replace:

```python
            for baseline, color, text in (
                    (30, self.FLIGHT_WHITE, 'No flights'),
                    (41, (150, 150, 150), 'overhead')):
                x = (DisplayConfig.MATRIX_COLS - len(text) * 6) // 2
                self.manager.draw_text('small', x, baseline, color, text)
```

with:

```python
            for baseline, color, text in (
                    (30, self.FLIGHT_WHITE, 'No flights'),
                    (41, (150, 150, 150), 'overhead')):
                x = (DisplayConfig.MATRIX_COLS
                     - self.manager.measure_text_aa(text)) // 2
                self.manager.draw_text_aa(x, baseline, color, text)
```

**Site 4 — summary headline** (line ~968-969). Replace:

```python
            self.manager.draw_text(
                'small', 24, 11, self.FLIGHT_WHITE, count_str)
```

with:

```python
            self.manager.draw_text_aa(24, 11, self.FLIGHT_WHITE, count_str)
```

- [ ] **Step 4: Run the full flightwall test file**

Run: `python3 -m pytest tests/test_flightwall_style.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add flight_display.py tests/test_flightwall_style.py
git commit -m "Use anti-aliased text for flight-screen small rows"
```

---

### Task 5: Monogram badge rendered at 4x

**Files:**
- Modify: `flight_display.py` (`_monogram_badge`, line ~538-552; imports line ~10-16)
- Test: `tests/test_flightwall_style.py` (extend `TestAirlineLogos`)

**Interfaces:**
- Consumes: `aa_text.find_ttf`, `Fonts.AA_TTF_CANDIDATES`.
- Produces: `_monogram_badge` keeps its exact signature and 20x20 RGB return; only rendering quality changes.

- [ ] **Step 1: Write the failing tests**

Add to `TestAirlineLogos` in `tests/test_flightwall_style.py`:

```python
    def test_monogram_is_antialiased(self) -> None:
        d = self._display()
        badge = d._monogram_badge('XYZ999')

        assert badge.size == (20, 20)
        # Supersampled render blends many colors; the old hard render
        # produced only a handful
        assert len(set(badge.getdata())) > 20

    def test_monogram_corners_rounded(self) -> None:
        badge = self._display()._monogram_badge('XYZ999')
        r, g, b = badge.getpixel((0, 0))

        assert r + g + b < 90  # corner outside the rounded rect: near-black
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_flightwall_style.py::TestAirlineLogos -v`
Expected: the two new tests FAIL (the `load_default` badge has few distinct colors and square corners); the four existing logo tests still pass.

- [ ] **Step 3: Implement the supersampled badge**

In `flight_display.py`, add to the imports (after the `route_cache` import):

```python
from aa_text import find_ttf
```

and add `Fonts` to the existing `scoreboard_config` import line.

Replace `_monogram_badge` (keep the docstring style):

```python
    def _monogram_badge(self, callsign: str) -> Image.Image:
        """20x20 fallback badge: brand-ish colored square + 2-letter code"""
        prefix = ((callsign or '').strip().upper() + 'ZZZ')[:3]
        code = self.ICAO_TO_IATA.get(prefix, prefix[:2])[:2]
        color = self.MONOGRAM_COLORS[
            sum(ord(c) for c in prefix) % len(self.MONOGRAM_COLORS)]
        ttf_path = find_ttf(Fonts.AA_TTF_CANDIDATES)
        if ttf_path:
            # Draw at 4x and downsample: smooth letters and corners
            big = Image.new('RGB', (80, 80))
            draw = ImageDraw.Draw(big)
            try:
                draw.rounded_rectangle((0, 0, 79, 79), radius=20, fill=color)
            except AttributeError:  # Pillow < 8.2
                draw.rectangle((0, 0, 79, 79), fill=color)
            font = ImageFont.truetype(ttf_path, 44)
            draw.text((40, 38), code, font=font, anchor='mm',
                      fill=(255, 255, 255))
            return big.resize((20, 20), Image.LANCZOS)
        # No TTF anywhere: the old crunchy-but-working badge
        img = Image.new('RGB', (20, 20))
        draw = ImageDraw.Draw(img)
        try:
            draw.rounded_rectangle((0, 0, 19, 19), radius=5, fill=color)
        except AttributeError:  # Pillow < 8.2
            draw.rectangle((0, 0, 19, 19), fill=color)
        draw.text((4, 4), code, font=ImageFont.load_default(),
                  fill=(255, 255, 255))
        return img
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_flightwall_style.py -v`
Expected: all PASS (including `test_monogram_is_deterministic` and `test_unknown_airline_gets_cached_monogram`, which must keep passing unchanged)

- [ ] **Step 5: Commit**

```bash
git add flight_display.py tests/test_flightwall_style.py
git commit -m "Render monogram badge supersampled at 4x"
```

---

### Task 6: Full verification

**Files:** none new.

- [ ] **Step 1: Run the entire suite**

Run: `python3 -m pytest tests/ -v`
Expected: everything passes. Pay attention to `test_setup_display.py` and any other test importing `scoreboard_manager` — the new `__init__` lines must not break them.

- [ ] **Step 2: Compile gate (mirrors `auto_update.sh`)**

Run: `python3 -m py_compile aa_text.py scoreboard_manager.py flight_display.py scoreboard_config.py`
Expected: silent success.

- [ ] **Step 3: Report done**

Deployment is by `git push` (the Pi's nightly `marquee-update.timer` pulls main and reboots), or an immediate scp + `sudo reboot` if the user wants to see it tonight — ask the user which. Final visual sign-off (letter brightness, size, baseline alignment) happens on the hardware; `Fonts.AA_TEXT_SIZE` and the DejaVu size `44` in the badge are the tuning knobs.

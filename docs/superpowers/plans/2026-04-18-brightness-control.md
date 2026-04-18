# Brightness Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a brightness slider (10-100%, default 100%) to the admin web panel so the user can tune LED matrix output level from the browser, with the value persisted to `/home/pi/config.json` and applied at scoreboard startup.

**Architecture:** Add three constants to `scoreboard_config.py`, a small `_load_brightness()` helper to `ScoreboardManager` that reads `/home/pi/config.json` with clamping and fallback, and wire up a new "Display Settings" section at the top of the Display Config tab in `wifi_config_server.py`. The Flask server clamps on save; the matrix setup clamps on load — defense in depth for a setting a user can hand-edit.

**Tech Stack:** Python 3.9+, Flask (existing), rpi-rgb-led-matrix (existing), pytest (existing test harness mocks `rgbmatrix`).

**Reference spec:** `docs/superpowers/specs/2026-04-18-brightness-control-design.md`

---

## File Structure

**Modified:**
- `scoreboard_config.py` — add `DisplayConfig.BRIGHTNESS_DEFAULT`, `BRIGHTNESS_MIN`, `BRIGHTNESS_MAX` constants
- `scoreboard_manager.py` — add `_load_brightness()` method, call it in `_setup_matrix()`
- `wifi_config_server.py` — add `'brightness': 100` to default config; add "Display Settings" HTML section with slider; wire up JS load/save; clamp in `/save_config` route

**Created:**
- `tests/test_brightness.py` — unit tests for `_load_brightness()` helper

**Config file schema change (`/home/pi/config.json`):**
New optional integer key `brightness` in range `[10, 100]`. Absent = 100.

---

## Task 1: Add brightness constants to config

**Files:**
- Modify: `scoreboard_config.py`

- [ ] **Step 1: Open `scoreboard_config.py` and locate the `DisplayConfig` class (around lines 15-21)**

Current content:
```python
class DisplayConfig:
    """LED Matrix display configuration"""
    MATRIX_ROWS: int = 48
    MATRIX_COLS: int = 96
    CHAIN_LENGTH: int = 1
    PARALLEL: int = 1
    HARDWARE_MAPPING: str = 'regular'
```

- [ ] **Step 2: Add three brightness constants to `DisplayConfig`**

Replace the class with:
```python
class DisplayConfig:
    """LED Matrix display configuration"""
    MATRIX_ROWS: int = 48
    MATRIX_COLS: int = 96
    CHAIN_LENGTH: int = 1
    PARALLEL: int = 1
    HARDWARE_MAPPING: str = 'regular'
    BRIGHTNESS_DEFAULT: int = 100
    BRIGHTNESS_MIN: int = 10
    BRIGHTNESS_MAX: int = 100
```

- [ ] **Step 3: Commit**

```bash
git add scoreboard_config.py
git commit -m "Add brightness constants to DisplayConfig"
```

---

## Task 2: Write failing test for `_load_brightness()`

**Files:**
- Create: `tests/test_brightness.py`

- [ ] **Step 1: Create `tests/test_brightness.py` with the full test suite**

The test file patches `CONFIG_PATH` to a temporary file and verifies `ScoreboardManager._load_brightness()` returns the right integer for each scenario. The `rgbmatrix` module is already auto-mocked by `tests/conftest.py`, but `ScoreboardManager.__init__` also creates the matrix and loads fonts — we don't want to run that. The helper is designed to be callable as a static method on an instance, so we instantiate with `MagicMock` for self.

Full content:
```python
"""Tests for ScoreboardManager._load_brightness() helper."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from scoreboard_manager import ScoreboardManager


class TestLoadBrightness:
    def test_returns_default_when_config_missing(self, tmp_path):
        missing = tmp_path / "config.json"
        with patch("scoreboard_manager.BRIGHTNESS_CONFIG_PATH", str(missing)):
            result = ScoreboardManager._load_brightness(MagicMock())
        assert result == 100

    def test_returns_value_from_config(self, tmp_path):
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"brightness": 50}))
        with patch("scoreboard_manager.BRIGHTNESS_CONFIG_PATH", str(cfg)):
            result = ScoreboardManager._load_brightness(MagicMock())
        assert result == 50

    def test_clamps_below_minimum(self, tmp_path):
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"brightness": 3}))
        with patch("scoreboard_manager.BRIGHTNESS_CONFIG_PATH", str(cfg)):
            result = ScoreboardManager._load_brightness(MagicMock())
        assert result == 10

    def test_clamps_above_maximum(self, tmp_path):
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"brightness": 500}))
        with patch("scoreboard_manager.BRIGHTNESS_CONFIG_PATH", str(cfg)):
            result = ScoreboardManager._load_brightness(MagicMock())
        assert result == 100

    def test_returns_default_when_key_missing(self, tmp_path):
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"zip_code": "60613"}))
        with patch("scoreboard_manager.BRIGHTNESS_CONFIG_PATH", str(cfg)):
            result = ScoreboardManager._load_brightness(MagicMock())
        assert result == 100

    def test_returns_default_when_value_not_numeric(self, tmp_path):
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"brightness": "bright"}))
        with patch("scoreboard_manager.BRIGHTNESS_CONFIG_PATH", str(cfg)):
            result = ScoreboardManager._load_brightness(MagicMock())
        assert result == 100

    def test_returns_default_when_config_malformed(self, tmp_path):
        cfg = tmp_path / "config.json"
        cfg.write_text("{not valid json")
        with patch("scoreboard_manager.BRIGHTNESS_CONFIG_PATH", str(cfg)):
            result = ScoreboardManager._load_brightness(MagicMock())
        assert result == 100
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_brightness.py -v`
Expected: All 7 tests FAIL with `AttributeError: type object 'ScoreboardManager' has no attribute '_load_brightness'` (or `AttributeError` for the patched `BRIGHTNESS_CONFIG_PATH` module attribute).

- [ ] **Step 3: Commit**

```bash
git add tests/test_brightness.py
git commit -m "Add failing tests for _load_brightness helper"
```

---

## Task 3: Implement `_load_brightness()` and apply it to the matrix

**Files:**
- Modify: `scoreboard_manager.py`

- [ ] **Step 1: Open `scoreboard_manager.py` and review the top-of-file imports (lines 1-14)**

Current imports:
```python
from __future__ import annotations

import pendulum
import time
import statsapi
from PIL import Image
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
from scoreboard_config import (
    DisplayConfig, TeamConfig, Colors, Positions, Fonts, GameConfig, RGBColor
)
from typing import Any
from retry import retry_api_call
```

- [ ] **Step 2: Add `json` import and a module-level `BRIGHTNESS_CONFIG_PATH` constant**

After the existing imports, add:
```python
import json

# Config file location for runtime settings. Module-level so tests can patch it.
BRIGHTNESS_CONFIG_PATH = '/home/pi/config.json'
```

Place these right after `from retry import retry_api_call` (line 14).

- [ ] **Step 3: Add the `_load_brightness()` method to `ScoreboardManager`**

Locate `_setup_matrix()` (currently around lines 35-43). Add a new method directly above it:
```python
    def _load_brightness(self) -> int:
        """
        Load brightness percentage from config.json.

        Returns an int in [BRIGHTNESS_MIN, BRIGHTNESS_MAX]. Falls back to
        BRIGHTNESS_DEFAULT if the file is missing, malformed, or the value is
        not a valid integer.
        """
        try:
            with open(BRIGHTNESS_CONFIG_PATH, 'r') as f:
                config = json.load(f)
            raw = config.get('brightness', DisplayConfig.BRIGHTNESS_DEFAULT)
            value = int(raw)
        except (FileNotFoundError, json.JSONDecodeError, ValueError, TypeError):
            return DisplayConfig.BRIGHTNESS_DEFAULT
        return max(
            DisplayConfig.BRIGHTNESS_MIN,
            min(DisplayConfig.BRIGHTNESS_MAX, value)
        )
```

- [ ] **Step 4: Use the loaded brightness in `_setup_matrix()`**

Current `_setup_matrix()`:
```python
    def _setup_matrix(self) -> RGBMatrix:
        """Configure and initialize the RGB matrix"""
        options = RGBMatrixOptions()
        options.rows = DisplayConfig.MATRIX_ROWS
        options.cols = DisplayConfig.MATRIX_COLS
        options.chain_length = DisplayConfig.CHAIN_LENGTH
        options.parallel = DisplayConfig.PARALLEL
        options.hardware_mapping = DisplayConfig.HARDWARE_MAPPING
        return RGBMatrix(options=options)
```

Replace with:
```python
    def _setup_matrix(self) -> RGBMatrix:
        """Configure and initialize the RGB matrix"""
        options = RGBMatrixOptions()
        options.rows = DisplayConfig.MATRIX_ROWS
        options.cols = DisplayConfig.MATRIX_COLS
        options.chain_length = DisplayConfig.CHAIN_LENGTH
        options.parallel = DisplayConfig.PARALLEL
        options.hardware_mapping = DisplayConfig.HARDWARE_MAPPING
        options.brightness = self._load_brightness()
        return RGBMatrix(options=options)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_brightness.py -v`
Expected: All 7 tests PASS.

- [ ] **Step 6: Run the full test suite to confirm nothing regressed**

Run: `pytest tests/ -v`
Expected: All tests pass (including the pre-existing `test_setup_display.py`, `test_core_logic.py`, `test_route_cache.py`, `test_adsb_lol_source.py`).

- [ ] **Step 7: Commit**

```bash
git add scoreboard_manager.py
git commit -m "Load brightness from config.json and apply to RGBMatrixOptions"
```

---

## Task 4: Add `brightness` to admin server default config and save handler

**Files:**
- Modify: `wifi_config_server.py`

- [ ] **Step 1: Add `brightness` key to `default_config` in `load_config()`**

Locate the `default_config` dict in `load_config()` (starts around line 109). Find the line:
```python
        'airlabs_api_key': ''
    }
```

Replace it with:
```python
        'airlabs_api_key': '',
        'brightness': 100
    }
```

- [ ] **Step 2: Accept and clamp `brightness` in the `/save_config` route**

Locate the `save_config_route()` function's `current_config.update({...})` call (starts around line 1572). Find the line:
```python
            'airlabs_api_key': data.get('airlabs_api_key', '')
        })
```

Replace with:
```python
            'airlabs_api_key': data.get('airlabs_api_key', ''),
            'brightness': max(10, min(100, int(data.get('brightness', 100))))
        })
```

Note: wrapping in `int()` converts JS-side numbers/strings to int; `max(10, min(100, ...))` clamps to the allowed range. If `int()` raises (e.g., garbage string), the whole `/save_config` route already has a top-level `except Exception` that returns `{'success': False, 'message': str(e)}`, which is acceptable — the client slider cannot produce garbage.

- [ ] **Step 3: Commit**

```bash
git add wifi_config_server.py
git commit -m "Accept and clamp brightness in admin save_config route"
```

---

## Task 5: Add the brightness slider to the admin UI

**Files:**
- Modify: `wifi_config_server.py`

- [ ] **Step 1: Add the "Display Settings" HTML section at the top of the Display Config tab**

Locate the Display Config tab opening (around line 517):
```html
        <div id="config-tab" class="tab-content">
            <h2>Display Configuration</h2>
            
            <div class="form-group">
                <label for="display_mode">Display Mode:</label>
```

Insert a new section between `<h2>Display Configuration</h2>` and the existing `<div class="form-group">` for `display_mode`. The replacement:
```html
        <div id="config-tab" class="tab-content">
            <h2>Display Configuration</h2>

            <div class="scroll-speeds-section">
                <h4>Display Settings</h4>
                <div class="speed-control">
                    <label>Brightness:</label>
                    <input type="range" class="speed-slider" id="brightness" min="10" max="100" value="100">
                    <span class="speed-value" id="brightness_val">100%</span>
                </div>
                <p class="help-text" style="margin-top: 8px;">Controls LED matrix brightness (10% = dim, 100% = full). Restart the service for changes to take effect.</p>
            </div>

            <div class="form-group">
                <label for="display_mode">Display Mode:</label>
```

This reuses the existing `.scroll-speeds-section`, `.speed-control`, `.speed-slider`, and `.speed-value` CSS classes for visual consistency with the scroll-speed sliders.

- [ ] **Step 2: Load the saved brightness value on page load**

Locate `window.onload` (around line 883). Find the line:
```javascript
            document.getElementById('flights_between_displays').checked = config.flights_between_displays === true;
```

Immediately after that line, add:
```javascript

            // Load brightness setting
            const brightnessSlider = document.getElementById('brightness');
            const brightnessVal = document.getElementById('brightness_val');
            const brightnessValue = config.brightness != null ? config.brightness : 100;
            brightnessSlider.value = brightnessValue;
            brightnessVal.textContent = brightnessValue + '%';
            brightnessSlider.addEventListener('input', function() {
                brightnessVal.textContent = this.value + '%';
            });
```

- [ ] **Step 3: Include brightness in the `saveConfig()` payload**

Locate the `saveConfig()` function's `config` object (around line 1098). Find the line:
```javascript
                airlabs_api_key: document.getElementById('airlabs_api_key').value
            };
```

Replace with:
```javascript
                airlabs_api_key: document.getElementById('airlabs_api_key').value,
                brightness: parseInt(document.getElementById('brightness').value)
            };
```

- [ ] **Step 4: Manually sanity-check the HTML by rendering the template**

Since this is pure template/JS, there's no Python test. Run a quick syntax check by importing the module:

Run: `python3 -c "import wifi_config_server; print('OK')"`
Expected: `OK` (no syntax error).

- [ ] **Step 5: Run the full test suite once more**

Run: `pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add wifi_config_server.py
git commit -m "Add brightness slider to admin Display Config tab"
```

---

## Task 6: Manual verification on Pi hardware

**Not code — record results below.**

- [ ] **Step 1: Deploy to the Pi**

Per `memory/deployment.md`: scp the three modified files and the new test file to `cubsmarquee-one` (192.168.4.244), then reboot.

```bash
scp scoreboard_config.py scoreboard_manager.py wifi_config_server.py pi@192.168.4.244:/home/pi/cubsmarquee/
scp tests/test_brightness.py pi@192.168.4.244:/home/pi/cubsmarquee/tests/
ssh pi@192.168.4.244 "sudo reboot"
```

Wait ~2 minutes for reboot.

- [ ] **Step 2: Confirm the admin page shows the Brightness slider**

Open `http://cubsmarquee.local/admin` → Display Config tab. Expected: a "Display Settings" card at the top with a Brightness slider reading "100%".

- [ ] **Step 3: Verify dimming works**

Drag the Brightness slider to 30, click Save Configuration, then on the System tab (or via SSH) run `sudo reboot`. After reboot, confirm the LED matrix is visibly dimmer.

- [ ] **Step 4: Verify restoring to 100% works**

Set the slider back to 100, save, reboot. Confirm the matrix returns to full brightness.

- [ ] **Step 5: Verify fallback when key is missing**

SSH to Pi and hand-edit `/home/pi/config.json` to remove the `brightness` key. Reboot. Confirm matrix runs at 100% (no errors in `/home/pi/scoreboard_logs/scoreboard.log`).

---

## Self-Review Notes

- Spec coverage: every bullet in the spec's "Technical Design" and "Edge cases" maps to a task (constants → Task 1, `_load_brightness` → Task 2-3, admin save → Task 4, admin UI → Task 5, default fallback + clamping + non-numeric handling → covered by tests in Task 2). Manual test plan from the spec → Task 6.
- Placeholder scan: no TBDs, all code blocks complete.
- Type consistency: `brightness` is an `int` everywhere (Python int, JS `parseInt`, clamped on both sides). Constant names (`BRIGHTNESS_DEFAULT`, `BRIGHTNESS_MIN`, `BRIGHTNESS_MAX`) match between Task 1 definition and Task 3 usage. Module-level `BRIGHTNESS_CONFIG_PATH` name is consistent between Task 2 (test patches) and Task 3 (definition).

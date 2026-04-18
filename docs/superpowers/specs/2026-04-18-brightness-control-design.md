# Brightness Control Design

**Date:** 2026-04-18
**Status:** Draft

## Overview

Add a brightness slider to the admin web panel so the LED matrix output level can be tuned without recompiling or editing files. The LED matrix is often uncomfortably bright in a dim room; currently there is no user-facing way to dim it.

## Goals

- Let the user set LED matrix brightness from the admin panel (`http://<hostname>.local/admin`).
- Persist the value in `/home/pi/config.json` alongside existing settings.
- Apply the value on service restart, matching the behavior of every other setting in the Display Config tab.

## Non-Goals

- Live brightness updates without a restart. The scoreboard process and the Flask admin server are separate; adding file-watching or IPC for a single infrequent setting is out of scope.
- Scheduled dimming (e.g., auto-dim at night). Can be a future feature.
- Per-display-type brightness overrides.

## User-Facing Design

A new "Display Settings" section appears at the top of the **Display Config** tab, above the Display Mode dropdown.

The section contains one control:

- **Brightness** — a slider from 10 to 100 (percent), default 100, with the current value shown next to it. Visual style matches the existing scroll-speed sliders.

The save flow is unchanged: clicking **Save Configuration** writes all Display Config fields (including brightness) to `/home/pi/config.json`. The existing "Restart the service for changes to take effect" status message covers brightness too.

### Range and default

- Range: **10-100**. Below 10 the matrix can look broken (barely visible, easily mistaken for a hardware failure). 100 is the library maximum.
- Default: **100**. Preserves current behavior for existing installs — if `brightness` is absent from `config.json`, nothing changes.

## Technical Design

### Component changes

1. **`scoreboard_config.py`** — add a default constant for documentation:
   ```python
   class DisplayConfig:
       # ... existing fields ...
       BRIGHTNESS_DEFAULT: int = 100
       BRIGHTNESS_MIN: int = 10
       BRIGHTNESS_MAX: int = 100
   ```

2. **`scoreboard_manager.py`** — in `_setup_matrix()`, read `brightness` from `/home/pi/config.json`, clamp to `[BRIGHTNESS_MIN, BRIGHTNESS_MAX]`, and set it on `RGBMatrixOptions`:
   ```python
   options.brightness = self._load_brightness()
   ```
   Where `_load_brightness()`:
   - Reads `/home/pi/config.json`.
   - Returns `int(config.get('brightness', 100))`, clamped.
   - On any error (file missing, parse failure, non-numeric value), returns `BRIGHTNESS_DEFAULT` and logs a warning.

3. **`wifi_config_server.py`** — three edits:
   - Add `'brightness': 100` to `default_config` in `load_config()`.
   - In the HTML template, add a "Display Settings" section before the Display Mode form-group, containing a slider identical in style to the scroll-speed sliders (reusing `.speed-control`, `.speed-slider`, `.speed-value` classes).
   - In the `window.onload` JS, load the slider value from config and wire its `input` event to update the readout.
   - In `saveConfig()` JS, include `brightness: parseInt(document.getElementById('brightness').value)` in the payload.
   - In `/save_config`, accept `brightness` and clamp server-side: `max(10, min(100, int(data.get('brightness', 100))))`.

### Data flow

```
[Admin UI slider]
       |
       v  POST /save_config
[Flask: wifi_config_server]
       |
       v  write
[/home/pi/config.json]
       |
       v  (user clicks Restart Service or Reboot Pi)
[scoreboard_manager._setup_matrix()]
       |
       v  read, clamp
[RGBMatrixOptions.brightness = value]
       |
       v
[RGBMatrix]
```

### Edge cases

| Case | Behavior |
|------|----------|
| `brightness` key missing from config.json | Default to 100 |
| Value < 10 or > 100 | Clamp to range (both server on save, and matrix setup on load) |
| Non-integer value (string, null, etc.) | Log warning, default to 100 |
| config.json missing or unreadable at matrix setup | Log warning, default to 100 |

### Testing

- **Unit**: Add a test in `tests/` that patches `open()` with various config contents (missing key, out-of-range, non-numeric, valid) and asserts `_load_brightness()` returns the expected clamped integer.
- **Manual on hardware**: Set slider to 10, 50, 100, verify visible brightness changes after restart. Confirm fallback to 100 when `brightness` key is removed from config.json.

## Open Questions

None.

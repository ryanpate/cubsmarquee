# Cubs LED Marquee

A real-time sports display system that projects Chicago Cubs baseball games, off-season content, and weather information onto a 96x48 pixel RGB LED matrix display running on a Raspberry Pi.

## Quick Start

```bash
# Run the scoreboard
sudo python3 main.py

# Or use the launch script (includes connectivity checks)
./launch_scoreboard.sh

# Start as a service
sudo systemctl start cubs-scoreboard
```

## Project Structure

### Core Application
| File | Purpose |
|------|---------|
| `main.py` | Entry point, orchestrates game cycles and mode switching |
| `scoreboard_manager.py` | LED matrix control, API integration, image/font loading |
| `game_state_handler.py` | Pre-game displays, standings, warmup, delay status |
| `live_game_handler.py` | Live game display with scores, bases, innings, batter info |
| `off_season_handler.py` | Off-season content rotation manager |
| `scoreboard_config.py` | Configuration constants (colors, positions, fonts) |
| `teams.py` | Team packs — MLB (Cubs, Cardinals) and NFL (Bears, Chiefs): identity, colors, assets, content sources incl. news keywords |

### Content Displays
| File | Purpose |
|------|---------|
| `weather_display.py` | Open-Meteo weather with animated effects (rain, snow, clouds) |
| `bears_display.py` | Chicago Bears NFL scores and game info |
| `pga_display.py` | PGA Tour leaderboard and golf facts |

### Services & Infrastructure
| File | Purpose |
|------|---------|
| `wifi_config_server.py` | Flask web admin panel at `cubsmarquee.local/admin` |
| `launch_scoreboard.sh` | Launch script with network checks and log rotation |
| `cubs-scoreboard.service` | Systemd service definition |
| `wifi-manager.service` | WiFi connectivity management service |
| `wifi-web-config.service` | Web admin panel service |
| `install_panel_v2.sh` | One-time per-Pi switch to a V2 (SM5368) panel: installs Waveshare's rgbmatrix build and sets `panel_version` |
| `auto_update.sh` | Nightly self-update from GitHub (4 AM via `marquee-update.timer`): pulls main, py_compile gate, syncs tracked files to `/home/pi/`, reboots |

### Data Files
| File | Purpose |
|------|---------|
| `cubs_facts.json` | 305+ Cubs trivia facts |
| `pga_facts.json` | PGA Tour facts and records |
| `/home/pi/config.json` | User configuration (API keys, toggles) |

### Assets
- `logos/` - MLB team logos (PNG format, sized for LED matrix)
- `fonts/` - Bitmap fonts (BDF format) for LED display
- `*.png` - Weather icons (rain, snow, clouds, etc.)
- `W.gif` - Cubs win celebration animation

## Architecture

### Display Flow
```
main.py (CubsScoreboard)
├── Check if off-season (no games in 14 days)
│   └── OffSeasonHandler.display_off_season_content()
└── process_game_cycle():
    ├── Get Cubs schedule via MLB API
    └── Route by game status:
        ├── SCHEDULED → GameStateHandler.display_no_game()
        ├── WARMUP → GameStateHandler.display_warmup()
        ├── DELAYED/POSTPONED → GameStateHandler.display_delayed/postponed()
        ├── IN PROGRESS → LiveGameHandler.display_game_on()
        └── FINAL → LiveGameHandler.display_game_over()
```

### Off-Season Content Rotation
1. Weather display with animations (2 min)
2. Bears game info - if NFL season (3 min)
3. Bears news - if available (2 min)
4. PGA leaderboard - if golf season (3 min)
5. PGA facts/news - if golf season (2 min)
6. Cubs news - if available (2 min)
7. Custom message + Cubs facts (4 min)

## Development

### Dependencies
```
rgbmatrix       # LED matrix control (Raspberry Pi GPIO)
MLB-StatsAPI    # Official MLB statistics API
requests        # HTTP requests
pendulum        # Timezone-aware date/time
Pillow          # Image processing
Flask           # Web admin panel
feedparser      # RSS feed parsing
```

### Code Quality

**Type Hints**: All core modules use Python 3.9+ type hints with `from __future__ import annotations`.

**Configuration**: All magic numbers and constants are centralized in `scoreboard_config.py`:
- `DisplayConfig` - Matrix dimensions and hardware settings
- `TeamConfig` - Team IDs and league IDs
- `Colors` - All RGB color tuples (Cubs, Bears, PGA themes)
- `Positions` - Pixel positions for UI elements
- `Fonts` - Font paths and character widths
- `GameConfig` - Timing, intervals, and display durations

**Abstract Base Class**: `DisplayHandler` in `scoreboard_config.py` provides a base class for display handlers with common utility methods like `_draw_header_stripes()` and `_center_text_x()`.

**Logging**: Centralized logging via `logger.py` with:
- Rotating file handler (5MB max, 3 backups)
- Console output for debugging
- Module-specific loggers via `get_logger("module_name")`
- Log location: `/var/log/cubs-scoreboard/scoreboard.log` (or `./scoreboard.log` fallback)

**Graceful Shutdown**: Signal handlers for SIGTERM and SIGINT ensure display is cleared on exit:
```python
from main import is_shutdown_requested
# Check in loops: if is_shutdown_requested(): break
```

**Image Caching**: Large images (marquee.png) are cached in memory at startup via `_load_marquee_image()` to avoid repeated file I/O.

### Key Patterns
- **Manager Pattern**: `ScoreboardManager` provides central LED matrix control
- **Handler Pattern**: Specialized handlers (Game, OffSeason, Weather) contain domain logic
- **Double Buffering**: Canvas swapped on vsync for smooth animations
- **API Caching**: Configurable cache intervals in `GameConfig` (30-60 min default)
- **Type Aliases**: `RGBColor` and `Position` for clarity

### Display Configuration

All display constants are in `scoreboard_config.py`:
- Matrix: 96x48 pixels (`DisplayConfig.MATRIX_COLS`, `DisplayConfig.MATRIX_ROWS`)
- Scroll speed: `GameConfig.SCROLL_SPEED` (default 0.002s)
- Scroll distance: `GameConfig.SCROLL_PIXELS` (default 1 pixel)

### Panel hardware revisions

Both revisions are HUB75 on the same 16-pin ribbon. V2 panels select a row by
clocking a bit through an SM5368 shift register (A=clock, B=enable, C=data)
rather than putting a binary row number on A/B/C, and wire the LEDs BGR.
Driving a V2 panel with V1 settings gives horizontal banding and ghosting
while the software framebuffer renders clean.

`ScoreboardManager._apply_panel_options()` applies the V2 profile only when
config.json has `panel_version: "v2"`, so V1 Pis are unaffected. V2 also needs
Waveshare's rgbmatrix build (`install_panel_v2.sh`) — upstream rejects a
`row_address_type` above 4. Passing `--led-panel-type` the way the Waveshare
docs describe does nothing from Python: that flag is expanded by the C++
argument parser, which the bindings never call.

### Color Constants (in `Colors` class)
- Cubs Blue: `Colors.CUBS_BLUE` - `(0, 51, 102)`
- Yellow: `Colors.YELLOW` - `(255, 223, 0)`
- Bears Navy: `Colors.BEARS_NAVY` - `(11, 22, 42)`
- Bears Orange: `Colors.BEARS_ORANGE` - `(200, 56, 3)`
- PGA colors: `Colors.PGA_BLUE`, `Colors.PGA_NAVY`, `Colors.PGA_GOLD`, `Colors.PGA_GREEN`

## APIs Used

- **MLB Stats API** - Game schedules, scores, lineups, play-by-play
- **Open-Meteo API** - Temperature, forecasts, and ZIP geocoding (no API key). Its `current` block is forecast-model output, not an observation, so it can report overcast during a thunderstorm — the condition shown comes from NWS instead
- **NWS API** (`api.weather.gov`) - Observed condition from the nearest METAR station; a thunder scan over stations within 40 mi; and active thunderstorm/tornado *warnings* (not watches). US only, no API key, but requires a `User-Agent`
- **RainViewer** (`api.rainviewer.com`) - Radar reflectivity at the exact coordinates, the only source that sees what is falling on *this* roof. Free tier caps zoom at 7 (~940 m/pixel); colour scheme 4 ramps blue→yellow→orange→red, magenta for snow

The current condition is resolved in order of how local the evidence is: Open-Meteo model → nearest station → radar overhead → thunder within 40 mi → active warning. Each step only overrides when it has an opinion, and every source falls back cleanly, so an outage anywhere cannot take weather off the display.

**Why this is layered:** a station is still miles away. On 2026-08-15 a storm sat over Rochester while KSPI (10 mi west) reported "Cloudy" — its `VCTS` never reaches the NWS structured `presentWeather` field, so only radar (orange pixel overhead) and the 40-mile thunder scan (KIJX, KAAA) caught it. Do not "simplify" this back to a single source.
- **ESPN API** - Bears NFL scores and PGA Tour leaderboards
- **RSS Feeds** - Cubs and Bears breaking news

## Configuration

User configuration stored at `/home/pi/config.json`:
- OpenWeather API key (optional - only the admin flight-address lookup uses it)
- Custom display message
- Feature toggles (Bears, PGA, news feeds)
- Weather location
- `team` — active team pack slug (`cubs` default, `cardinals`)
- `nfl_team` — active NFL team pack slug (`bears` default, `chiefs`)
- `nfl_preempt_mlb` — when `true`, a live NFL game takes over the display the way a live MLB game does, and MLB drops to its scheduled card (default `false`). Football season is detected from the ESPN schedule (game within -3/+14 days), not from a month range, so preseason counts like the regular season
- `panel_version` — panel hardware revision (`v1` default, `v2`); set by `install_panel_v2.sh`
- `hardware_mapping` — matrix wiring revision (`regular` default = direct to GPIO; `adafruit-hat` / `adafruit-hat-pwm` for the Adafruit bonnet). Per-Pi, since the units are not wired alike; omit to keep `DisplayConfig.HARDWARE_MAPPING`
- `gpio_slowdown` — optional matrix timing override (Pi 5: 2, Pi 4/earlier: 4). Set the **lowest value that renders clean** — higher costs refresh. Measured: cubsmarquee (Pi 4, bonnet) is clean at **3**, ghosts at 2. Too low shows as ghosting/noisy pixels, and the threshold scales with CPU clock: curing that Pi's undervoltage took it from 600 MHz to 1800 and introduced ghosting that had never appeared before (2026-08-13)
- `limit_refresh_rate_hz` — optional cap that pins the refresh rate so interrupt jitter stops reading as flicker; set below the free-running rate (measure with `show_refresh_rate`). **A cap the Pi cannot sustain causes a flickering line across the panel** — it is not a harmless no-op (cubsmarquee, 2026-08-09). Leave unset unless measured.

Access admin panel at `http://cubsmarquee.local/admin` for GUI configuration.

## Logs

Logs stored at `/home/pi/scoreboard_logs/` with automatic rotation.

View live logs:
```bash
tail -f /home/pi/scoreboard_logs/scoreboard.log
```

## Common Commands

```bash
# Check service status
sudo systemctl status cubs-scoreboard

# Restart scoreboard
sudo systemctl restart cubs-scoreboard

# View logs
sudo journalctl -u cubs-scoreboard -f

# Run diagnostics
./diagnose_connectivity.sh

# Clean up old logs
./cleanup_logs.sh
```

## Testing

Run unit tests with pytest (mocks rgbmatrix for non-Pi environments):
```bash
pytest tests/ -v
```

Test coverage includes:
- Schedule parsing and doubleheader detection
- Score calculations and win/loss detection
- Time formatting and timezone handling
- Bears ESPN API parsing
- Configuration validation
- Off-season detection logic

Manual testing on Raspberry Pi hardware required for display verification.

## Build/Deploy

1. Install dependencies: `pip install -r requirements.txt`
2. Install rgbmatrix library (requires GPIO access)
3. Configure services: Install systemd unit files
4. Set API keys in `/home/pi/config.json` or via admin panel
5. Start services: `sudo systemctl start cubs-scoreboard`

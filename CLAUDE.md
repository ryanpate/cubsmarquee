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

### Content Displays
| File | Purpose |
|------|---------|
| `weather_display.py` | Weather data with animated effects (rain, snow, clouds) |
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

### Color Constants (in `Colors` class)
- Cubs Blue: `Colors.CUBS_BLUE` - `(0, 51, 102)`
- Yellow: `Colors.YELLOW` - `(255, 223, 0)`
- Bears Navy: `Colors.BEARS_NAVY` - `(11, 22, 42)`
- Bears Orange: `Colors.BEARS_ORANGE` - `(200, 56, 3)`
- PGA colors: `Colors.PGA_BLUE`, `Colors.PGA_NAVY`, `Colors.PGA_GOLD`, `Colors.PGA_GREEN`

## APIs Used

- **MLB Stats API** - Game schedules, scores, lineups, play-by-play
- **OpenWeatherMap API** - Weather data and forecasts
- **ESPN API** - Bears NFL scores and PGA Tour leaderboards
- **RSS Feeds** - Cubs and Bears breaking news

## Configuration

User configuration stored at `/home/pi/config.json`:
- OpenWeatherMap API key
- Custom display message
- Feature toggles (Bears, PGA, news feeds)
- Weather location

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

No formal test suite. Manual testing on Raspberry Pi hardware required.

## Build/Deploy

1. Install dependencies: `pip install -r requirements.txt`
2. Install rgbmatrix library (requires GPIO access)
3. Configure services: Install systemd unit files
4. Set API keys in `/home/pi/config.json` or via admin panel
5. Start services: `sudo systemctl start cubs-scoreboard`

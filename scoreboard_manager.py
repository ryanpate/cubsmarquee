"""Main manager class for the Cubs LED Scoreboard"""

from __future__ import annotations

import pendulum
import time
import statsapi
from PIL import Image
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
from scoreboard_config import (
    DisplayConfig, TeamConfig, Colors, Positions, Fonts, GameConfig, RGBColor,
    load_user_config
)
from typing import Any
from retry import retry_api_call
import json
from logger import get_logger

# Config file location for runtime settings. Module-level so tests can patch it.
USER_CONFIG_PATH = '/home/pi/config.json'

_logger = get_logger("scoreboard")


class ScoreboardManager:
    """Manages the LED scoreboard display and game state"""

    def __init__(self) -> None:
        """Initialize the scoreboard manager"""
        self.matrix: RGBMatrix = self._setup_matrix()
        self.canvas = self.matrix.CreateFrameCanvas()
        self.fonts: dict[str, graphics.Font] = self._load_fonts()
        self.images: dict[str, Image.Image] = {}
        self.current_game: dict[str, Any] | None = None
        self.current_game_id: int | None = None
        self.current_lineup: str | None = None
        self.game_images: dict[str, Image.Image] = {}

        # Split-squad indicator (set by main.py when multiple games are active)
        self.split_squad_indicator: str = ""  # e.g., "1/2" or "2/2"
        self.split_squad_switch_time: float = 0.0  # When to switch to next game

        # Cache for the no-game-today schedule lookahead
        self._lookahead_cache: list[dict[str, Any]] | None = None
        self._lookahead_cached_at: float = 0.0

        # Runtime brightness / auto-dim state
        self._last_brightness_check: float = 0.0
        self._applied_brightness: int | None = None

    def _load_brightness(self) -> int:
        """
        Load brightness percentage from config.json.

        Returns an int in [BRIGHTNESS_MIN, BRIGHTNESS_MAX]. Falls back to
        BRIGHTNESS_DEFAULT if the file is missing, malformed, or the value is
        not a valid integer.
        """
        try:
            with open(USER_CONFIG_PATH, 'r') as f:
                config = json.load(f)
            raw = config.get('brightness', DisplayConfig.BRIGHTNESS_DEFAULT)
            value = int(raw)
        except (FileNotFoundError, json.JSONDecodeError, ValueError, TypeError) as e:
            _logger.warning(
                "Could not load brightness from %s (%s); falling back to %d",
                USER_CONFIG_PATH, e, DisplayConfig.BRIGHTNESS_DEFAULT,
            )
            return DisplayConfig.BRIGHTNESS_DEFAULT
        return max(
            DisplayConfig.BRIGHTNESS_MIN,
            min(DisplayConfig.BRIGHTNESS_MAX, value)
        )

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

    def _load_fonts(self) -> dict[str, graphics.Font]:
        """Load all required fonts"""
        fonts: dict[str, graphics.Font] = {}
        font_mapping: dict[str, str] = {
            'large_bold': Fonts.LARGE_BOLD,
            'medium_bold': Fonts.MEDIUM_BOLD,
            'standard_bold': Fonts.STANDARD_BOLD,
            'lineup': Fonts.LINEUP,
            'small_bold': Fonts.SMALL_BOLD,
            'small': Fonts.SMALL,
            'tiny_bold': Fonts.TINY_BOLD,
            'tiny': Fonts.TINY,
            'micro': Fonts.MICRO,
            'ultra_micro': Fonts.ULTRA_MICRO
        }

        for name, path in font_mapping.items():
            font = graphics.Font()
            font.LoadFont(path)
            fonts[name] = font

        return fonts
    
    def load_game_images(
        self, game_data: list[dict[str, Any]], game_index: int = 0
    ) -> dict[str, Image.Image] | None:
        """
        Load team logos and other images for the current game.

        Handles missing images gracefully by using placeholder images or
        falling back to text-only display.
        """
        try:
            gameid: int = game_data[game_index]['game_id']
            game_info: dict[str, Any] = retry_api_call(
                statsapi.get, 'game', {'gamePk': gameid}
            )

            # Determine opponent abbreviation
            opp_abv: str = 'UNK'
            for team_type in game_info['gameData']['teams']:
                team_data = game_info['gameData']['teams'][team_type]
                if team_data['abbreviation'] != 'CHC':
                    opp_abv = team_data['abbreviation']
                    break

            # Load images with individual error handling
            self.game_images = {}

            # Load Cubs logo (required)
            cubs_logo_path = './logos/cubs.png'
            try:
                self.game_images['cubs'] = Image.open(cubs_logo_path)
            except FileNotFoundError:
                print(f"Warning: Cubs logo not found at {cubs_logo_path}")
                self.game_images['cubs'] = self._create_placeholder_image()

            # Load opponent logo (fall back to placeholder)
            opp_logo_path = f'./logos/{opp_abv}.png'
            try:
                self.game_images['opponent'] = Image.open(opp_logo_path)
            except FileNotFoundError:
                print(f"Warning: Opponent logo not found at {opp_logo_path}, using placeholder")
                self.game_images['opponent'] = self._create_placeholder_image()

            # Load batting indicator (optional)
            batting_path = './baseball.png'
            try:
                self.game_images['batting'] = Image.open(batting_path)
            except FileNotFoundError:
                print(f"Warning: Batting image not found at {batting_path}")
                self.game_images['batting'] = self._create_placeholder_image(size=(8, 8))

            # Load marquee image (optional)
            marquee_path = './marquee.png'
            try:
                self.game_images['marquee'] = Image.open(marquee_path)
            except FileNotFoundError:
                print(f"Warning: Marquee image not found at {marquee_path}")
                self.game_images['marquee'] = self._create_placeholder_image()

            return self.game_images

        except Exception as e:
            print(f"Error loading game images: {e}")
            import traceback
            traceback.print_exc()
            # Return minimal placeholder set so display can continue
            return self._create_fallback_images()

    def _create_placeholder_image(
        self, size: tuple[int, int] = (16, 16), color: tuple[int, int, int] = (50, 50, 50)
    ) -> Image.Image:
        """Create a placeholder image when the real image is missing"""
        img = Image.new('RGB', size, color)
        return img

    def _create_fallback_images(self) -> dict[str, Image.Image]:
        """Create a complete set of fallback images for error recovery"""
        return {
            'cubs': self._create_placeholder_image(),
            'opponent': self._create_placeholder_image(),
            'batting': self._create_placeholder_image(size=(8, 8)),
            'marquee': self._create_placeholder_image(size=(96, 32))
        }

    def get_schedule(self) -> list[dict[str, Any]]:
        """Get the Cubs game schedule"""
        current_date = pendulum.now()
        date_string: str = current_date.format('MM/DD/YYYY')
        sched: list[dict[str, Any]] = retry_api_call(
            statsapi.schedule,
            start_date=date_string, team=TeamConfig.CUBS_TEAM_ID
        )
        if sched:
            return sched

        # No game today: look ahead with a single ranged query instead of
        # one call per day, and cache the result so off-season polling
        # doesn't hammer the API
        now = time.time()
        if (self._lookahead_cache is not None
                and now - self._lookahead_cached_at < GameConfig.SCHEDULE_UPDATE_INTERVAL):
            return self._lookahead_cache

        future: list[dict[str, Any]] = retry_api_call(
            statsapi.schedule,
            start_date=current_date.add(days=1).format('MM/DD/YYYY'),
            end_date=current_date.add(
                days=GameConfig.MAX_DAYS_TO_CHECK).format('MM/DD/YYYY'),
            team=TeamConfig.CUBS_TEAM_ID
        )

        if future:
            # Keep only the next game day (matches the old day-by-day scan)
            first_date = future[0]['game_date']
            future = [g for g in future if g['game_date'] == first_date]
        else:
            print(f"No games found in the next {GameConfig.MAX_DAYS_TO_CHECK} days")

        self._lookahead_cache = future
        self._lookahead_cached_at = now
        return future

    def get_pitchers(
        self, game_data: list[dict[str, Any]], game_index: int, gameid: int
    ) -> str:
        """Get pitcher information for the game"""
        home_pitcher: str = game_data[game_index]['home_probable_pitcher'] or 'TBD'
        away_pitcher: str = game_data[game_index]['away_probable_pitcher'] or 'TBD'

        game_info: dict[str, Any] = retry_api_call(
            statsapi.get, 'game', {'gamePk': gameid}
        )

        if game_data[game_index]['home_id'] == TeamConfig.CUBS_TEAM_ID:
            away_team: str = game_info['gameData']['teams']['away']['teamName']
            return f'Cubs Pitcher: {home_pitcher}    {away_team} Pitcher: {away_pitcher}'
        else:
            home_team: str = game_info['gameData']['teams']['home']['teamName']
            return f'Cubs Pitcher: {away_pitcher}    {home_team} Pitcher: {home_pitcher}'

    def get_lineup(self, gameid: int) -> str:
        """Get the lineup for both teams"""
        try:
            game_info: dict[str, Any] = retry_api_call(
                statsapi.get, 'game', {'gamePk': gameid}
            )
            boxscore: dict[str, Any] = game_info['liveData']['boxscore']

            lineup: list[str] = []

            home_team: str = boxscore['teams']['home']['team']['name']
            home_batters: list[int] = boxscore['teams']['home']['batters']
            away_team: str = boxscore['teams']['away']['team']['name']
            away_batters: list[int] = boxscore['teams']['away']['batters']

            # Fetch every batter in one batched call instead of one call
            # per player (the people endpoint accepts comma-separated IDs)
            players_by_id: dict[int, dict[str, Any]] = {}
            all_batters = home_batters + away_batters
            if all_batters:
                people = retry_api_call(
                    statsapi.get, 'people',
                    {'personIds': ','.join(str(pid) for pid in all_batters)}
                )['people']
                players_by_id = {p['id']: p for p in people}

            # Process home team
            home_lineup: str = f"{home_team} - "
            for player_id in home_batters:
                player_info = players_by_id.get(player_id)
                if not player_info:
                    continue
                last_name: str = player_info['lastName']
                position: str = player_info['primaryPosition']['abbreviation']
                home_lineup += f"{position}:{last_name} "

            lineup.append(home_lineup)

            # Process away team
            away_lineup: str = f"  {away_team} - "
            for player_id in away_batters:
                player_info = players_by_id.get(player_id)
                if not player_info:
                    continue
                last_name = player_info['lastName']
                position = player_info['primaryPosition']['abbreviation']
                away_lineup += f"{position}:{last_name} "

            lineup.append(away_lineup)

            return ''.join(lineup)

        except Exception as e:
            print(f"Error getting lineup: {e}")
            return "Lineup not available"

    def format_game_time(
        self, game_data: list[dict[str, Any]], game_index: int
    ) -> str:
        """
        Format the game time for display in local Chicago time.

        Uses pendulum for proper timezone handling including DST.
        """
        try:
            # Get the full datetime string from game data
            game_datetime_str: str = game_data[game_index]['game_datetime']

            # Parse the ISO datetime string (UTC) using pendulum
            game_datetime = pendulum.parse(game_datetime_str)

            # Convert to Chicago timezone (handles CST/CDT automatically)
            chicago_time = game_datetime.in_timezone('America/Chicago')

            # Format as 12-hour time (e.g., "7:05")
            return chicago_time.format('h:mm')

        except Exception as e:
            print(f"Error formatting game time: {e}")
            # Fallback to raw time extraction if parsing fails
            try:
                game_time: str = game_data[game_index]['game_datetime'][11:16]
                return game_time
            except Exception:
                return "TBD"

    def clear_canvas(self) -> None:
        """Clear the canvas"""
        self.canvas.Clear()

    @staticmethod
    def _parse_hhmm(value: str) -> int:
        """Parse 'HH:MM' into minutes since midnight (raises ValueError)"""
        hours, minutes = value.split(':')
        hours, minutes = int(hours), int(minutes)
        if not (0 <= hours <= 23 and 0 <= minutes <= 59):
            raise ValueError(f"Invalid time: {value}")
        return hours * 60 + minutes

    @staticmethod
    def _is_dim_time(now_minute: int, start_minute: int, end_minute: int) -> bool:
        """True if now is inside the dim window (window may wrap midnight)"""
        if start_minute == end_minute:
            return False
        if start_minute < end_minute:
            return start_minute <= now_minute < end_minute
        return now_minute >= start_minute or now_minute < end_minute

    def get_effective_brightness(self) -> int:
        """Base brightness, or the dimmed value inside the auto-dim window"""
        brightness = self._load_brightness()
        config = load_user_config()
        if not config.get('dim_enabled'):
            return brightness

        try:
            start = self._parse_hhmm(config.get('dim_start', '22:00'))
            end = self._parse_hhmm(config.get('dim_end', '07:00'))
            dim = int(config.get('dim_brightness', 30))
        except (ValueError, TypeError, AttributeError):
            return brightness

        now = pendulum.now()
        if self._is_dim_time(now.hour * 60 + now.minute, start, end):
            dim = max(DisplayConfig.BRIGHTNESS_MIN,
                      min(DisplayConfig.BRIGHTNESS_MAX, dim))
            return min(dim, brightness)
        return brightness

    def update_brightness(self) -> None:
        """Apply brightness/auto-dim at runtime (throttled; called per frame)"""
        now = time.time()
        if now - self._last_brightness_check < 10:
            return
        self._last_brightness_check = now

        brightness = self.get_effective_brightness()
        if brightness != self._applied_brightness:
            self.matrix.brightness = brightness
            self._applied_brightness = brightness
            _logger.info("Brightness set to %d%%", brightness)

    def swap_canvas(self) -> None:
        """Swap the canvas buffer"""
        self.update_brightness()
        self.canvas = self.matrix.SwapOnVSync(self.canvas)

    def draw_text(
        self, font_name: str, x: int, y: int, color_tuple: RGBColor, text: str
    ) -> None:
        """Draw text on the canvas"""
        font = self.fonts.get(font_name)
        if not font:
            print(f"Font {font_name} not found")
            return

        color = graphics.Color(*color_tuple)
        graphics.DrawText(self.canvas, font, x, y, color, text)

    def draw_pixel(self, x: int, y: int, r: int, g: int, b: int) -> None:
        """Draw a single pixel"""
        self.canvas.SetPixel(x, y, r, g, b)

    def fill_canvas(self, r: int, g: int, b: int) -> None:
        """Fill the entire canvas with a color"""
        self.canvas.Fill(r, g, b)
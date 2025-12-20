"""Main manager class for the Cubs LED Scoreboard"""

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

    def _setup_matrix(self) -> RGBMatrix:
        """Configure and initialize the RGB matrix"""
        options = RGBMatrixOptions()
        options.rows = DisplayConfig.MATRIX_ROWS
        options.cols = DisplayConfig.MATRIX_COLS
        options.chain_length = DisplayConfig.CHAIN_LENGTH
        options.parallel = DisplayConfig.PARALLEL
        options.hardware_mapping = DisplayConfig.HARDWARE_MAPPING
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
        """Load team logos and other images for the current game"""
        try:
            gameid: int = game_data[game_index]['game_id']
            game_info: dict[str, Any] = statsapi.get('game', {'gamePk': gameid})

            # Determine opponent abbreviation
            opp_abv: str = 'UNK'
            for team_type in game_info['gameData']['teams']:
                team_data = game_info['gameData']['teams'][team_type]
                if team_data['abbreviation'] != 'CHC':
                    opp_abv = team_data['abbreviation']
                    break

            # Load images
            self.game_images = {
                'cubs': Image.open('./logos/cubs.png'),
                'opponent': Image.open(f'./logos/{opp_abv}.png'),
                'batting': Image.open('./baseball.png'),
                'marquee': Image.open('./marquee.png')
            }

            return self.game_images

        except Exception as e:
            print(f"Error loading game images: {e}")
            return None

    def get_schedule(self) -> list[dict[str, Any]]:
        """Get the Cubs game schedule"""
        current_date = pendulum.now()
        date_string: str = current_date.format('MM/DD/YYYY')
        sched: list[dict[str, Any]] = statsapi.schedule(
            start_date=date_string, team=TeamConfig.CUBS_TEAM_ID
        )

        # Keep checking future dates until we find a game
        days_ahead: int = 0
        while not sched and days_ahead < GameConfig.MAX_DAYS_TO_CHECK:
            days_ahead += 1
            next_date = current_date.add(days=days_ahead)
            date_string = next_date.format('MM/DD/YYYY')
            sched = statsapi.schedule(
                start_date=date_string, team=TeamConfig.CUBS_TEAM_ID
            )

        if not sched:
            print(f"No games found in the next {GameConfig.MAX_DAYS_TO_CHECK} days")

        return sched

    def get_pitchers(
        self, game_data: list[dict[str, Any]], game_index: int, gameid: int
    ) -> str:
        """Get pitcher information for the game"""
        home_pitcher: str = game_data[game_index]['home_probable_pitcher'] or 'TBD'
        away_pitcher: str = game_data[game_index]['away_probable_pitcher'] or 'TBD'

        game_info: dict[str, Any] = statsapi.get('game', {'gamePk': gameid})

        if game_data[game_index]['home_id'] == TeamConfig.CUBS_TEAM_ID:
            away_team: str = game_info['gameData']['teams']['away']['teamName']
            return f'Cubs Pitcher: {home_pitcher}    {away_team} Pitcher: {away_pitcher}'
        else:
            home_team: str = game_info['gameData']['teams']['home']['teamName']
            return f'Cubs Pitcher: {away_pitcher}    {home_team} Pitcher: {home_pitcher}'

    def get_lineup(self, gameid: int) -> str:
        """Get the lineup for both teams"""
        try:
            game_info: dict[str, Any] = statsapi.get('game', {'gamePk': gameid})
            boxscore: dict[str, Any] = game_info['liveData']['boxscore']

            lineup: list[str] = []

            # Process home team
            home_team: str = boxscore['teams']['home']['team']['name']
            home_batters: list[int] = boxscore['teams']['home']['batters']
            home_lineup: str = f"{home_team} - "

            for player_id in home_batters:
                player_info = statsapi.get('people', {'personIds': player_id})['people'][0]
                last_name: str = player_info['lastName']
                position: str = player_info['primaryPosition']['abbreviation']
                home_lineup += f"{position}:{last_name} "

            lineup.append(home_lineup)

            # Process away team
            away_team: str = boxscore['teams']['away']['team']['name']
            away_batters: list[int] = boxscore['teams']['away']['batters']
            away_lineup: str = f"  {away_team} - "

            for player_id in away_batters:
                player_info = statsapi.get('people', {'personIds': player_id})['people'][0]
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
        """Format the game time for display"""
        game_time: str = game_data[game_index]['game_datetime'][-9:19]

        # Handle midnight
        if game_time[:2] == '00':
            game_time = '24:' + game_time[3:]

        # Convert to local time (CST/CDT - assuming UTC-5)
        hour: int = int(game_time[:2])
        if hour - 5 < 0:
            hour = hour + 7
        else:
            hour = hour - 5

        # Convert to 12-hour format
        if hour > 12:
            hour = hour - 12

        return f"{hour}{game_time[2:5]}"

    def clear_canvas(self) -> None:
        """Clear the canvas"""
        self.canvas.Clear()

    def swap_canvas(self) -> None:
        """Swap the canvas buffer"""
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
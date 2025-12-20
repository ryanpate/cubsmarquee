"""Configuration and constants for the Cubs LED Scoreboard"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scoreboard_manager import ScoreboardManager

# Type aliases for clarity
RGBColor = tuple[int, int, int]
Position = tuple[int, int]


class DisplayConfig:
    """LED Matrix display configuration"""
    MATRIX_ROWS: int = 48
    MATRIX_COLS: int = 96
    CHAIN_LENGTH: int = 1
    PARALLEL: int = 1
    HARDWARE_MAPPING: str = 'regular'


class TeamConfig:
    """Team-specific configuration"""
    CUBS_TEAM_ID: int = 112
    # MLB League IDs
    NL_LEAGUE_ID: int = 104
    AL_LEAGUE_ID: int = 103


class Colors:
    """RGB color definitions"""
    WHITE: RGBColor = (255, 255, 255)
    BLACK: RGBColor = (0, 0, 0)
    YELLOW: RGBColor = (255, 223, 0)
    BRIGHT_YELLOW: RGBColor = (255, 233, 0)
    RED: RGBColor = (255, 0, 0)
    BLUE: RGBColor = (0, 0, 255)
    CUBS_BLUE: RGBColor = (0, 51, 102)
    GREEN: RGBColor = (70, 128, 83)
    DELAY_YELLOW: RGBColor = (255, 210, 0)
    POSTPONE_RED: RGBColor = (255, 100, 100)

    # Bears colors
    BEARS_NAVY: RGBColor = (11, 22, 42)
    BEARS_ORANGE: RGBColor = (200, 56, 3)

    # PGA colors
    PGA_BLUE: RGBColor = (0, 51, 153)
    PGA_NAVY: RGBColor = (13, 30, 63)
    PGA_GOLD: RGBColor = (255, 215, 0)
    PGA_GREEN: RGBColor = (34, 139, 34)


class Positions:
    """Display positions for various elements"""
    # Base positions for diamond display
    SECOND_BASE: Position = (46, 8)
    FIRST_BASE: Position = (53, 15)  # second_base + (7, 7)
    THIRD_BASE: Position = (39, 15)  # second_base - (7, 7)
    BASE_OFFSET: int = 7  # Offset between bases

    # Image positions during live game
    CUBS_IMAGE: Position = (1, 0)
    OPP_IMAGE: Position = (1, 17)
    BATTING_HOME: Position = (30, 6)
    BATTING_AWAY: Position = (30, 22)

    # Game over positions
    CUBS_IMAGE_GAMEOVER: Position = (1, 1)
    OPP_IMAGE_GAMEOVER: Position = (68, 1)

    # Score box boundaries
    SCORE_BOX_LEFT: int = 17
    SCORE_BOX_RIGHT: int = 32
    SCORE_BOX_TOP: int = 1
    SCORE_BOX_BOTTOM: int = 32
    SCORE_DIVIDER_Y: int = 16

    # Right panel (game info area)
    RIGHT_PANEL_START: int = 32
    RIGHT_PANEL_END: int = 96
    BASE_LINE_Y: int = 23
    VERTICAL_DIVIDER_X: int = 70

    # Pitcher/batter info area
    PITCHER_AREA_TOP: int = 32
    PITCHER_AREA_BOTTOM: int = 40
    BATTER_AREA_TOP: int = 40
    BATTER_AREA_BOTTOM: int = 48

    # Batting indicator box dimensions
    BATTING_BOX_WIDTH: int = 4
    BATTING_BOX_HEIGHT: int = 2
    BATTING_HOME_BOX_Y: tuple[int, int] = (7, 9)
    BATTING_AWAY_BOX_Y: tuple[int, int] = (23, 25)
    BATTING_BOX_X: tuple[int, int] = (30, 34)

    # Sweater header stripe positions (Bears/PGA)
    HEADER_TOP_STRIPE: tuple[int, int] = (4, 7)
    HEADER_BOTTOM_STRIPE: tuple[int, int] = (22, 25)
    HEADER_TEXT_Y: int = 19


class Fonts:
    """Font file paths"""
    LARGE_BOLD: str = "./fonts/10x20.bdf"
    MEDIUM_BOLD: str = "./fonts/9x18B.bdf"
    STANDARD_BOLD: str = "./fonts/7x13B.bdf"
    LINEUP: str = "./fonts/7x14B.bdf"
    SMALL_BOLD: str = "./fonts/6x13B.bdf"
    SMALL: str = "./fonts/6x9.bdf"
    TINY_BOLD: str = "./fonts/5x8.bdf"
    TINY: str = "./fonts/5x7.bdf"
    MICRO: str = "./fonts/4x6.bdf"
    ULTRA_MICRO: str = "./fonts/tom-thumb.bdf"

    # Character widths for text positioning calculations
    CHAR_WIDTH_LARGE: int = 10
    CHAR_WIDTH_MEDIUM: int = 9
    CHAR_WIDTH_STANDARD: int = 7
    CHAR_WIDTH_SMALL: int = 6
    CHAR_WIDTH_TINY: int = 5
    CHAR_WIDTH_MICRO: int = 4


class GameConfig:
    """Game-related configuration"""
    MAX_DAYS_TO_CHECK: int = 14
    GAME_CHECK_DELAY: int = 5  # seconds between game status checks
    NO_GAME_STANDINGS_DISPLAY_TIME: int = 15  # seconds
    SCROLL_SPEED: float = 0.002  # seconds between scroll updates
    SCROLL_PIXELS: int = 1  # pixels to move per frame
    GAME_OVER_WAIT_TIME: int = 360  # seconds for doubleheader wait
    ERROR_RETRY_DELAY: int = 10  # seconds

    # Animation timing
    ANIMATION_FRAME_DELAY: float = 0.3  # seconds between animation frames
    MODE_SWITCH_DURATION: int = 15  # seconds between display mode switches

    # API update intervals (in seconds)
    WEATHER_UPDATE_INTERVAL: int = 1800  # 30 minutes
    NEWS_UPDATE_INTERVAL: int = 1800  # 30 minutes
    SCHEDULE_UPDATE_INTERVAL: int = 3600  # 1 hour
    LIVE_SCORE_UPDATE_INTERVAL: int = 60  # 1 minute
    SEASON_CHECK_INTERVAL: int = 86400  # 24 hours

    # Off-season rotation durations (in minutes)
    WEATHER_DISPLAY_DURATION: int = 2
    BEARS_DISPLAY_DURATION: int = 3
    BEARS_NEWS_DURATION: int = 2
    PGA_DISPLAY_DURATION: int = 3
    PGA_FACTS_DURATION: int = 2
    CUBS_NEWS_DURATION: int = 2
    MESSAGE_DISPLAY_DURATION: int = 4

    # Display thresholds
    OFF_SEASON_DAYS_THRESHOLD: int = 30  # Days until next game to trigger off-season


class DisplayHandler(ABC):
    """Abstract base class for all display handlers"""

    def __init__(self, scoreboard_manager: ScoreboardManager) -> None:
        """Initialize with reference to main scoreboard manager"""
        self.manager = scoreboard_manager

    @abstractmethod
    def display(self, duration: int) -> None:
        """
        Main display method that all handlers must implement.

        Args:
            duration: Time in seconds to display content
        """
        pass

    def _draw_header_stripes(
        self,
        stripe_color: RGBColor,
        background_color: RGBColor,
        header_text: str
    ) -> None:
        """
        Draw a sweater-style header with horizontal stripes.

        Args:
            stripe_color: RGB color for the stripes
            background_color: RGB color for the background
            header_text: Text to display between stripes
        """
        # Fill background
        for y in range(DisplayConfig.MATRIX_ROWS):
            for x in range(DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, y, *background_color)

        # Top stripe
        for y in range(Positions.HEADER_TOP_STRIPE[0], Positions.HEADER_TOP_STRIPE[1]):
            for x in range(DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, y, *stripe_color)

        # Bottom stripe
        for y in range(Positions.HEADER_BOTTOM_STRIPE[0], Positions.HEADER_BOTTOM_STRIPE[1]):
            for x in range(DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, y, *stripe_color)

        # Header text centered
        text_width = len(header_text) * Fonts.CHAR_WIDTH_SMALL
        x_pos = max(0, (DisplayConfig.MATRIX_COLS - text_width) // 2)
        self.manager.draw_text('small_bold', x_pos, Positions.HEADER_TEXT_Y,
                               Colors.WHITE, header_text)

    def _center_text_x(self, text: str, char_width: int) -> int:
        """
        Calculate x position to center text on display.

        Args:
            text: The text to center
            char_width: Width of each character in pixels

        Returns:
            X position for centered text
        """
        text_width = len(text) * char_width
        return max(0, (DisplayConfig.MATRIX_COLS - text_width) // 2)

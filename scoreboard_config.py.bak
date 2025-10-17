"""Configuration and constants for the Cubs LED Scoreboard"""

class DisplayConfig:
    """LED Matrix display configuration"""
    MATRIX_ROWS = 48
    MATRIX_COLS = 96
    CHAIN_LENGTH = 1
    PARALLEL = 1
    HARDWARE_MAPPING = 'regular'
    
class TeamConfig:
    """Team-specific configuration"""
    CUBS_TEAM_ID = 112
    
class Colors:
    """RGB color definitions"""
    WHITE = (255, 255, 255)
    BLACK = (0, 0, 0)
    YELLOW = (255, 223, 0)
    BRIGHT_YELLOW = (255, 233, 0)
    RED = (255, 0, 0)
    BLUE = (0, 0, 255)
    CUBS_BLUE = (0, 51, 102)
    GREEN = (70, 128, 83)
    DELAY_YELLOW = (255, 210, 0)
    POSTPONE_RED = (255, 100, 100)
    
class Positions:
    """Display positions for various elements"""
    # Base positions
    SECOND_BASE = (46, 8)
    FIRST_BASE = (53, 15)  # second_base + (7, 7)
    THIRD_BASE = (39, 15)  # second_base - (7, 7)
    
    # Image positions
    CUBS_IMAGE = (1, 0)
    OPP_IMAGE = (1, 17)
    BATTING_HOME = (30, 6)
    BATTING_AWAY = (30, 22)
    
    # Game over positions
    CUBS_IMAGE_GAMEOVER = (1, 1)
    OPP_IMAGE_GAMEOVER = (68, 1)
    
class Fonts:
    """Font file paths"""
    LARGE_BOLD = "./fonts/10x20.bdf"
    MEDIUM_BOLD = "./fonts/9x18B.bdf"
    STANDARD_BOLD = "./fonts/7x13B.bdf"
    LINEUP = "./fonts/7x14B.bdf"
    SMALL_BOLD = "./fonts/6x13B.bdf"
    SMALL = "./fonts/6x9.bdf"
    TINY_BOLD = "./fonts/5x8.bdf"
    TINY = "./fonts/5x7.bdf"
    MICRO = "./fonts/4x6.bdf"
    ULTRA_MICRO = "./fonts/tom-thumb.bdf"
    
class GameConfig:
    """Game-related configuration"""
    MAX_DAYS_TO_CHECK = 14
    GAME_CHECK_DELAY = 5  # seconds between game status checks
    NO_GAME_STANDINGS_DISPLAY_TIME = 15  # seconds
    SCROLL_SPEED = 0.02  # seconds between scroll updates
    GAME_OVER_WAIT_TIME = 360  # seconds for doubleheader wait
    ERROR_RETRY_DELAY = 10  # seconds
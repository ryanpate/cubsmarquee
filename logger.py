"""Centralized logging configuration for Cubs LED Scoreboard"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


# Default log format
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Log file settings
LOG_DIR = Path("/var/log/cubs-scoreboard")
LOG_FILE = LOG_DIR / "scoreboard.log"
MAX_LOG_SIZE = 5 * 1024 * 1024  # 5 MB
BACKUP_COUNT = 3


def setup_logging(
    level: int = logging.INFO,
    log_to_file: bool = True,
    log_to_console: bool = True
) -> logging.Logger:
    """
    Set up the root logger with file and console handlers.

    Args:
        level: Logging level (default INFO)
        log_to_file: Whether to log to file (default True)
        log_to_console: Whether to log to console (default True)

    Returns:
        Configured root logger
    """
    # Get the root logger for our application
    logger = logging.getLogger("cubs_scoreboard")
    logger.setLevel(level)

    # Clear any existing handlers
    logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    # Console handler
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # File handler with rotation
    if log_to_file:
        try:
            # Create log directory if it doesn't exist
            LOG_DIR.mkdir(parents=True, exist_ok=True)

            file_handler = RotatingFileHandler(
                LOG_FILE,
                maxBytes=MAX_LOG_SIZE,
                backupCount=BACKUP_COUNT
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except PermissionError:
            # Fall back to local directory if /var/log is not writable
            local_log = Path("./scoreboard.log")
            file_handler = RotatingFileHandler(
                local_log,
                maxBytes=MAX_LOG_SIZE,
                backupCount=BACKUP_COUNT
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            logger.warning(f"Could not write to {LOG_FILE}, using {local_log}")

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a child logger for a specific module.

    Args:
        name: Module name (e.g., 'weather_display', 'bears_display')

    Returns:
        Logger instance for the module
    """
    return logging.getLogger(f"cubs_scoreboard.{name}")


# Pre-configured module loggers for easy import
class Loggers:
    """Pre-configured loggers for each module"""

    @staticmethod
    def main() -> logging.Logger:
        return get_logger("main")

    @staticmethod
    def scoreboard() -> logging.Logger:
        return get_logger("scoreboard")

    @staticmethod
    def game_state() -> logging.Logger:
        return get_logger("game_state")

    @staticmethod
    def live_game() -> logging.Logger:
        return get_logger("live_game")

    @staticmethod
    def off_season() -> logging.Logger:
        return get_logger("off_season")

    @staticmethod
    def weather() -> logging.Logger:
        return get_logger("weather")

    @staticmethod
    def bears() -> logging.Logger:
        return get_logger("bears")

    @staticmethod
    def pga() -> logging.Logger:
        return get_logger("pga")

    @staticmethod
    def admin() -> logging.Logger:
        return get_logger("admin")

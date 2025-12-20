"""Main application file for Cubs LED Scoreboard"""

from __future__ import annotations

import logging
import signal
import time
import sys
import pendulum
import traceback
from typing import Any, NoReturn

from scoreboard_manager import ScoreboardManager
from game_state_handler import GameStateHandler
from live_game_handler import LiveGameHandler
from off_season_handler import OffSeasonHandler
from scoreboard_config import GameConfig, TeamConfig
from logger import setup_logging, get_logger


# Global flag for graceful shutdown
_shutdown_requested: bool = False

# Module logger
logger = get_logger("main")


def _signal_handler(signum: int, frame: Any) -> None:
    """Handle shutdown signals gracefully"""
    global _shutdown_requested
    signal_name = signal.Signals(signum).name
    logger.info(f"Received {signal_name} - initiating graceful shutdown...")
    _shutdown_requested = True


def is_shutdown_requested() -> bool:
    """Check if shutdown has been requested"""
    return _shutdown_requested


class CubsScoreboard:
    """Main Cubs Scoreboard Application"""

    def __init__(self) -> None:
        """Initialize the scoreboard application"""
        logger.info("Initializing Cubs LED Scoreboard...")

        try:
            self.manager: ScoreboardManager = ScoreboardManager()
            logger.info("Scoreboard manager initialized")

            self.state_handler: GameStateHandler = GameStateHandler(self.manager)
            logger.info("State handler initialized")

            self.live_handler: LiveGameHandler = LiveGameHandler(self.manager)
            logger.info("Live handler initialized")

            self.off_season_handler: OffSeasonHandler = OffSeasonHandler(self.manager)
            logger.info("Off-season handler initialized")

            self.current_game_index: int = 0
            logger.info("All components initialized successfully")

        except Exception as e:
            logger.error(f"ERROR during initialization: {e}")
            logger.debug(traceback.format_exc())
            raise

    def run(self) -> NoReturn:
        """Main application loop"""
        logger.info("Starting Cubs LED Scoreboard main loop...")

        # Clear display at startup
        try:
            self.manager.clear_canvas()
            self.manager.swap_canvas()
            logger.info("Display cleared and ready")
        except Exception as e:
            logger.warning(f"Could not clear display at startup: {e}")

        # Wait a moment for system to stabilize
        time.sleep(2)

        try:
            while not is_shutdown_requested():
                try:
                    # Check for shutdown between operations
                    if is_shutdown_requested():
                        break

                    # Check if it's off-season
                    if self.is_off_season():
                        logger.info(
                            "Off-season detected - entering off-season display mode")
                        self.off_season_handler.display_off_season_content()
                        # After off-season handler exits (season started), continue with game cycle
                        if is_shutdown_requested():
                            break

                    self.process_game_cycle()

                except KeyboardInterrupt:
                    raise  # Re-raise to exit cleanly

                except Exception as e:
                    logger.error(f"Error in main loop iteration: {e}")
                    logger.debug(traceback.format_exc())
                    self.handle_error()

            # Graceful shutdown path
            logger.info("Shutdown requested - exiting main loop...")

        except KeyboardInterrupt:
            logger.info("Shutting down Cubs LED Scoreboard...")

        except Exception as e:
            logger.critical(f"Fatal error in main loop: {e}")
            logger.debug(traceback.format_exc())
            self.handle_error()

    def is_off_season(self) -> bool:
        """
        Determine if it's currently the off-season.
        Returns True if no games are found in the next 14 days.
        """
        try:
            game_data: list[dict[str, Any]] = self.manager.get_schedule()

            if not game_data:
                logger.info("No games scheduled in the next 14 days - off-season mode")
                return True

            # Check if the game is far in the future (more than 30 days)
            # This handles the gap between end of regular season and playoffs
            if game_data:
                game_date_str: str = game_data[0]['game_date']
                game_date = pendulum.parse(game_date_str)
                days_until_game: int = (game_date - pendulum.now()).days

                if days_until_game > GameConfig.OFF_SEASON_DAYS_THRESHOLD:
                    logger.info(
                        f"Next game is {days_until_game} days away - off-season mode")
                    return True

            return False

        except Exception as e:
            logger.error(f"Error checking off-season status: {e}")
            logger.debug(traceback.format_exc())
            # Default to regular season if there's an error
            return False

    def process_game_cycle(self) -> None:
        """Process one complete game cycle"""
        try:
            # Get current schedule
            game_data: list[dict[str, Any]] = self.manager.get_schedule()

            if not game_data:
                logger.info("No games found in schedule - entering off-season mode")
                # Enter off-season display
                self.off_season_handler.display_off_season_content()
                return

            # Check for doubleheader
            self.current_game_index = self.determine_game_index(game_data)

            # Load images for current game
            self.manager.load_game_images(game_data, self.current_game_index)

            # Get game info
            gameid: int = game_data[self.current_game_index]['game_id']
            status: str = game_data[self.current_game_index]['status']

            logger.info(f"Game Status: {status}")

            # Route to appropriate handler based on status
            self.route_by_status(game_data, gameid, status)

        except Exception as e:
            logger.error(f"Error in game cycle: {e}")
            logger.debug(traceback.format_exc())
            self.handle_error()

    def determine_game_index(self, game_data: list[dict[str, Any]]) -> int:
        """Determine which game to display (handles doubleheaders)"""
        if len(game_data) > 1:
            # Doubleheader - check if first game is over
            if game_data[0]['status'] in ['Final', 'Game Over']:
                return 1
        return 0

    def route_by_status(
        self, game_data: list[dict[str, Any]], gameid: int, status: str
    ) -> None:
        """Route to appropriate display based on game status"""
        # Get lineup if needed
        lineup: str | None = None
        if status in ['Warmup', 'Pre-Game', 'In Progress', 'Delayed', 'Postponed']:
            lineup = self.manager.get_lineup(gameid)

        # Route based on status
        if status == 'Scheduled':
            self.state_handler.display_no_game(
                game_data, self.current_game_index)

        elif status in ['Warmup', 'Pre-Game']:
            self.state_handler.display_warmup(
                game_data, self.current_game_index, lineup, gameid
            )
            # After warmup, transition to game
            self.process_game_cycle()

        elif status.startswith('Delayed'):
            self.state_handler.display_delayed(
                game_data, self.current_game_index, lineup, gameid
            )
            # After delay, transition to game
            self.process_game_cycle()

        elif status.startswith('Postpon'):
            self.state_handler.display_postponed(
                game_data, self.current_game_index, lineup, gameid
            )
            # After postponement, check for rescheduling
            self.process_game_cycle()

        elif status == 'In Progress':
            self.live_handler.display_game_on(
                game_data, self.current_game_index, gameid
            )
            # After game ends, cycle continues
            self.process_game_cycle()

        elif status in ['Final', 'Game Over']:
            self.live_handler.display_game_over(
                game_data, self.current_game_index, gameid
            )
            # After game over display, start new cycle
            self.process_game_cycle()

        else:
            logger.warning(f"Unknown game status: {status}")
            time.sleep(GameConfig.ERROR_RETRY_DELAY)

    def handle_error(self) -> None:
        """Handle errors gracefully"""
        logger.info("Attempting to recover from error...")
        time.sleep(GameConfig.ERROR_RETRY_DELAY)

        # Clear canvas and restart
        try:
            self.manager.clear_canvas()
            self.manager.swap_canvas()
            time.sleep(1)
        except Exception as e:
            logger.warning(f"Could not clear canvas during error recovery: {e}")

        # Don't call run() here - just let the main loop continue


def main() -> None:
    """Main entry point"""
    # Initialize logging first
    setup_logging()

    logger.info("=" * 60)
    logger.info("Cubs LED Scoreboard Starting...")
    logger.info("=" * 60)

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    logger.info("Signal handlers registered (SIGTERM, SIGINT)")

    scoreboard: CubsScoreboard | None = None

    try:
        scoreboard = CubsScoreboard()
        scoreboard.run()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.critical(f"FATAL ERROR: {e}")
        logger.debug(traceback.format_exc())
        logger.info("Scoreboard will retry in 30 seconds...")
        time.sleep(30)
        # System service will restart the application
    finally:
        # Ensure display is cleared on exit
        if scoreboard is not None:
            try:
                logger.info("Clearing display before exit...")
                scoreboard.manager.clear_canvas()
                scoreboard.manager.swap_canvas()
                logger.info("Display cleared. Goodbye!")
            except Exception as e:
                logger.warning(f"Could not clear display on exit: {e}")
        sys.exit(0)


if __name__ == "__main__":
    main()

"""Main application file for Cubs LED Scoreboard"""

from __future__ import annotations

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


class CubsScoreboard:
    """Main Cubs Scoreboard Application"""

    def __init__(self) -> None:
        """Initialize the scoreboard application"""
        print("Initializing Cubs LED Scoreboard...")

        try:
            self.manager: ScoreboardManager = ScoreboardManager()
            print("✓ Scoreboard manager initialized")

            self.state_handler: GameStateHandler = GameStateHandler(self.manager)
            print("✓ State handler initialized")

            self.live_handler: LiveGameHandler = LiveGameHandler(self.manager)
            print("✓ Live handler initialized")

            self.off_season_handler: OffSeasonHandler = OffSeasonHandler(self.manager)
            print("✓ Off-season handler initialized")

            self.current_game_index: int = 0
            print("✓ All components initialized successfully")

        except Exception as e:
            print(f"ERROR during initialization: {e}")
            print(traceback.format_exc())
            raise

    def run(self) -> NoReturn:
        """Main application loop"""
        print("Starting Cubs LED Scoreboard main loop...")

        # Clear display at startup
        try:
            self.manager.clear_canvas()
            self.manager.swap_canvas()
            print("✓ Display cleared and ready")
        except Exception as e:
            print(f"Warning: Could not clear display at startup: {e}")

        # Wait a moment for system to stabilize
        time.sleep(2)

        try:
            while True:
                try:
                    # Check if it's off-season
                    if self.is_off_season():
                        print(
                            "Off-season detected - entering off-season display mode")
                        self.off_season_handler.display_off_season_content()
                        # After off-season handler exits (season started), continue with game cycle

                    self.process_game_cycle()

                except KeyboardInterrupt:
                    raise  # Re-raise to exit cleanly

                except Exception as e:
                    print(f"Error in main loop iteration: {e}")
                    print(traceback.format_exc())
                    self.handle_error()

        except KeyboardInterrupt:
            print("\nShutting down Cubs LED Scoreboard...")
            self.manager.clear_canvas()
            sys.exit(0)

        except Exception as e:
            print(f"Fatal error in main loop: {e}")
            print(traceback.format_exc())
            self.handle_error()

    def is_off_season(self) -> bool:
        """
        Determine if it's currently the off-season.
        Returns True if no games are found in the next 14 days.
        """
        try:
            game_data: list[dict[str, Any]] = self.manager.get_schedule()

            if not game_data:
                print("No games scheduled in the next 14 days - off-season mode")
                return True

            # Check if the game is far in the future (more than 30 days)
            # This handles the gap between end of regular season and playoffs
            if game_data:
                game_date_str: str = game_data[0]['game_date']
                game_date = pendulum.parse(game_date_str)
                days_until_game: int = (game_date - pendulum.now()).days

                if days_until_game > GameConfig.OFF_SEASON_DAYS_THRESHOLD:
                    print(
                        f"Next game is {days_until_game} days away - off-season mode")
                    return True

            return False

        except Exception as e:
            print(f"Error checking off-season status: {e}")
            print(traceback.format_exc())
            # Default to regular season if there's an error
            return False

    def process_game_cycle(self) -> None:
        """Process one complete game cycle"""
        try:
            # Get current schedule
            game_data: list[dict[str, Any]] = self.manager.get_schedule()

            if not game_data:
                print("No games found in schedule - entering off-season mode")
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

            print(f"Game Status: {status}")

            # Route to appropriate handler based on status
            self.route_by_status(game_data, gameid, status)

        except Exception as e:
            print(f"Error in game cycle: {e}")
            print(traceback.format_exc())
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
            print(f"Unknown game status: {status}")
            time.sleep(GameConfig.ERROR_RETRY_DELAY)

    def handle_error(self) -> None:
        """Handle errors gracefully"""
        print("Attempting to recover from error...")
        time.sleep(GameConfig.ERROR_RETRY_DELAY)

        # Clear canvas and restart
        try:
            self.manager.clear_canvas()
            self.manager.swap_canvas()
            time.sleep(1)
        except Exception as e:
            print(f"Could not clear canvas during error recovery: {e}")

        # Don't call run() here - just let the main loop continue


def main() -> None:
    """Main entry point"""
    print("=" * 60)
    print("Cubs LED Scoreboard Starting...")
    print("=" * 60)

    try:
        scoreboard = CubsScoreboard()
        scoreboard.run()
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        print(traceback.format_exc())
        print("Scoreboard will retry in 30 seconds...")
        time.sleep(30)
        # System service will restart the application


if __name__ == "__main__":
    main()

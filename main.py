"""Main application file for Cubs LED Scoreboard"""

import time
import sys
import pendulum
from scoreboard_manager import ScoreboardManager
from game_state_handler import GameStateHandler
from live_game_handler import LiveGameHandler
from scoreboard_config import GameConfig, TeamConfig

class CubsScoreboard:
    """Main Cubs Scoreboard Application"""
    
    def __init__(self):
        """Initialize the scoreboard application"""
        self.manager = ScoreboardManager()
        self.state_handler = GameStateHandler(self.manager)
        self.live_handler = LiveGameHandler(self.manager)
        self.current_game_index = 0
        
    def run(self):
        """Main application loop"""
        print("Starting Cubs LED Scoreboard...")
        
        try:
            while True:
                self.process_game_cycle()
        except KeyboardInterrupt:
            print("\nShutting down Cubs LED Scoreboard...")
            self.manager.clear_canvas()
            sys.exit(0)
        except Exception as e:
            print(f"Unexpected error in main loop: {e}")
            self.handle_error()
    
    def process_game_cycle(self):
        """Process one complete game cycle"""
        try:
            # Get current schedule
            game_data = self.manager.get_schedule()
            
            if not game_data:
                print("No games found in schedule")
                time.sleep(GameConfig.ERROR_RETRY_DELAY)
                return
            
            # Check for doubleheader
            self.current_game_index = self.determine_game_index(game_data)
            
            # Load images for current game
            self.manager.load_game_images(game_data, self.current_game_index)
            
            # Get game info
            gameid = game_data[self.current_game_index]['game_id']
            status = game_data[self.current_game_index]['status']
            
            print(f"Game Status: {status}")
            
            # Route to appropriate handler based on status
            self.route_by_status(game_data, gameid, status)
            
        except Exception as e:
            print(f"Error in game cycle: {e}")
            self.handle_error()
    
    def determine_game_index(self, game_data):
        """Determine which game to display (handles doubleheaders)"""
        if len(game_data) > 1:
            # Doubleheader - check if first game is over
            if game_data[0]['status'] in ['Final', 'Game Over']:
                return 1
        return 0
    
    def route_by_status(self, game_data, gameid, status):
        """Route to appropriate display based on game status"""
        # Get lineup if needed
        lineup = None
        if status in ['Warmup', 'Pre-Game', 'In Progress', 'Delayed', 'Postponed']:
            lineup = self.manager.get_lineup(gameid)
        
        # Route based on status
        if status == 'Scheduled':
            self.state_handler.display_no_game(game_data, self.current_game_index)
            
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
    
    def handle_error(self):
        """Handle errors gracefully"""
        print("Attempting to recover from error...")
        time.sleep(GameConfig.ERROR_RETRY_DELAY)
        
        # Clear canvas and restart
        try:
            self.manager.clear_canvas()
            self.manager.swap_canvas()
        except:
            pass
        
        # Restart the cycle
        self.run()

def main():
    """Main entry point"""
    scoreboard = CubsScoreboard()
    scoreboard.run()

if __name__ == "__main__":
    main()
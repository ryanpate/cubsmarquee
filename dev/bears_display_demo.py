"""Chicago Bears game display - DEMO/TEST VERSION with mock data"""

import time
import pendulum
from scoreboard_config import Colors, GameConfig


class BearsDisplay:
    """Handles Chicago Bears game information display - DEMO VERSION"""

    def __init__(self, scoreboard_manager):
        """Initialize Bears display"""
        self.manager = scoreboard_manager
        
        # Classic Bears colors
        self.BEARS_NAVY = (11, 22, 42)      # Navy blue background
        self.BEARS_ORANGE = (200, 56, 3)    # Classic Bears orange
        self.BEARS_WHITE = (255, 255, 255)  # White text
        
        # Demo mode flag - set to True to use mock data
        self.DEMO_MODE = True
        
    def _draw_sweater_header(self):
        """Draw the classic Bears sweater header with orange stripes"""
        # Fill entire background with Bears navy
        for y in range(48):
            for x in range(96):
                self.manager.draw_pixel(x, y, *self.BEARS_NAVY)

        # Top orange stripe (3 pixels tall)
        for y in range(6, 9):
            for x in range(96):
                self.manager.draw_pixel(x, y, *self.BEARS_ORANGE)

        # Bottom orange stripe (3 pixels tall)
        for y in range(24, 27):
            for x in range(96):
                self.manager.draw_pixel(x, y, *self.BEARS_ORANGE)

        # Draw "CHICAGO BEARS" text in white, centered between stripes
        self.manager.draw_text('small_bold', 8, 21,
                               self.BEARS_WHITE, 'CHICAGO BEARS')

    def display_bears_info(self, duration=180):
        """Display Bears game information - DEMO VERSION"""
        print("\n" + "="*50)
        print("BEARS DISPLAY DEMO MODE")
        print("Choose a demo scenario:")
        print("1. Live Game (In Progress)")
        print("2. Final Game (Win)")
        print("3. Final Game (Loss)")
        print("4. Pre-Game (Today)")
        print("5. Next Game (Future)")
        print("="*50)
        
        # For automatic testing, cycle through all scenarios
        scenarios = [
            self._demo_live_game,
            self._demo_final_win,
            self._demo_final_loss,
            self._demo_pregame,
            self._demo_next_game
        ]
        
        # Show each scenario for a portion of the duration
        scenario_duration = duration / len(scenarios)
        
        for i, scenario in enumerate(scenarios, 1):
            print(f"\n>>> Showing Scenario {i} <<<")
            scenario(scenario_duration)

    def _demo_live_game(self, duration):
        """Demo: Bears game in progress"""
        start_time = time.time()
        
        # Mock live game data
        bears_score = '13'
        opp_score = '7'
        opponent_abbr = 'GB'
        game_time = 'Q3 - 8:47'
        
        print(f"LIVE GAME: CHI {bears_score} - {opponent_abbr} {opp_score} ({game_time})")
        
        while time.time() - start_time < duration:
            self.manager.clear_canvas()
            self._draw_sweater_header()
            
            # Live game display
            self.manager.draw_text('tiny_bold', 30, 28,
                                   self.BEARS_WHITE, 'LIVE GAME')
            
            # Bears score
            self.manager.draw_text('small_bold', 20, 36,
                                   self.BEARS_WHITE, f'CHI {bears_score}')
            
            # Opponent score
            self.manager.draw_text('small_bold', 58, 36,
                                   self.BEARS_WHITE, f'{opponent_abbr} {opp_score}')
            
            # Quarter/Time info at bottom
            self.manager.draw_text('micro', 28, 44,
                                   self.BEARS_ORANGE, game_time)
            
            self.manager.swap_canvas()
            time.sleep(0.5)

    def _demo_final_win(self, duration):
        """Demo: Bears won"""
        start_time = time.time()
        
        # Mock final game data - WIN
        bears_score = '27'
        opp_score = '24'
        opponent_abbr = 'MIN'
        
        print(f"FINAL WIN: CHI {bears_score} - {opponent_abbr} {opp_score}")
        
        while time.time() - start_time < duration:
            self.manager.clear_canvas()
            self._draw_sweater_header()
            
            # WIN display
            self.manager.draw_text('tiny_bold', 35, 28,
                                   (0, 200, 0), 'WIN')
            
            # Final scores
            self.manager.draw_text('small_bold', 20, 36,
                                   self.BEARS_WHITE, f'CHI {bears_score}')
            self.manager.draw_text('small_bold', 58, 36,
                                   self.BEARS_WHITE, f'{opponent_abbr} {opp_score}')
            
            self.manager.draw_text('micro', 35, 44,
                                   self.BEARS_ORANGE, 'FINAL')
            
            self.manager.swap_canvas()
            time.sleep(0.5)

    def _demo_final_loss(self, duration):
        """Demo: Bears lost"""
        start_time = time.time()
        
        # Mock final game data - LOSS
        bears_score = '17'
        opp_score = '24'
        opponent_abbr = 'DET'
        
        print(f"FINAL LOSS: CHI {bears_score} - {opponent_abbr} {opp_score}")
        
        while time.time() - start_time < duration:
            self.manager.clear_canvas()
            self._draw_sweater_header()
            
            # LOSS display
            self.manager.draw_text('tiny_bold', 35, 28,
                                   (200, 0, 0), 'LOSS')
            
            # Final scores
            self.manager.draw_text('small_bold', 20, 36,
                                   self.BEARS_WHITE, f'CHI {bears_score}')
            self.manager.draw_text('small_bold', 58, 36,
                                   self.BEARS_WHITE, f'{opponent_abbr} {opp_score}')
            
            self.manager.draw_text('micro', 35, 44,
                                   self.BEARS_ORANGE, 'FINAL')
            
            self.manager.swap_canvas()
            time.sleep(0.5)

    def _demo_pregame(self, duration):
        """Demo: Game today but hasn't started"""
        start_time = time.time()
        
        # Mock pregame data
        opponent_name = 'Green Bay Packers'
        display_time = '12:00 PM'
        
        print(f"PREGAME TODAY: vs {opponent_name} at {display_time}")
        
        while time.time() - start_time < duration:
            self.manager.clear_canvas()
            self._draw_sweater_header()
            
            # TODAY vs
            self.manager.draw_text('tiny', 28, 28,
                                   self.BEARS_WHITE, 'TODAY vs')
            
            # Opponent name centered
            opp_x = max(5, (96 - len(opponent_name) * 5) // 2)
            self.manager.draw_text('tiny', opp_x, 36,
                                   self.BEARS_ORANGE, opponent_name)
            
            # Game time at bottom (in Central time)
            time_x = max(5, (96 - len(display_time) * 4) // 2)
            self.manager.draw_text('micro', time_x, 44,
                                   self.BEARS_WHITE, display_time)
            
            self.manager.swap_canvas()
            time.sleep(0.5)

    def _demo_next_game(self, duration):
        """Demo: Scrolling next game message"""
        start_time = time.time()
        scroll_position = 96
        
        # Mock next game data
        message = "NEXT GAME: Sun Nov 24 at Minnesota Vikings at 12:00 PM"
        
        print(f"SCROLLING: {message}")
        
        while time.time() - start_time < duration:
            self.manager.clear_canvas()
            self._draw_sweater_header()
            
            # Scroll the message using GameConfig settings for consistency
            scroll_increment = getattr(GameConfig, 'SCROLL_PIXELS', 2)
            scroll_position -= scroll_increment
            text_length = len(message) * 9
            
            if scroll_position + text_length < 0:
                scroll_position = 96
            
            # Draw scrolling message below the header
            self.manager.draw_text('medium_bold', int(scroll_position), 44,
                                   self.BEARS_WHITE, message)
            
            self.manager.swap_canvas()
            time.sleep(GameConfig.SCROLL_SPEED)


# =============================================================================
# HOW TO USE THIS DEMO VERSION
# =============================================================================
"""
TESTING THE BEARS DISPLAY:

1. TEMPORARY TESTING (doesn't affect your main scoreboard):
   
   In your terminal/SSH:
   
   python3 << 'EOF'
   from scoreboard_manager import ScoreboardManager
   from bears_display_demo import BearsDisplay
   import time
   
   # Initialize
   manager = ScoreboardManager()
   bears = BearsDisplay(manager)
   
   # Run demo for 60 seconds (shows all 5 scenarios)
   bears.display_bears_info(duration=60)
   
   # Clean up
   manager.clear_canvas()
   EOF

2. TESTING SPECIFIC SCENARIOS:
   
   # Test just the live game
   python3 << 'EOF'
   from scoreboard_manager import ScoreboardManager
   from bears_display_demo import BearsDisplay
   
   manager = ScoreboardManager()
   bears = BearsDisplay(manager)
   
   # Show live game for 30 seconds
   bears._demo_live_game(30)
   
   manager.clear_canvas()
   EOF

3. ADJUSTING THE DISPLAY:
   
   - Edit the position values in this file
   - Change colors (BEARS_NAVY, BEARS_ORANGE, BEARS_WHITE)
   - Adjust text positions (x, y coordinates)
   - Modify stripe heights/positions in _draw_sweater_header()
   - Change font sizes in draw_text() calls
   
   Font options: 'tiny', 'tiny_bold', 'micro', 'small', 'small_bold', 
                 'medium_bold', 'large_bold'

4. ONCE YOU'RE HAPPY WITH THE LOOK:
   
   Copy your adjustments back to the real bears_display.py file

TIPS:
- Each scenario runs for duration/5 seconds by default
- Press Ctrl+C to stop the demo
- Watch the terminal output to see which scenario is showing
- The sweater header should look the same across all scenarios
"""
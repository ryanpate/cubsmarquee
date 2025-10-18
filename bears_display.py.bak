"""Chicago Bears game display - Future enhancement for off-season"""

import time
import requests
import pendulum
from scoreboard_config import Colors


class BearsDisplay:
    """Handles Chicago Bears game information display"""
    
    def __init__(self, scoreboard_manager):
        """Initialize Bears display"""
        self.manager = scoreboard_manager
        self.bears_data = None
        self.last_update = None
        self.update_interval = 3600  # Update every hour
        
    def _fetch_bears_schedule(self):
        """
        Fetch Bears schedule from ESPN API
        ESPN API is free and doesn't require authentication
        """
        try:
            # ESPN API endpoint for Chicago Bears (team ID: 3)
            url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/chi/schedule"
            
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            self.bears_data = data
            self.last_update = time.time()
            print("Bears schedule updated")
            return True
            
        except Exception as e:
            print(f"Error fetching Bears schedule: {e}")
            return False
    
    def _should_update_schedule(self):
        """Check if schedule needs updating"""
        if not self.bears_data or not self.last_update:
            return True
        return (time.time() - self.last_update) > self.update_interval
    
    def _get_todays_game(self):
        """Get today's Bears game if there is one"""
        if not self.bears_data:
            return None
        
        today = pendulum.now().format('YYYY-MM-DD')
        
        try:
            events = self.bears_data.get('events', [])
            
            for event in events:
                game_date = event['date'][:10]  # Get YYYY-MM-DD
                
                if game_date == today:
                    return event
            
            return None
            
        except Exception as e:
            print(f"Error parsing Bears game: {e}")
            return None
    
    def _get_next_game(self):
        """Get next upcoming Bears game"""
        if not self.bears_data:
            return None
        
        now = pendulum.now()
        
        try:
            events = self.bears_data.get('events', [])
            
            for event in events:
                game_date = pendulum.parse(event['date'])
                
                if game_date > now:
                    return event
            
            return None
            
        except Exception as e:
            print(f"Error parsing Bears game: {e}")
            return None
    
    def display_bears_info(self, duration=180):
        """Display Bears game information"""
        # Fetch schedule if needed
        if self._should_update_schedule():
            if not self._fetch_bears_schedule():
                return  # Failed to fetch
        
        if not self.bears_data:
            return
        
        # Check for today's game
        todays_game = self._get_todays_game()
        
        if todays_game:
            self._display_game_day(todays_game, duration)
        else:
            next_game = self._get_next_game()
            if next_game:
                self._display_next_game(next_game, duration)
    
    def _display_game_day(self, game, duration):
        """Display today's Bears game"""
        start_time = time.time()
        
        try:
            # Parse game data
            competition = game['competitions'][0]
            home_team = competition['competitors'][0]
            away_team = competition['competitors'][1]
            
            # Determine if Bears are home or away
            bears_home = home_team['team']['abbreviation'] == 'CHI'
            
            if bears_home:
                bears = home_team
                opponent = away_team
            else:
                bears = away_team
                opponent = home_team
            
            opponent_name = opponent['team']['displayName']
            opponent_abbr = opponent['team']['abbreviation']
            
            # Get scores if game has started
            bears_score = bears['score']
            opp_score = opponent['score']
            
            # Get game status
            status = competition['status']['type']['name']
            game_time = competition['status']['type']['shortDetail']
            
            while time.time() - start_time < duration:
                self.manager.clear_canvas()
                
                # Background - Bears colors (Navy and Orange)
                for y in range(48):
                    # Gradient from navy blue
                    for x in range(96):
                        self.manager.draw_pixel(x, y, 11, 22, 42)
                
                # Draw title
                self.manager.draw_text('small_bold', 20, 10, 
                                     (255, 143, 0), 'CHICAGO BEARS')
                
                if status == 'STATUS_IN_PROGRESS':
                    # Game in progress - show scores
                    self.manager.draw_text('tiny_bold', 30, 20, 
                                         Colors.WHITE, 'LIVE GAME')
                    
                    # Bears score
                    self.manager.draw_text('medium_bold', 15, 32, 
                                         Colors.WHITE, f'CHI {bears_score}')
                    
                    # Opponent score
                    self.manager.draw_text('medium_bold', 55, 32, 
                                         Colors.WHITE, f'{opponent_abbr} {opp_score}')
                    
                    # Quarter/Time info
                    self.manager.draw_text('micro', 25, 42, 
                                         Colors.YELLOW, game_time)
                
                elif status == 'STATUS_FINAL':
                    # Game final
                    result = 'WIN' if int(bears_score) > int(opp_score) else 'LOSS'
                    result_color = Colors.GREEN if result == 'WIN' else Colors.RED
                    
                    self.manager.draw_text('tiny_bold', 35, 20, 
                                         result_color, result)
                    
                    # Final scores
                    self.manager.draw_text('small', 15, 32, 
                                         Colors.WHITE, f'CHI {bears_score}')
                    self.manager.draw_text('small', 55, 32, 
                                         Colors.WHITE, f'{opponent_abbr} {opp_score}')
                    
                    self.manager.draw_text('micro', 35, 42, 
                                         Colors.WHITE, 'FINAL')
                
                else:
                    # Game scheduled but not started
                    self.manager.draw_text('tiny', 20, 22, 
                                         Colors.WHITE, 'TODAY vs')
                    
                    opp_x = max(5, (96 - len(opponent_name) * 5) // 2)
                    self.manager.draw_text('tiny', opp_x, 32, 
                                         Colors.YELLOW, opponent_name)
                    
                    time_x = max(5, (96 - len(game_time) * 4) // 2)
                    self.manager.draw_text('micro', time_x, 42, 
                                         Colors.WHITE, game_time)
                
                self.manager.swap_canvas()
                time.sleep(0.5)
                
        except Exception as e:
            print(f"Error displaying Bears game: {e}")
    
    def _display_next_game(self, game, duration):
        """Display next upcoming Bears game"""
        start_time = time.time()
        scroll_pos = 96
        
        try:
            # Parse game data
            competition = game['competitions'][0]
            home_team = competition['competitors'][0]
            away_team = competition['competitors'][1]
            
            bears_home = home_team['team']['abbreviation'] == 'CHI'
            
            if bears_home:
                opponent = away_team
                vs_at = 'vs'
            else:
                opponent = home_team
                vs_at = 'at'
            
            opponent_name = opponent['team']['displayName']
            game_date_raw = game['date']
            game_date = pendulum.parse(game_date_raw)
            
            # Format date and time
            date_str = game_date.format('ddd MMM D')
            time_str = game_date.format('h:mm A')
            
            message = f"NEXT BEARS GAME: {date_str} {vs_at} {opponent_name} at {time_str}"
            
            while time.time() - start_time < duration:
                self.manager.clear_canvas()
                
                # Background - Bears navy
                self.manager.fill_canvas(11, 22, 42)
                
                # Title
                self.manager.draw_text('small_bold', 12, 12, 
                                     (255, 143, 0), 'CHICAGO BEARS')
                
                # Scroll the message
                scroll_pos -= 1
                text_length = len(message) * 7
                
                if scroll_pos + text_length < 0:
                    scroll_pos = 96
                
                self.manager.draw_text('lineup', scroll_pos, 35, 
                                     Colors.WHITE, message)
                
                self.manager.swap_canvas()
                time.sleep(0.02)
                
        except Exception as e:
            print(f"Error displaying next Bears game: {e}")


# USAGE EXAMPLE - Add to off_season_handler.py:
"""
from bears_display import BearsDisplay

# In __init__:
self.bears_display = BearsDisplay(scoreboard_manager)

# In rotation cycle (September through February):
if self._is_football_season():
    self.bears_display.display_bears_info(duration=180)

# Helper method:
def _is_football_season(self):
    month = pendulum.now().month
    return month >= 9 or month <= 2  # Sept through Feb
"""
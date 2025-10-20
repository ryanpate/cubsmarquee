"""Chicago Bears game display - Classic Bears Sweater Style"""

import time
import requests
import pendulum
from scoreboard_config import Colors, GameConfig


class BearsDisplay:
    """Handles Chicago Bears game information display"""

    def __init__(self, scoreboard_manager):
        """Initialize Bears display"""
        self.manager = scoreboard_manager
        self.bears_data = None
        self.last_update = None
        self.update_interval = 3600  # Update every hour

        # Classic Bears colors
        self.BEARS_NAVY = (11, 22, 42)      # Navy blue background
        self.BEARS_ORANGE = (200, 56, 3)    # Classic Bears orange
        self.BEARS_WHITE = (255, 255, 255)  # White text

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

            # Get scores from the API - score is an object with 'value' and 'displayValue'
            # Example: {"value": 24.0, "displayValue": "24"}
            bears_score_obj = bears.get('score', {})
            opp_score_obj = opponent.get('score', {})

            # Extract the actual score value safely
            if isinstance(bears_score_obj, dict):
                bears_score = str(int(bears_score_obj.get('value', 0)))
            else:
                bears_score = str(bears_score_obj) if bears_score_obj else '0'

            if isinstance(opp_score_obj, dict):
                opp_score = str(int(opp_score_obj.get('value', 0)))
            else:
                opp_score = str(opp_score_obj) if opp_score_obj else '0'

            print(f"Bears score: {bears_score}, Opponent score: {opp_score}")

            # Get game status
            status = competition['status']['type']['name']
            game_time_raw = competition['status']['type']['shortDetail']

            # If game_time contains actual time info, convert to Central
            # Otherwise just use as-is (for "Final", "Postponed", etc.)
            game_time = game_time_raw

            while time.time() - start_time < duration:
                self.manager.clear_canvas()

                # Draw sweater-style header
                self._draw_sweater_header()

                if status == 'STATUS_IN_PROGRESS':
                    # Game in progress - show scores below header
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

                elif status == 'STATUS_FINAL':
                    # Game final - safely convert scores to integers for comparison
                    try:
                        bears_score_int = int(
                            float(bears_score)) if bears_score else 0
                        opp_score_int = int(
                            float(opp_score)) if opp_score else 0
                        result = 'WIN' if bears_score_int > opp_score_int else 'LOSS'
                    except (ValueError, TypeError):
                        result = 'FINAL'

                    result_color = (
                        0, 200, 0) if result == 'WIN' else (200, 0, 0)

                    self.manager.draw_text('tiny_bold', 35, 28,
                                           result_color, result)

                    # Final scores
                    self.manager.draw_text('small_bold', 20, 36,
                                           self.BEARS_WHITE, f'CHI {bears_score}')
                    self.manager.draw_text('small_bold', 58, 36,
                                           self.BEARS_WHITE, f'{opponent_abbr} {opp_score}')

                    self.manager.draw_text('micro', 35, 44,
                                           self.BEARS_ORANGE, 'FINAL')

                else:
                    # Game scheduled but not started
                    # Convert game time to Central timezone
                    game_datetime = pendulum.parse(game['date'])
                    game_datetime_central = game_datetime.in_timezone(
                        'America/Chicago')
                    display_time = game_datetime_central.format('h:mm A')

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

        except Exception as e:
            print(f"Error displaying Bears game: {e}")
            import traceback
            traceback.print_exc()

    def _display_next_game(self, game, duration):
        """Display next upcoming Bears game with scrolling text"""
        start_time = time.time()
        scroll_position = 96

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

            # Convert to Central timezone (system timezone)
            game_date_central = game_date.in_timezone('America/Chicago')

            # Format date and time in Central time
            date_str = game_date_central.format('ddd MMM D')
            time_str = game_date_central.format('h:mm A')

            message = f"NEXT GAME: {date_str} {vs_at} {opponent_name} at {time_str}"

            while time.time() - start_time < duration:
                self.manager.clear_canvas()

                # Draw sweater-style header
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

                # Use GameConfig SCROLL_SPEED for consistent timing
                time.sleep(GameConfig.SCROLL_SPEED)

        except Exception as e:
            print(f"Error displaying Bears game: {e}")
            import traceback
            traceback.print_exc()

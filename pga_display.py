"""PGA Tour display - Tournament leaderboard and scores"""

import time
import requests
import pendulum
from scoreboard_config import Colors, GameConfig


class PGADisplay:
    """Handles PGA Tour tournament information display"""

    def __init__(self, scoreboard_manager):
        """Initialize PGA display"""
        self.manager = scoreboard_manager
        self.pga_data = None
        self.last_update = None
        self.update_interval = 3600  # Update every hour
        self.live_update_interval = 300  # Update live scores every 5 minutes

        # PGA Tour colors
        self.PGA_BLUE = (0, 51, 153)        # PGA Tour blue
        self.PGA_NAVY = (13, 30, 63)        # Dark navy background
        self.PGA_GOLD = (255, 215, 0)       # Gold accents
        self.PGA_WHITE = (255, 255, 255)    # White text
        self.PGA_GREEN = (34, 139, 34)      # Golf course green

    def _fetch_pga_data(self):
        """
        Fetch PGA Tour leaderboard from ESPN API
        ESPN API is free and doesn't require authentication
        """
        try:
            # ESPN API endpoint for PGA Tour
            # This provides current tournament leaderboard
            url = "https://site.api.espn.com/apis/site/v2/sports/golf/pga/leaderboard"

            response = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
            })
            response.raise_for_status()
            data = response.json()

            self.pga_data = data
            self.last_update = time.time()
            print("PGA Tour data updated")
            return True

        except Exception as e:
            print(f"Error fetching PGA Tour data: {e}")
            return False

    def _should_update_data(self):
        """Check if data needs updating"""
        if not self.pga_data or not self.last_update:
            return True
        return (time.time() - self.last_update) > self.update_interval

    def _get_active_tournament(self):
        """Get currently active tournament if there is one"""
        if not self.pga_data:
            return None

        try:
            # Check if there's an active event
            events = self.pga_data.get('events', [])

            if not events:
                return None

            # Get the first event (current/upcoming tournament)
            event = events[0]

            # Check if tournament is in progress
            status = event.get('status', {}).get('type', {}).get('name', '')

            return event if event else None

        except Exception as e:
            print(f"Error parsing PGA tournament: {e}")
            return None

    def _get_tournament_info(self, event):
        """
        Extract tournament information
        Returns dict with: name, status, leaders, course, etc.
        """
        try:
            tournament_name = event.get('name', 'PGA TOUR')
            status = event.get('status', {}).get('type', {}).get('name', '')
            status_detail = event.get('status', {}).get('type', {}).get('shortDetail', '')

            # Get competition data
            competitions = event.get('competitions', [])
            if not competitions:
                return None

            competition = competitions[0]

            # Get competitors (players)
            competitors = competition.get('competitors', [])

            # Get top 5 leaders
            leaders = []
            for i, player in enumerate(competitors[:5]):
                try:
                    athlete = player.get('athlete', {})
                    name = athlete.get('displayName', 'Unknown')

                    # Get score (relative to par)
                    score_obj = player.get('score')
                    if isinstance(score_obj, dict):
                        score = score_obj.get('displayValue', 'E')
                    else:
                        score = str(score_obj) if score_obj else 'E'

                    # Get position
                    position = player.get('status', {}).get('position', {}).get('displayValue', str(i+1))

                    leaders.append({
                        'name': name,
                        'score': score,
                        'position': position
                    })
                except Exception as e:
                    print(f"Error parsing player {i}: {e}")
                    continue

            return {
                'name': tournament_name,
                'status': status,
                'status_detail': status_detail,
                'leaders': leaders
            }

        except Exception as e:
            print(f"Error getting tournament info: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _draw_pga_header(self):
        """Draw the PGA Tour header with green/blue theme"""
        # Fill background with navy
        for y in range(48):
            for x in range(96):
                self.manager.draw_pixel(x, y, *self.PGA_NAVY)

        # Top green stripe (golf course theme)
        for y in range(3, 6):
            for x in range(96):
                self.manager.draw_pixel(x, y, *self.PGA_GREEN)

        # Bottom gold stripe
        for y in range(20, 23):
            for x in range(96):
                self.manager.draw_pixel(x, y, *self.PGA_GOLD)

        # Draw "PGA TOUR" text in white
        self.manager.draw_text('small_bold', 20, 17,
                               self.PGA_WHITE, 'PGA TOUR')

    def display_pga_info(self, duration=180):
        """Display PGA Tour tournament information"""
        # Fetch data if needed
        if self._should_update_data():
            if not self._fetch_pga_data():
                # If fetch fails, display a message
                self._display_no_data(duration)
                return

        if not self.pga_data:
            self._display_no_data(duration)
            return

        # Check for active tournament
        tournament = self._get_active_tournament()

        if tournament:
            self._display_tournament(tournament, duration)
        else:
            self._display_no_tournament(duration)

    def _display_tournament(self, event, duration):
        """Display active tournament with leaderboard"""
        start_time = time.time()
        last_update = 0

        try:
            # Get initial tournament info
            tourney_info = self._get_tournament_info(event)
            if not tourney_info:
                return

            tournament_name = tourney_info['name']
            status = tourney_info['status']
            status_detail = tourney_info['status_detail']
            leaders = tourney_info['leaders']

            print(f"Tournament: {tournament_name}, Status: {status}")

            while time.time() - start_time < duration:
                # Update live scores periodically
                current_time = time.time()
                if current_time - last_update >= self.live_update_interval:
                    if self._fetch_pga_data():
                        tournament = self._get_active_tournament()
                        if tournament:
                            updated_info = self._get_tournament_info(tournament)
                            if updated_info:
                                leaders = updated_info['leaders']
                                status_detail = updated_info['status_detail']
                                print("PGA scores updated")
                    last_update = current_time

                self.manager.clear_canvas()

                # Draw header
                self._draw_pga_header()

                # Display tournament name (scrolling if too long)
                name_short = tournament_name[:20] if len(tournament_name) > 20 else tournament_name
                name_x = max(5, (96 - len(name_short) * 4) // 2)
                self.manager.draw_text('tiny_bold', name_x, 28,
                                       self.PGA_WHITE, name_short)

                # Display leaderboard - top 3 players
                if leaders:
                    y_pos = 35
                    for i, leader in enumerate(leaders[:3]):
                        pos = leader['position']
                        name = leader['name'].split()[-1][:8]  # Last name, max 8 chars
                        score = leader['score']

                        # Format: "1. SMITH -12"
                        line = f"{pos}. {name} {score}"
                        self.manager.draw_text('tiny', 8, y_pos,
                                             self.PGA_WHITE, line)
                        y_pos += 6

                self.manager.swap_canvas()
                time.sleep(0.5)

        except Exception as e:
            print(f"Error displaying PGA tournament: {e}")
            import traceback
            traceback.print_exc()

    def _display_no_tournament(self, duration):
        """Display message when no tournament is active"""
        start_time = time.time()
        scroll_position = 96

        message = "PGA TOUR - Check back during tournament season"

        while time.time() - start_time < duration:
            self.manager.clear_canvas()

            # Draw header
            self._draw_pga_header()

            # Scroll the message
            scroll_increment = getattr(GameConfig, 'SCROLL_PIXELS', 2)
            scroll_position -= scroll_increment
            text_length = len(message) * 5

            if scroll_position + text_length < 0:
                scroll_position = 96

            # Draw scrolling message
            self.manager.draw_text('tiny_bold', int(scroll_position), 40,
                                   self.PGA_WHITE, message)

            self.manager.swap_canvas()
            time.sleep(GameConfig.SCROLL_SPEED)

    def _display_no_data(self, duration):
        """Display message when data fetch fails"""
        start_time = time.time()

        while time.time() - start_time < duration:
            self.manager.clear_canvas()

            # Draw header
            self._draw_pga_header()

            # Error message
            self.manager.draw_text('tiny', 15, 35,
                                   self.PGA_WHITE, 'PGA DATA')
            self.manager.draw_text('tiny', 10, 42,
                                   self.PGA_WHITE, 'UNAVAILABLE')

            self.manager.swap_canvas()
            time.sleep(1)

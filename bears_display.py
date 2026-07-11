"""Chicago Bears game display - Classic Bears Sweater Style"""

from __future__ import annotations

import time
import requests
import pendulum
from PIL import Image
from typing import TYPE_CHECKING, Any

from scoreboard_config import (
    Colors, Fonts, GameConfig, RGBColor, get_scroll_delay, load_user_config)
from retry import retry_http_request

if TYPE_CHECKING:
    from scoreboard_manager import ScoreboardManager


def extract_situation(competition: dict) -> dict:
    """Extract the live in-game situation from an ESPN competition dict.

    All fields are optional in the ESPN payload (absent between plays,
    at halftime, and for non-live games) and degrade to None/False.
    """
    result: dict[str, Any] = {
        'possession': None,
        'down_distance': None,
        'is_red_zone': False,
        'last_play': None,
    }
    situation = competition.get('situation')
    if not situation:
        return result

    possession_id = situation.get('possession')
    if possession_id:
        for competitor in competition.get('competitors', []):
            team = competitor.get('team', {})
            if str(team.get('id')) == str(possession_id):
                if team.get('abbreviation') == 'CHI':
                    result['possession'] = 'bears'
                else:
                    result['possession'] = 'opponent'
                break

    down_distance = situation.get('shortDownDistanceText')
    possession_text = situation.get('possessionText')
    if down_distance and possession_text:
        result['down_distance'] = f'{down_distance} {possession_text}'.upper()
    elif down_distance:
        result['down_distance'] = down_distance.upper()

    result['is_red_zone'] = bool(situation.get('isRedZone'))
    result['last_play'] = (situation.get('lastPlay') or {}).get('text')
    return result


def extract_broadcast(competition: dict) -> str | None:
    """TV network from either ESPN shape: scoreboard uses broadcasts[].names,
    the schedule endpoint uses broadcasts[].media.shortName."""
    broadcasts = competition.get('broadcasts') or []
    if not broadcasts:
        return None
    first = broadcasts[0]
    names = first.get('names')
    if names:
        return names[0]
    return (first.get('media') or {}).get('shortName')


def extract_week(event: dict) -> int | None:
    """NFL week number from an ESPN event"""
    return (event.get('week') or {}).get('number')


def format_countdown(seconds: float) -> str:
    """Format seconds until kickoff as '2D 14H', '3H 22M', or '22M'"""
    total_minutes = int(seconds // 60)
    days, remainder = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(remainder, 60)
    if days > 0:
        return f'{days}D {hours}H'
    if hours > 0:
        return f'{hours}H {minutes}M'
    return f'{minutes}M'


def countdown_color(seconds: float, yellow_under: float,
                    orange_under: float) -> RGBColor:
    """Countdown text color: white, yellow when close, orange when imminent"""
    if seconds < orange_under:
        return (255, 120, 0)
    if seconds < yellow_under:
        return Colors.YELLOW
    return Colors.WHITE


def celebration_message(delta: int) -> str:
    """Pick the scoring celebration text from the score change"""
    if delta in (6, 7, 8):
        return 'TOUCHDOWN!'
    if delta == 3:
        return 'FIELD GOAL!'
    if delta == 2:
        return 'SAFETY!'
    return 'BEARS SCORE!'


def format_kickoff_time(dt) -> str:
    """Kickoff time in Central, with 12:00 PM shown as NOON"""
    if dt.hour == 12 and dt.minute == 0:
        return 'NOON'
    return dt.format('h:mm A')


class BearsDisplay:
    """Handles Chicago Bears game information display"""

    def __init__(self, scoreboard_manager: ScoreboardManager) -> None:
        """Initialize Bears display"""
        self.manager = scoreboard_manager
        self.bears_data: dict[str, Any] | None = None
        self.last_update: float | None = None
        self.update_interval: int = GameConfig.SCHEDULE_UPDATE_INTERVAL
        self.live_update_interval: int = GameConfig.LIVE_SCORE_UPDATE_INTERVAL

        # Classic Bears colors (using centralized config)
        self.BEARS_NAVY: RGBColor = Colors.BEARS_NAVY
        self.BEARS_ORANGE: RGBColor = Colors.BEARS_ORANGE
        self.BEARS_WHITE: RGBColor = Colors.WHITE
        self.BEARS_GRAY: RGBColor = (170, 170, 170)

        # Pre-generate cached background image for performance
        self._bears_sweater_bg: Image.Image = self._create_bears_sweater_background()

    def _create_bears_sweater_background(self) -> Image.Image:
        """Pre-generate compact Bears sweater header background for performance

        Full 96x48 navy frame with orange stripes at y0-1 and y10-11; the
        header band is y0-11 and content draws on navy from y12 down.
        """
        img = Image.new("RGB", (96, 48), self.BEARS_NAVY)
        pixels = img.load()
        for y in (0, 1, 10, 11):
            for x in range(96):
                pixels[x, y] = self.BEARS_ORANGE
        print("Bears sweater background cached")
        return img

    def _load_scroll_config(self) -> dict:
        """Load scroll speed settings from config file"""
        return load_user_config()

    def _fetch_live_scores(self, game_id):
        """
        Fetch live scores from the scoreboard endpoint
        The schedule endpoint doesn't always have live scores immediately
        """
        try:
            url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"

            response = retry_http_request(url, timeout=10)
            data = response.json()

            # Find the game by ID
            for event in data.get('events', []):
                if event.get('id') == game_id:
                    return event

            return None

        except Exception as e:
            print(f"Error fetching live scores: {e}")
            return None

    def _fetch_bears_schedule(self):
        """
        Fetch Bears schedule from ESPN API
        ESPN API is free and doesn't require authentication
        """
        try:
            # ESPN API endpoint for Chicago Bears (team ID: 3)
            url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/chi/schedule"

            response = retry_http_request(url, timeout=10)
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

        # Get today's date in Chicago timezone
        today = pendulum.now('America/Chicago').format('YYYY-MM-DD')

        try:
            events = self.bears_data.get('events', [])

            for event in events:
                # Parse the UTC date and convert to Chicago timezone before comparing
                game_datetime = pendulum.parse(event['date'])
                game_date = game_datetime.in_timezone('America/Chicago').format('YYYY-MM-DD')

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

    def _get_current_scores(self, game, game_id):
        """
        Get current scores for a game
        Returns dict with: status, game_time, bears_score, opp_score, opponent_abbr, opponent_name
        """
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

            # Get game status
            status = competition['status']['type']['name']
            game_time_raw = competition['status']['type']['shortDetail']

            # Check if scores exist in schedule data
            bears_has_score = 'score' in bears
            opp_has_score = 'score' in opponent

            # For today's games, always fetch from scoreboard to get most current status
            # This ensures we get final scores and status updates immediately
            if not bears_has_score or not opp_has_score or status in ['STATUS_IN_PROGRESS', 'STATUS_SCHEDULED']:
                print("Fetching from scoreboard for current status...")
                live_game = self._fetch_live_scores(game_id)

                if live_game:
                    # Update game data with live scoreboard data
                    competition = live_game['competitions'][0]
                    home_team = competition['competitors'][0]
                    away_team = competition['competitors'][1]

                    # Re-determine Bears and opponent with fresh data
                    if home_team['team']['abbreviation'] == 'CHI':
                        bears = home_team
                        opponent = away_team
                    else:
                        bears = away_team
                        opponent = home_team

                    # Update status from live data
                    status = competition['status']['type']['name']
                    game_time_raw = competition['status']['type']['shortDetail']
                    print(f"Updated from scoreboard - Status: {status}")

            # Extract scores - they're in format {"value": 24.0, "displayValue": "24"}
            bears_score_obj = bears.get('score')
            opp_score_obj = opponent.get('score')

            # Parse Bears score
            if isinstance(bears_score_obj, dict):
                bears_score = bears_score_obj.get('displayValue', '0')
            elif bears_score_obj is not None:
                bears_score = str(int(float(bears_score_obj)))
            else:
                bears_score = '0'

            # Parse opponent score
            if isinstance(opp_score_obj, dict):
                opp_score = opp_score_obj.get('displayValue', '0')
            elif opp_score_obj is not None:
                opp_score = str(int(float(opp_score_obj)))
            else:
                opp_score = '0'

            # Live in-game situation (possession, down & distance, last play).
            # Uses the final `competition` value, which is the live scoreboard
            # data when a refetch happened above.
            situation = extract_situation(competition)

            return {
                'status': status,
                'game_time': game_time_raw,
                'bears_score': bears_score,
                'opp_score': opp_score,
                'opponent_abbr': opponent_abbr,
                'opponent_name': opponent_name,
                'possession': situation['possession'],
                'down_distance': situation['down_distance'],
                'is_red_zone': situation['is_red_zone'],
                'last_play': situation['last_play'],
            }

        except Exception as e:
            print(f"Error getting current scores: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _draw_sweater_header(self):
        """Draw the compact Bears sweater header using the cached background"""
        self.manager.set_image(self._bears_sweater_bg, 0, 0)

        # "CHICAGO BEARS" in tiny_bold (5px/char, 13 chars = 65px), centered
        self.manager.draw_text('tiny_bold', 15, 9,
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
        """Display today's Bears game with live score updates"""
        start_time = time.time()
        last_score_update = 0
        frame_count = 0
        prev_bears_score = None
        last_scrolled_play = None

        try:
            game_id = game.get('id')

            score_data = self._get_current_scores(game, game_id)
            if not score_data:
                return

            try:
                prev_bears_score = int(float(score_data['bears_score']))
            except (ValueError, TypeError):
                prev_bears_score = None

            print(f"Game status: {score_data['status']}, "
                  f"Detail: {score_data['game_time']}")

            while time.time() - start_time < duration:
                # Refresh live scores every LIVE_SCORE_UPDATE_INTERVAL seconds
                current_time = time.time()
                if (score_data['status'] == 'STATUS_IN_PROGRESS' and
                        current_time - last_score_update >= self.live_update_interval):
                    print("Updating live scores...")
                    updated_data = self._get_current_scores(game, game_id)

                    if updated_data:
                        try:
                            new_score = int(float(updated_data['bears_score']))
                        except (ValueError, TypeError):
                            new_score = prev_bears_score

                        # Bears scored since the last poll - celebrate
                        if (prev_bears_score is not None and
                                new_score is not None and
                                new_score > prev_bears_score):
                            self._play_scoring_celebration(
                                new_score - prev_bears_score)

                        if new_score is not None:
                            prev_bears_score = new_score
                        score_data = updated_data
                        print(f"Scores updated - Bears: {score_data['bears_score']}, "
                              f"Opponent: {score_data['opp_score']}")

                    last_score_update = current_time

                self.manager.clear_canvas()
                self._draw_sweater_header()

                status = score_data['status']
                if status == 'STATUS_IN_PROGRESS':
                    self._draw_live_content(score_data, frame_count)
                elif status == 'STATUS_FINAL':
                    self._draw_final_content(score_data, frame_count)
                else:
                    self._draw_pregame_content(game)

                self.manager.swap_canvas()
                frame_count += 1
                time.sleep(0.5)

                # Scroll each new play description once across the bottom strip
                if status == 'STATUS_IN_PROGRESS':
                    play = score_data.get('last_play')
                    if play and play != last_scrolled_play:
                        self._scroll_last_play(play)
                        last_scrolled_play = play

        except Exception as e:
            print(f"Error displaying Bears game: {e}")
            import traceback
            traceback.print_exc()

    def _draw_live_content(self, score_data, frame_count):
        """Draw scores, possession dot, down & distance, and clock (y12-47)"""
        bears_score = score_data['bears_score']
        opp_score = score_data['opp_score']
        opp_abbr = score_data['opponent_abbr']

        # Score row
        self.manager.draw_text('small_bold', 8, 24,
                               self.BEARS_WHITE, f'CHI {bears_score}')
        self.manager.draw_text('small_bold', 52, 24,
                               self.BEARS_WHITE, f'{opp_abbr} {opp_score}')

        # Orange possession dot beside the team with the ball
        possession = score_data.get('possession')
        if possession == 'bears':
            self._draw_possession_dot(3)
        elif possession == 'opponent':
            self._draw_possession_dot(91)

        # Down & distance; red and blinking in the red zone
        down_distance = score_data.get('down_distance')
        if down_distance:
            if score_data.get('is_red_zone'):
                color = (255, 60, 60) if frame_count % 2 == 0 else None
            else:
                color = self.BEARS_WHITE
            if color:
                x = max(0, (96 - len(down_distance) * Fonts.CHAR_WIDTH_TINY) // 2)
                self.manager.draw_text('tiny', x, 31, color, down_distance)

        # Quarter / clock
        game_time = score_data.get('game_time') or ''
        if game_time:
            x = max(0, (96 - len(game_time) * Fonts.CHAR_WIDTH_MICRO) // 2)
            self.manager.draw_text('micro', x, 38, self.BEARS_ORANGE, game_time)

    def _draw_possession_dot(self, x):
        """Draw a 3x3 orange football dot at the given x, beside the score row"""
        for px in range(x, x + 3):
            for py in range(18, 21):
                self.manager.draw_pixel(px, py, *self.BEARS_ORANGE)

    def _scroll_last_play(self, text):
        """Scroll a play description once across the bottom strip (y40-47)"""
        original = self.manager.get_frame_copy()
        snapshot = original.copy()

        # Clear the strip to plain navy so the text scrolls over clean rows
        pixels = snapshot.load()
        for y in range(40, 48):
            for x in range(96):
                pixels[x, y] = self.BEARS_NAVY

        text = text.upper()
        text_width = len(text) * Fonts.CHAR_WIDTH_MICRO
        config = self._load_scroll_config()
        scroll_delay = get_scroll_delay(config.get('scroll_speed_bears', 5))

        scroll_x = 96
        while scroll_x + text_width >= 0:
            self.manager.set_image(snapshot, 0, 0)
            self.manager.draw_text('micro', scroll_x, 46,
                                   self.BEARS_WHITE, text)
            self.manager.swap_canvas()
            time.sleep(scroll_delay)
            scroll_x -= 1

        # Restore the pre-scroll frame
        self.manager.set_image(original, 0, 0)
        self.manager.swap_canvas()

    def _play_scoring_celebration(self, delta):
        """Flash a scoring message for ~4 seconds when the Bears score"""
        message = celebration_message(delta)
        x = max(0, (96 - len(message) * Fonts.CHAR_WIDTH_SMALL) // 2)

        for i in range(8):
            self.manager.clear_canvas()
            self._draw_sweater_header()
            color = self.BEARS_ORANGE if i % 2 == 0 else self.BEARS_WHITE
            self.manager.draw_text('small_bold', x, 32, color, message)
            self.manager.swap_canvas()
            time.sleep(0.5)

    def _draw_pregame_content(self, game):
        """Draw the pregame card: opponent, kickoff, countdown, week/TV"""
        competition = game['competitions'][0]
        home_team = competition['competitors'][0]
        away_team = competition['competitors'][1]
        bears_home = home_team['team']['abbreviation'] == 'CHI'
        opponent = away_team if bears_home else home_team
        vs_at = 'VS' if bears_home else 'AT'

        # Nickname always fits 96px (longest is BUCCANEERS = 50px in tiny_bold)
        opp_name = (opponent['team'].get('shortDisplayName')
                    or opponent['team']['displayName']).upper()

        kickoff = pendulum.parse(game['date']).in_timezone('America/Chicago')

        line1 = f'TODAY {vs_at}'
        x = max(0, (96 - len(line1) * Fonts.CHAR_WIDTH_TINY) // 2)
        self.manager.draw_text('tiny', x, 19, self.BEARS_WHITE, line1)

        x = max(0, (96 - len(opp_name) * Fonts.CHAR_WIDTH_TINY) // 2)
        self.manager.draw_text('tiny_bold', x, 27, self.BEARS_ORANGE, opp_name)

        time_str = format_kickoff_time(kickoff)
        x = max(0, (96 - len(time_str) * Fonts.CHAR_WIDTH_TINY) // 2)
        self.manager.draw_text('tiny', x, 35, self.BEARS_WHITE, time_str)

        # Live countdown, recomputed each frame
        seconds = (kickoff - pendulum.now('America/Chicago')).total_seconds()
        if seconds > 0:
            countdown = f'KICKOFF IN {format_countdown(seconds)}'
            color = countdown_color(seconds, yellow_under=3 * 3600,
                                    orange_under=3600)
            x = max(0, (96 - len(countdown) * Fonts.CHAR_WIDTH_MICRO) // 2)
            self.manager.draw_text('micro', x, 42, color, countdown)

        # Week and TV network, either part omitted when missing
        parts = []
        week = extract_week(game)
        if week:
            parts.append(f'WK {week}')
        network = extract_broadcast(competition)
        if network:
            parts.append(network.upper())
        if parts:
            line = ' '.join(parts)
            x = max(0, (96 - len(line) * Fonts.CHAR_WIDTH_MICRO) // 2)
            self.manager.draw_text('micro', x, 47, self.BEARS_GRAY, line)

    def _draw_final_content(self, score_data, frame_count):
        """Draw the final-score screen"""
        bears_score = score_data['bears_score']
        opp_score = score_data['opp_score']
        opp_abbr = score_data['opponent_abbr']

        self.manager.draw_text('small_bold', 8, 24,
                               self.BEARS_WHITE, f'CHI {bears_score}')
        self.manager.draw_text('small_bold', 52, 24,
                               self.BEARS_WHITE, f'{opp_abbr} {opp_score}')

        try:
            bears_score_int = int(float(bears_score)) if bears_score else 0
            opp_score_int = int(float(opp_score)) if opp_score else 0
            result = 'WIN' if bears_score_int > opp_score_int else 'LOSS'
        except (ValueError, TypeError):
            result = 'FINAL'

        result_color = (0, 200, 0) if result == 'WIN' else (200, 0, 0)
        self.manager.draw_text('tiny_bold', 37, 36, result_color, result)

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

                # Scroll smoothly 1 pixel at a time (like Spring Training)
                scroll_position -= 1
                text_length = len(message) * 9

                if scroll_position + text_length < 0:
                    scroll_position = 96

                # Draw scrolling text
                self.manager.draw_text('medium_bold', int(scroll_position), 44,
                                       self.BEARS_WHITE, message)

                self.manager.swap_canvas()
                # Load config after drawing (like Spring Training)
                config = self._load_scroll_config()
                scroll_delay = get_scroll_delay(config.get('scroll_speed_bears', 5))
                time.sleep(scroll_delay)

        except Exception as e:
            print(f"Error displaying Bears game: {e}")
            import traceback
            traceback.print_exc()

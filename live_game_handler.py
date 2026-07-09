"""Handler for live game display including scores, bases, and game updates"""

from __future__ import annotations

import time
import pendulum
import statsapi
from PIL import Image
from typing import TYPE_CHECKING, Any

from scoreboard_config import Colors, Fonts, Positions, GameConfig, TeamConfig, DisplayConfig
from retry import retry_api_call
from logger import get_logger
from flight_display import FlightDisplay

logger = get_logger("live_game")

if TYPE_CHECKING:
    from scoreboard_manager import ScoreboardManager


class LiveGameHandler:
    """Handles live game display and updates"""

    def __init__(self, scoreboard_manager: ScoreboardManager) -> None:
        """Initialize with reference to main scoreboard manager"""
        self.manager = scoreboard_manager
        self.cubs_score: int = 0
        self.opp_score: int = 0
        self.is_cubs_home: bool = False
        self._flight_display: FlightDisplay | None = None
        self._last_inning_state: str = ''

    def display_game_on(
        self, game_data: list[dict[str, Any]], game_index: int, gameid: int
    ) -> None:
        """Main game display loop"""
        self.is_cubs_home = (
            game_data[game_index]['home_id'] == TeamConfig.CUBS_TEAM_ID)

        # Initialize scores
        if self.is_cubs_home:
            self.cubs_score = game_data[game_index]['home_score']
            self.opp_score = game_data[game_index]['away_score']
        else:
            self.cubs_score = game_data[game_index]['away_score']
            self.opp_score = game_data[game_index]['home_score']

        while True:
            game_data = self.manager.get_schedule()

            # Check for game over
            current_status = game_data[game_index]['status']
            if current_status in ['Game Over', 'Final'] or current_status.startswith('Completed Early'):
                self.display_game_over(game_data, game_index, gameid)
                break

            # Exit live display when the game is no longer actively being played
            # (delay/suspension/postponement/cancellation). Returning lets the
            # main loop route to the appropriate handler on the next cycle.
            if (current_status.startswith('Delayed')
                    or current_status.startswith('Suspend')
                    or current_status.startswith('Postpon')
                    or current_status == 'Cancelled'):
                return

            # Get current game data
            game_info = retry_api_call(statsapi.get, 'game', {'gamePk': gameid})
            play_data = retry_api_call(statsapi.get, 'game_playByPlay', {'gamePk': gameid})

            # Clear canvas
            self.manager.clear_canvas()

            # Get inning state for batting indicator logic
            inning_state = game_info['liveData']['linescore']['inningState'][:3]

            # Create base composite image with all background regions pre-painted
            base_image = Image.new("RGB", (96, 48))
            pixels = base_image.load()

            # Paint black divider between logos and scores (x=16, y=0-30)
            for y in range(0, 31):
                pixels[16, y] = (0, 0, 0)

            # Paint score boxes white (x=17-31, y=0-30) with black divider at y=15
            for x in range(17, 32):
                for y in range(0, 31):
                    if y == 15:
                        pixels[x, y] = (0, 0, 0)
                    else:
                        pixels[x, y] = (255, 255, 255)

            # Paint right side Cubs blue (x=32-95, y=0-30)
            for x in range(32, 96):
                for y in range(0, 31):
                    pixels[x, y] = (0, 51, 102)

            # Paint black divider line between logos (y=15, x=0-15)
            for x in range(0, 16):
                pixels[x, 15] = (0, 0, 0)

            # Paint white base line (y=22, x=32-95)
            for x in range(32, 96):
                pixels[x, 22] = (255, 255, 255)

            # Paint white vertical line at x=70 (y=0-30)
            for y in range(0, 31):
                pixels[70, y] = (255, 255, 255)

            # Add team logos (resized to 16x15 to fill logo area edge-to-edge)
            cubs_logo = self.manager.game_images['cubs'].resize((16, 15)).convert('RGBA')
            opp_logo = self.manager.game_images['opponent'].resize((16, 15)).convert('RGBA')

            # Composite logos onto white background so dark logos remain visible
            for logo, pos in [(cubs_logo, (0, 0)), (opp_logo, (0, 16))]:
                logo_bg = Image.new("RGB", logo.size, (255, 255, 255))
                logo_bg.paste(logo, (0, 0), logo)
                base_image.paste(logo_bg, pos)

            # Set the full composite image to the canvas in one call
            self.manager.set_image(base_image.convert("RGB"), 0, 0)

            # Draw pitcher info area with gradient
            m = 0
            for pitcher_line in range(31, 39):
                for pitcher_line_v in range(0, 96):
                    self.manager.draw_pixel(
                        pitcher_line_v, pitcher_line, 255 + m, 255 + m, 255 + m)
                m -= 20

            # Draw batter info area with gradient
            m = 0
            for batter_line in range(39, 47):
                for batter_line_v in range(0, 96):
                    self.manager.draw_pixel(
                        batter_line_v, batter_line, 255 + m, 255 + m, 255 + m)
                m -= 20

            # Draw batting indicator box (red box)
            if self.is_cubs_home:
                if inning_state in ['Bot', 'Mid']:
                    for ht_h in range(6, 8):
                        for ht_v in range(30, 34):
                            self.manager.draw_pixel(ht_v, ht_h, 255, 0, 0)
                else:
                    for at_h in range(22, 24):
                        for at_v in range(30, 34):
                            self.manager.draw_pixel(at_v, at_h, 255, 0, 0)
            else:
                if inning_state in ['Top', 'End']:
                    for ht_h in range(6, 8):
                        for ht_v in range(30, 34):
                            self.manager.draw_pixel(ht_v, ht_h, 255, 0, 0)
                else:
                    for at_h in range(22, 24):
                        for at_v in range(30, 34):
                            self.manager.draw_pixel(at_v, at_h, 255, 0, 0)

            # Draw bases
            self._draw_bases_original(game_info)

            # Draw scores
            self._draw_scores(game_data, game_index)

            # Draw game info (inning, count, outs, pitcher, batter)
            self._draw_game_info_improved(game_info, play_data)

            # NOW draw batting indicator by pasting image on pixel-drawn canvas
            self._draw_batting_indicator_overlay(inning_state)

            # Check for score changes
            self._check_score_changes(game_data, game_index)

            # Draw split-squad indicator if active (top-right corner)
            if self.manager.split_squad_indicator:
                self._draw_split_squad_indicator()

            # Show replay challenge / umpire review over the batter strip
            banner = self._get_review_banner(current_status)
            if banner:
                self._draw_review_banner(banner)

            self.manager.swap_canvas()

            # Show brief flight summary on inning transitions (Mid/End states)
            if inning_state in ('Mid', 'End') and inning_state != self._last_inning_state:
                self._show_between_innings_flights()
            self._last_inning_state = inning_state

            time.sleep(GameConfig.GAME_CHECK_DELAY)

            # Exit loop if in split-squad mode and it's time to switch games
            if self.manager.split_squad_indicator:
                if time.time() >= self.manager.split_squad_switch_time:
                    # Return to main loop to switch to next game
                    break

    # Compact labels for common play events (micro font fits ~24 chars)
    PLAY_EVENT_ABBREVIATIONS: dict[str, str] = {
        'Strikeout': 'K',
        'Single': '1B',
        'Double': '2B',
        'Triple': '3B',
        'Home Run': 'HR',
        'Walk': 'BB',
        'Intent Walk': 'IBB',
        'Hit By Pitch': 'HBP',
        'Grounded Into DP': 'GDP',
        'Sac Fly': 'SF',
        'Sac Bunt': 'SAC',
        'Field Error': 'E',
        'Groundout': 'GO',
        'Flyout': 'FO',
        'Lineout': 'LO',
        'Pop Out': 'PO',
        'Forceout': 'FC',
        'Fielders Choice': 'FC',
    }

    def _get_last_play_text(self, play_data) -> str | None:
        """Compact 'LAST: <event> <batter>' line for the latest finished play"""
        try:
            for play in reversed(play_data.get('allPlays', [])):
                event = play.get('result', {}).get('event')
                if not event:
                    continue  # at-bat still in progress
                abbr = self.PLAY_EVENT_ABBREVIATIONS.get(event, event.upper())
                batter = play['matchup']['batter']['fullName']
                last_name = batter.split()[-1].upper()
                rbi = play.get('result', {}).get('rbi', 0)
                text = f"LAST: {abbr} {last_name}"
                if rbi:
                    text += f" +{rbi}"
                return text[:24]  # 96px wide at 4px per micro-font char
        except (KeyError, IndexError, AttributeError):
            pass
        return None

    @staticmethod
    def _get_review_banner(status: str) -> str | None:
        """Banner text for replay challenge / umpire review game states"""
        lowered = status.lower()
        if 'challenge' in lowered or 'review' in lowered:
            return status.upper()
        return None

    def _draw_review_banner(self, text: str) -> None:
        """Overlay a red challenge/review banner on the batter info strip"""
        for y in range(39, 48):
            for x in range(0, 96):
                self.manager.draw_pixel(x, y, 180, 0, 0)

        # Center in tiny_bold (5px per char)
        text_x = max(0, (96 - len(text) * Fonts.CHAR_WIDTH_TINY) // 2)
        self.manager.draw_text('tiny_bold', text_x, 46, Colors.WHITE, text)

    def _draw_batting_indicator_overlay(self, inning_state):
        """Draw batting indicator by overlaying on the current pixel buffer"""
        # Determine position based on who's batting
        batting_home_pos = (30, 5)
        batting_away_pos = (30, 21)

        # Get the appropriate position
        if self.is_cubs_home:
            if inning_state in ['Bot', 'Mid']:
                pos = batting_home_pos
            else:
                pos = batting_away_pos
        else:
            if inning_state in ['Top', 'End']:
                pos = batting_home_pos
            else:
                pos = batting_away_pos

        # Get the batting indicator image
        batting_img = self.manager.game_images['batting']

        # Paste it directly using PIL by converting current canvas to image,
        # adding the batting indicator, and setting it back
        # Create a new composite with the batting indicator
        final_image = Image.new("RGB", (96, 48))

        # We need to draw everything again on this image, or use a stored version
        # Since we can't get the current canvas easily, let's just paste the indicator
        # over a specific region by drawing pixels

        # Convert batting image to pixel array and draw it
        batting_pixels = batting_img.load()
        bat_width, bat_height = batting_img.size

        for y in range(bat_height):
            for x in range(bat_width):
                pixel = batting_pixels[x, y]
                # Only draw non-transparent pixels (if RGBA) or non-black pixels
                if len(pixel) == 4:  # RGBA
                    if pixel[3] > 0:  # Check alpha
                        self.manager.draw_pixel(
                            pos[0] + x, pos[1] + y, pixel[0], pixel[1], pixel[2])
                else:  # RGB
                    # Skip if pixel is pure black (assumed transparent)
                    if pixel != (0, 0, 0):
                        self.manager.draw_pixel(
                            pos[0] + x, pos[1] + y, pixel[0], pixel[1], pixel[2])

    def _draw_split_squad_indicator(self) -> None:
        """
        Draw split-squad game indicator in top-right corner.
        Shows which game is being displayed (e.g., "1/2" or "2/2").
        """
        indicator = self.manager.split_squad_indicator
        if not indicator:
            return

        # Draw a small background box in top-right corner
        # Position: x=88-95, y=0-7 (8x8 pixels)
        box_x = 88
        box_y = 0

        # Dark background for visibility
        for y in range(box_y, box_y + 8):
            for x in range(box_x, DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, y, 40, 40, 40)

        # Draw the indicator text (e.g., "1/2") in yellow
        self.manager.draw_text('micro', box_x + 1, 6, Colors.YELLOW, indicator)

    def _show_between_innings_flights(self) -> None:
        """Show a brief 5-second flight count overlay during inning transitions."""
        try:
            # Check if flights are enabled in config
            config_path = '/home/pi/config.json'
            alt_config_path = './config.json'
            import os, json
            config_file = config_path if os.path.exists(config_path) else alt_config_path
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    if not config.get('enable_flights', True):
                        return

            # Lazy-init flight display
            if self._flight_display is None:
                self._flight_display = FlightDisplay(self.manager)

            summary = self._flight_display.get_quick_flight_summary()
            if not summary or summary['count'] == 0:
                return

            count = summary['count']
            callsign = summary['closest_callsign']
            distance = summary['closest_distance']

            # Show for 5 seconds - simple overlay on dark background
            start_time = time.time()
            while time.time() - start_time < 5:
                self.manager.clear_canvas()

                # Dark blue background
                from PIL import Image
                bg = Image.new("RGB", (96, 48), (15, 40, 80))
                self.manager.set_image(bg, 0, 0)

                # "OVERHEAD" centered at top
                text1 = "OVERHEAD"
                x1 = (96 - len(text1) * 5) // 2
                self.manager.draw_text('tiny_bold', x1, 12, Colors.WHITE, text1)

                # Aircraft count - big and centered
                count_str = f"{count} AIRCRAFT"
                x2 = (96 - len(count_str) * 5) // 2
                self.manager.draw_text('tiny_bold', x2, 24,
                                       (255, 215, 0), count_str)

                # Closest flight info
                close_str = f"{callsign} {distance:.1f}MI"
                x3 = (96 - len(close_str) * 5) // 2
                self.manager.draw_text('tiny', x3, 36, (150, 150, 150), close_str)

                self.manager.swap_canvas()
                time.sleep(0.2)

        except Exception as e:
            logger.debug(f"Between-innings flight display error: {e}")

    def _draw_bases_original(self, game_info):
        """Draw bases exactly like original"""
        # Base positions from original
        second_base_x, second_base_y = 46, 7
        first_base_x, first_base_y = second_base_x + 7, second_base_y + 7
        third_base_x, third_base_y = second_base_x - 7, second_base_y + 7

        base_positions = {
            'first': (first_base_x, first_base_y),
            'second': (second_base_x, second_base_y),
            'third': (third_base_x, third_base_y)
        }

        # Draw base outlines
        for base_name, (bag_x, bag_y) in base_positions.items():
            original_y = bag_y
            for a in range(0, 5):
                self.manager.draw_pixel(bag_x + a, bag_y, 255, 255, 255)
                bag_y -= 1
                if a == 4:
                    for b in range(5, 10):
                        self.manager.draw_pixel(
                            bag_x + b, bag_y, 255, 255, 255)
                        bag_y += 1
                        if b == 9:
                            for c in range(10, 5, -1):
                                self.manager.draw_pixel(
                                    bag_x + c, bag_y, 255, 255, 255)
                                bag_y += 1
                                if c == 6:
                                    for d in range(5, 0, -1):
                                        self.manager.draw_pixel(
                                            bag_x + d, bag_y, 255, 255, 255)
                                        bag_y -= 1
            bag_y = original_y

        # Fill bases based on runners
        offense = game_info['liveData']['linescore']['offense']

        # First base
        if offense.get('first'):
            self._fill_base_original(first_base_x, first_base_y, 1)
        else:
            self._fill_base_original(first_base_x, first_base_y, 0)

        # Second base
        if offense.get('second'):
            self._fill_base_original(second_base_x, second_base_y, 1)
        else:
            self._fill_base_original(second_base_x, second_base_y, 0)

        # Third base
        if offense.get('third'):
            self._fill_base_original(third_base_x, third_base_y, 1)
        else:
            self._fill_base_original(third_base_x, third_base_y, 0)

    def _fill_base_original(self, hit_x, hit_y, filled):
        """Fill base like original"""
        next_y = 0
        if filled == 1:
            for fill in range(1, 6):
                for i in range(5):
                    self.manager.draw_pixel(
                        hit_x + i + fill, hit_y + i - next_y, 255, 255, 255)
                next_y += 1
        else:
            for fill in range(1, 6):
                for i in range(5):
                    self.manager.draw_pixel(
                        hit_x + i + fill, hit_y + i - next_y, 0, 51, 102)
                next_y += 1

    def _draw_scores(self, game_data, game_index):
        """Draw team scores"""
        if self.is_cubs_home:
            cubs_display_score = str(game_data[game_index]['home_score'])
            opp_display_score = str(game_data[game_index]['away_score'])
        else:
            cubs_display_score = str(game_data[game_index]['away_score'])
            opp_display_score = str(game_data[game_index]['home_score'])

        self._draw_score_in_box(cubs_display_score, 12)
        self._draw_score_in_box(opp_display_score, 29)

    def _draw_score_in_box(self, score_text: str, y: int) -> None:
        """Draw a score inside the 15px-wide score box (x=17-31).

        Double-digit scores are drawn digit-by-digit at a 6px advance
        (vs. the font's native 9px) so both digits fit cleanly within
        the box. The first digit renders at the box's left edge and
        the second sits close enough to leave ~1px of margin on the
        right, keeping "10"-"19" readable without overflowing.
        """
        if len(score_text) == 1:
            self.manager.draw_text('medium_bold', 20, y,
                                   Colors.BLACK, score_text)
        else:
            self.manager.draw_text('medium_bold', 17, y,
                                   Colors.BLACK, score_text[0])
            self.manager.draw_text('medium_bold', 23, y,
                                   Colors.BLACK, score_text[1])

    def _draw_game_info_improved(self, game_info, play_data):
        """Draw game info with improved pitch count"""
        linescore = game_info['liveData']['linescore']
        matchup = play_data['currentPlay']['matchup']
        count = play_data['currentPlay']['count']

        # Colors
        count_color = Colors.WHITE
        run_color = Colors.BLACK

        # Inning text
        inning_text_up = linescore['inningState'][:3]
        inning_text_down = linescore['currentInningOrdinal']
        self.manager.draw_text('tiny', 76, 8, count_color, inning_text_up)
        self.manager.draw_text('tiny', 76, 18, count_color, inning_text_down)

        # Count
        count_text = f"{count['balls']} - {count['strikes']}"
        self.manager.draw_text('tiny', 39, 30, count_color, count_text)

        # Outs
        out_text = str(linescore['outs'])
        out_text_a = ' OUTS'
        self.manager.draw_text('tiny', 72, 30, count_color, out_text)
        self.manager.draw_text('micro', 75, 29, count_color, out_text_a)

        # Batter text, alternating with the last completed play every 8s
        last_play = self._get_last_play_text(play_data)
        if last_play and int(time.time() / 8) % 2:
            self.manager.draw_text('micro', 2, 45, Colors.YELLOW, last_play)
        else:
            batter_text = f"BAT: {matchup['batter']['fullName']}"
            self.manager.draw_text('micro', 2, 45, run_color, batter_text)

        # Pitcher text
        pitching_text = matchup['pitcher']['fullName']
        self.manager.draw_text('micro', 2, 37, run_color, pitching_text)

        # IMPROVED PITCH COUNT - Get from current pitcher in boxscore
        try:
            current_pitcher_id = matchup['pitcher']['id']
            boxscore = game_info['liveData']['boxscore']['teams']

            # Get player data from both teams
            home_players = boxscore['home']['players']
            away_players = boxscore['away']['players']

            pitcher_key = f"ID{current_pitcher_id}"

            # Find pitcher and get their pitch count
            pitch_count = 0
            if pitcher_key in home_players:
                pitch_count = home_players[pitcher_key]['stats']['pitching']['numberOfPitches']
            elif pitcher_key in away_players:
                pitch_count = away_players[pitcher_key]['stats']['pitching']['numberOfPitches']

            pitch_count_text = f'P:{pitch_count}'

            # Position pitch count based on number of digits
            if pitch_count > 99:
                x_pos = 96 - (len(pitch_count_text) * 4 + 2)
            else:
                x_pos = 96 - (len(pitch_count_text) * 4)

            self.manager.draw_text(
                'micro', x_pos, 37, run_color, pitch_count_text)

        except (KeyError, IndexError, TypeError) as e:
            print(f"Error getting pitch count: {e}")

    def _check_score_changes(self, game_data, game_index):
        """Check for score changes and trigger animations"""
        if self.is_cubs_home:
            new_cubs_score = game_data[game_index]['home_score']
            new_opp_score = game_data[game_index]['away_score']
        else:
            new_cubs_score = game_data[game_index]['away_score']
            new_opp_score = game_data[game_index]['home_score']

        if new_cubs_score > self.cubs_score:
            self.animate_cubs_run()
            self.cubs_score = new_cubs_score

        if new_opp_score > self.opp_score:
            self.animate_opponent_run()
            self.opp_score = new_opp_score

    def animate_cubs_run(self):
        """Animate Cubs scoring a run"""
        # Baseball flying animation
        baseball_image = Image.open('./logos/baseball.png')
        run_image = Image.open('./logos/run_scored.png')
        run_image_flipped = run_image.transpose(Image.FLIP_LEFT_RIGHT)

        run_y = 15
        next_x = 25

        for x in range(25, 97):
            self.manager.clear_canvas()
            if x > next_x + 5:
                next_x += 5
                run_y -= 1

            output_image = Image.new("RGB", (96, 48))
            output_image.paste(run_image_flipped, (0, 12))
            output_image.paste(baseball_image, (x, run_y))
            self.manager.set_image(output_image.convert("RGB"), 0, 0)
            self.manager.swap_canvas()

        # Flash "RUN SCORED"
        for _ in range(3):
            self.manager.clear_canvas()
            self.manager.draw_text('medium_bold', 35, 19, Colors.WHITE, 'RUN')
            self.manager.draw_text('medium_bold', 21, 35,
                                   Colors.WHITE, 'SCORED')
            self.manager.draw_text('medium_bold', 36, 20,
                                   Colors.BRIGHT_YELLOW, 'RUN')
            self.manager.draw_text('medium_bold', 22, 36,
                                   Colors.BRIGHT_YELLOW, 'SCORED')
            self.manager.swap_canvas()
            time.sleep(0.5)
            self.manager.clear_canvas()
            self.manager.swap_canvas()
            time.sleep(0.5)

    def animate_opponent_run(self):
        """Animate opponent scoring a run with alert-style flash"""
        opp_image = self.manager.game_images['opponent'].resize((20, 20)).convert('RGBA')

        # Create logo on red background
        logo_bg = Image.new("RGB", opp_image.size, (180, 0, 0))
        logo_bg.paste(opp_image, (0, 0), opp_image)

        # Flash red/dark frames with opponent logo and "SCORES" text
        for cycle in range(4):
            # Red flash frame
            self.manager.clear_canvas()
            output_image = Image.new("RGB", (96, 48), (180, 0, 0))
            output_image.paste(logo_bg, (38, 1))
            self.manager.set_image(output_image.convert("RGB"), 0, 0)
            self.manager.draw_text('medium_bold', 21, 42, Colors.WHITE, 'SCORES')
            self.manager.swap_canvas()
            time.sleep(0.35)

            # Dark frame
            self.manager.clear_canvas()
            output_image = Image.new("RGB", (96, 48), (60, 0, 0))
            output_image.paste(logo_bg, (38, 1))
            self.manager.set_image(output_image.convert("RGB"), 0, 0)
            self.manager.draw_text('medium_bold', 21, 42, (120, 120, 120), 'SCORES')
            self.manager.swap_canvas()
            time.sleep(0.25)

    def display_game_over(self, game_data, game_index, gameid):
        """Display game over screen - Cubs always on left, opponent always on right.
        Cycles between game-over display and off-season content rotation."""
        game_info = retry_api_call(statsapi.get, 'game', {'gamePk': gameid})
        boxscore = game_info['liveData']['boxscore']['teams']
        linescore = game_info['liveData']['linescore']

        # Determine if Cubs are home team directly from game_info
        home_team_id = game_info['gameData']['teams']['home']['id']
        cubs_are_home = (home_team_id == TeamConfig.CUBS_TEAM_ID)

        # Get the actual final scores from the boxscore
        home_score = boxscore['home']['teamStats']['batting']['runs']
        away_score = boxscore['away']['teamStats']['batting']['runs']

        # Assign Cubs and opponent scores based on who's home
        if cubs_are_home:
            cubs_final_score = home_score
            opp_final_score = away_score
            cubs_stats = boxscore['home']['teamStats']
        else:
            cubs_final_score = away_score
            opp_final_score = home_score
            cubs_stats = boxscore['away']['teamStats']

        hits = cubs_stats['batting']['hits']
        errors = cubs_stats['fielding']['errors']
        innings = linescore['currentInning']

        # Determine win or loss
        cubs_won = cubs_final_score > opp_final_score
        result = "WIN" if cubs_won else "LOSS"

        # Function to draw the game over screen
        def draw_game_over_screen():
            self.manager.clear_canvas()

            # Create blue background image
            output_image = Image.new("RGB", (96, 48), (0, 51, 102))

            # Resize and paste team logos onto blue background (use alpha mask for transparency)
            cubs_resized = self.manager.game_images['cubs'].resize((26, 26)).convert('RGBA')
            opp_resized = self.manager.game_images['opponent'].resize((26, 26)).convert('RGBA')
            output_image.paste(cubs_resized, Positions.CUBS_IMAGE_GAMEOVER, cubs_resized)
            output_image.paste(opp_resized, Positions.OPP_IMAGE_GAMEOVER, opp_resized)

            # Set the image with blue background
            self.manager.set_image(output_image.convert("RGB"), 0, 0)

            # Draw "FINAL" text - centered and lowered to be fully visible
            self.manager.draw_text('small_bold', 33, 11,
                                Colors.WHITE, 'FINAL')

            # Draw "WIN" or "LOSS" text with color based on result
            result_x = 38 if result == "WIN" else 35
            result_color = Colors.YELLOW if result == "WIN" else Colors.RED
            self.manager.draw_text('small_bold', result_x, 21,
                                result_color, result)

            # Draw stats
            self.manager.draw_text(
                'micro', 29, 29, Colors.WHITE, f'INNINGS:{innings}')
            self.manager.draw_text(
                'micro', 29, 35, Colors.WHITE, f'HITS:   {hits}')
            self.manager.draw_text(
                'micro', 29, 41, Colors.WHITE, f'RUNS:   {cubs_final_score}')
            self.manager.draw_text(
                'micro', 29, 47, Colors.WHITE, f'ERRORS: {errors}')

            # Cubs score always on LEFT side
            if cubs_final_score >= 10:
                cubs_x = 5
            else:
                cubs_x = 9

            # Opponent score always on RIGHT side
            if opp_final_score >= 10:
                opp_x = 70
            else:
                opp_x = 75

            # Draw Cubs score on LEFT
            self.manager.draw_text('large_bold', cubs_x,
                                45, Colors.WHITE, str(cubs_final_score))

            # Draw opponent score on RIGHT
            self.manager.draw_text('large_bold', opp_x,
                                45, Colors.WHITE, str(opp_final_score))

            self.manager.swap_canvas()

        # Function to display animated W flag for 15 seconds
        def display_w_flag_cycle():
            try:
                # Load the W flag GIF
                w_flag = Image.open('./W.gif')

                # Get all frames from the GIF
                frames = []
                try:
                    while True:
                        # Resize frame to fit display and convert to RGB
                        frame = w_flag.copy().convert('RGB')
                        frame = frame.resize((96, 48), Image.LANCZOS)
                        frames.append(frame)
                        w_flag.seek(w_flag.tell() + 1)
                except EOFError:
                    pass  # End of frames

                if not frames:
                    print("No frames found in W.gif")
                    return False

                # Get frame duration (in milliseconds, default to 100ms if not specified)
                try:
                    duration = w_flag.info.get(
                        'duration', 100) / 1000.0  # Convert to seconds
                except:
                    duration = 0.1  # Default to 100ms per frame

                # Display animation for 15 seconds
                start_time = time.time()
                frame_index = 0

                while time.time() - start_time < 15:
                    self.manager.clear_canvas()
                    self.manager.set_image(frames[frame_index], 0, 0)
                    self.manager.swap_canvas()

                    time.sleep(duration)
                    frame_index = (frame_index + 1) % len(frames)

                return True

            except FileNotFoundError:
                print("W.gif not found in ./logos/ directory")
                return False
            except Exception as e:
                print(f"Error displaying W flag: {e}")
                return False

        # Main loop - final score interleaved between rotation segments
        current_date = pendulum.now().format('YYYY-MM-DD')

        def show_game_over_interlude():
            """Show the game over screen (and W flag on wins) for the
            interlude period. Returns True when the loop should exit."""
            nonlocal cubs_won
            screen_start = time.time()
            while time.time() - screen_start < GameConfig.GAME_OVER_INTERLUDE_TIME:
                draw_game_over_screen()
                time.sleep(0.5)

                # Check exit conditions during game over screen display
                if pendulum.now().format('YYYY-MM-DD') != current_date:
                    return True
                if pendulum.now().format('HH:MM') == '04:00':
                    return True
                if game_data[game_index]['doubleheader'] == 'S':
                    return True

            # If Cubs won, show W flag for 15 seconds
            if cubs_won:
                flag_success = display_w_flag_cycle()
                # If flag failed to load, just continue with game over screen only
                if not flag_success:
                    cubs_won = False  # Don't try to show flag again
            return False

        # Show the final score right away; afterwards the rotation's
        # between-segment callback keeps bringing it back
        show_game_over_interlude()

        while True:
            # Check if it's time to exit
            over_date = pendulum.now().format('YYYY-MM-DD')
            current_time = pendulum.now().format('HH:MM')

            # Exit conditions
            if over_date != current_date or current_time == '04:00':
                break

            if game_data[game_index]['doubleheader'] == 'S':
                time.sleep(GameConfig.GAME_OVER_WAIT_TIME)
                break

            # Cycle through off-season content (weather, Bears, PGA, etc.)
            # with the game over screen between every segment
            has_handler = getattr(self, 'off_season_handler', None) is not None
            logger.info(f"Game over loop: has off_season_handler={has_handler}, cubs_won={cubs_won}")
            if has_handler:
                try:
                    logger.info("Starting post-game rotation with game-over interludes")
                    self.off_season_handler._display_rotation_cycle(
                        between_callback=show_game_over_interlude)
                    logger.info("Post-game rotation cycle completed")
                except Exception as e:
                    logger.error(f"Error in post-game rotation cycle: {e}")
                    import traceback
                    logger.debug(traceback.format_exc())
                    time.sleep(10)
            elif show_game_over_interlude():
                break

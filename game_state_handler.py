"""Handlers for different game states and display modes"""

from __future__ import annotations

import time
import pendulum
import statsapi
from PIL import Image, ImageDraw
from rgbmatrix import graphics
from typing import TYPE_CHECKING, Any

from scoreboard_config import Colors, Positions, GameConfig, TeamConfig, RGBColor, DisplayConfig, get_scroll_delay
from retry import retry_api_call

if TYPE_CHECKING:
    from scoreboard_manager import ScoreboardManager


class GameStateHandler:
    """Handles display for different game states"""

    def __init__(self, scoreboard_manager: ScoreboardManager) -> None:
        """Initialize with reference to main scoreboard manager"""
        self.manager = scoreboard_manager
        self.scroll_position: int = 96  # For scrolling text
        self.rain_drops: list[dict[str, Any]] = []  # Lazy-initialized

    def display_warmup(
        self,
        game_data: list[dict[str, Any]],
        game_index: int,
        lineup: str | None,
        gameid: int
    ) -> None:
        """Display warmup/pre-game screen"""
        start_time: str = self.manager.format_game_time(game_data, game_index)
        self._display_pregame_base(
            "WARM UP", Colors.GREEN, start_time, lineup or "", game_data, game_index, gameid)

    def display_delayed(
        self,
        game_data: list[dict[str, Any]],
        game_index: int,
        lineup: str | None,
        gameid: int
    ) -> None:
        """Display delayed game screen with rain animation"""
        start_time: str = self.manager.format_game_time(game_data, game_index)
        # Detect if the delay reason mentions rain for a more specific label
        status: str = game_data[game_index].get('status', '')
        label: str = "RAIN DELAY" if 'rain' in status.lower() else "GAME DELAY"
        self._display_delay_animated(
            label, start_time, lineup or "", game_data, game_index, gameid)

    def display_postponed(
        self,
        game_data: list[dict[str, Any]],
        game_index: int,
        lineup: str | None,
        gameid: int
    ) -> None:
        """Display postponed game screen with rain animation.

        Shows 'CHICAGO CUBS VS {OPPONENT}' instead of lineup since the game
        isn't being played. Single-pass so the caller can cycle other content.
        """
        start_time: str = self.manager.format_game_time(game_data, game_index)
        opponent_name: str = self._get_opponent_name(gameid)
        matchup_text: str = f"CHICAGO CUBS VS {opponent_name.upper()}"
        self._display_delay_animated(
            "POSTPONED", start_time, lineup or "", game_data, game_index, gameid,
            single_pass=True, scroll_text_override=matchup_text)

    def _get_opponent_name(self, gameid: int) -> str:
        """Fetch the opposing team's name for a given game."""
        try:
            game_info: dict[str, Any] = retry_api_call(
                statsapi.get, 'game', {'gamePk': gameid}
            )
            home = game_info['gameData']['teams']['home']
            away = game_info['gameData']['teams']['away']
            if home['abbreviation'] == 'CHC':
                return away['name']
            return home['name']
        except Exception:
            return "OPPONENT"

    def display_suspended(
        self,
        game_data: list[dict[str, Any]],
        game_index: int,
        lineup: str | None,
        gameid: int
    ) -> None:
        """Display suspended game screen with rain animation"""
        start_time: str = self.manager.format_game_time(game_data, game_index)
        self._display_delay_animated(
            "SUSPENDED", start_time, lineup or "", game_data, game_index, gameid)

    def display_cancelled(
        self,
        game_data: list[dict[str, Any]],
        game_index: int,
        lineup: str | None,
        gameid: int
    ) -> None:
        """Display cancelled game screen with rain animation (single pass)"""
        start_time: str = self.manager.format_game_time(game_data, game_index)
        self._display_delay_animated(
            "CANCELLED", start_time, lineup or "", game_data, game_index, gameid,
            single_pass=True)

    def _init_rain_drops(self) -> None:
        """Initialize rain drop positions (called lazily on first delay display)"""
        import random
        self.rain_drops = []
        for _ in range(14):
            self.rain_drops.append({
                'x': random.randint(0, 95),
                'y': random.randint(-10, 47),
                'speed': random.uniform(1.8, 3.0)
            })

    def _draw_stormy_background(self) -> None:
        """Paint a dark stormy-blue gradient background across the matrix"""
        for y in range(DisplayConfig.MATRIX_ROWS):
            # Interpolate from (5, 15, 40) top to (10, 25, 60) bottom
            t = y / float(DisplayConfig.MATRIX_ROWS - 1)
            r = int(5 + t * 5)
            g = int(15 + t * 10)
            b = int(40 + t * 20)
            for x in range(DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, y, r, g, b)

    def _animate_rain_drops(self) -> None:
        """Advance and draw rain drops (2-pixel streaks)"""
        import random
        for drop in self.rain_drops:
            y = int(drop['y'])
            x = int(drop['x'])
            if 0 <= y < DisplayConfig.MATRIX_ROWS:
                self.manager.draw_pixel(x, y, 180, 200, 220)
            if 0 <= y + 1 < DisplayConfig.MATRIX_ROWS:
                self.manager.draw_pixel(x, y + 1, 160, 180, 200)
            drop['y'] += drop['speed']
            if drop['y'] > DisplayConfig.MATRIX_ROWS:
                drop['y'] = random.randint(-8, -1)
                drop['x'] = random.randint(0, 95)
                drop['speed'] = random.uniform(1.8, 3.0)

    def _display_delay_animated(
        self,
        label: str,
        start_time: str,
        lineup: str,
        game_data: list[dict[str, Any]],
        game_index: int,
        gameid: int,
        single_pass: bool = False,
        scroll_text_override: str | None = None
    ) -> None:
        """Animated delay/postponement/cancellation screen with falling rain.

        If scroll_text_override is provided, it's shown at the bottom instead
        of the lineup and is NOT refreshed between passes.
        """
        if not self.rain_drops:
            self._init_rain_drops()

        use_override: bool = scroll_text_override is not None
        scroll_text: str = scroll_text_override if use_override else lineup

        # Terminal statuses — exit the loop when status transitions to these
        resume_statuses = {'In Progress', 'Warmup', 'Pre-Game', 'Final', 'Game Over'}

        refresh_counter: int = 0
        refresh_interval: int = 200  # Re-check status every ~200 frames
        passes_completed: int = 0

        # Precompute centered X for label (use medium_bold: ~9px per char)
        label_x: int = max(0, (DisplayConfig.MATRIX_COLS - len(label) * 9) // 2)

        while True:
            self.manager.clear_canvas()
            self._draw_stormy_background()
            self._animate_rain_drops()

            # Divider line above label
            for x in range(DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, 14, 255, 255, 255)

            # Status label
            self.manager.draw_text(
                'medium_bold', label_x, 12, Colors.BRIGHT_YELLOW, label)

            # Start time info
            self.manager.draw_text('small', 17, 24, Colors.WHITE, 'START TIME')
            self.manager.draw_text('small', 36, 32, Colors.WHITE, start_time)

            # Scroll text at bottom (lineup or custom override)
            self.scroll_position -= 1
            text_length: int = len(scroll_text) * 7
            if self.scroll_position + text_length < 0:
                self.scroll_position = 96
                passes_completed += 1
                # Refresh lineup on loop (only when not using override text)
                if not use_override and scroll_text:
                    scroll_text = self.manager.get_lineup(gameid)
                # Bail after one scroll pass when requested (cancelled, postponed)
                if single_pass and passes_completed >= 1:
                    break

            self.manager.draw_text(
                'lineup', self.scroll_position, 45, Colors.WHITE, scroll_text)

            # Split-squad indicator
            if self.manager.split_squad_indicator:
                self._draw_split_squad_indicator()

            self.manager.swap_canvas()
            time.sleep(0.03)

            # Split-squad rotation timeout
            if self.manager.split_squad_indicator:
                if time.time() >= self.manager.split_squad_switch_time:
                    break

            # Periodically check if the delay is over
            refresh_counter += 1
            if refresh_counter >= refresh_interval:
                refresh_counter = 0
                try:
                    game_data = self.manager.get_schedule()
                    current_status: str = game_data[game_index].get('status', '')
                    if current_status in resume_statuses:
                        break
                except Exception:
                    # If status check fails, keep showing the delay screen
                    pass

    def _display_pregame_base(
        self,
        status_text: str,
        bg_color: RGBColor,
        start_time: str,
        lineup: str,
        game_data: list[dict[str, Any]],
        game_index: int,
        gameid: int
    ) -> None:
        """Base method for pregame displays (warmup, delayed, postponed) - OPTIMIZED"""
        # Compare times for game start
        game_datetime: str = game_data[game_index]['game_datetime'][-9:19]
        time_compare: str = game_datetime[:5]
        current_time: str = pendulum.now().format('HH:MM')

        # Counter for when to refresh data (every 100 iterations instead of constantly)
        refresh_counter: int = 0
        refresh_interval: int = 1000  # Refresh data every 100 scroll iterations

        while current_time != time_compare and game_data[game_index]['status'] not in ['In Progress', 'Final']:
            self.manager.clear_canvas()
            self.manager.fill_canvas(*bg_color)

            # Draw divider line
            for x in range(96):
                self.manager.draw_pixel(x, 14, 255, 255, 255)

            # Draw status text
            x_offset: int = 17 if status_text != "POSTPONED" else 8
            self.manager.draw_text('medium_bold', x_offset,
                                   12, Colors.WHITE, status_text)
            self.manager.draw_text('small', 17, 24, Colors.WHITE, 'START TIME')
            self.manager.draw_text('small', 36, 32, Colors.WHITE, start_time)

            # Scroll lineup
            self.scroll_position -= 1
            text_length: int = len(lineup) * 7  # Approximate character width

            if self.scroll_position + text_length < 0:
                self.scroll_position = 96
                # Only refresh lineup when text loops, not every frame
                lineup = self.manager.get_lineup(gameid)

            self.manager.draw_text(
                'lineup', self.scroll_position, 45, Colors.WHITE, lineup)

            # Draw split-squad indicator if active
            if self.manager.split_squad_indicator:
                self._draw_split_squad_indicator()

            self.manager.swap_canvas()

            # Use slower scroll speed for warmup readability
            time.sleep(0.03)

            # Exit if in split-squad mode and it's time to switch games
            if self.manager.split_squad_indicator:
                if time.time() >= self.manager.split_squad_switch_time:
                    break

            # Increment refresh counter
            refresh_counter += 1

            # Only check for status changes periodically, not every frame
            if refresh_counter >= refresh_interval:
                refresh_counter = 0
                # Check for status changes
                game_data = self.manager.get_schedule()
                if game_data[game_index]['status'] == 'In Progress':
                    break
                current_time = pendulum.now().format('HH:MM')
            else:
                # Just update current time without hitting the API
                current_time = pendulum.now().format('HH:MM')

    def _draw_split_squad_indicator(self) -> None:
        """
        Draw split-squad game indicator in top-right corner.
        Shows which game is being displayed (e.g., "1/2" or "2/2").
        """
        indicator = self.manager.split_squad_indicator
        if not indicator:
            return

        # Draw a small background box in top-right corner
        box_x = 88
        box_y = 0

        # Dark background for visibility
        for y in range(box_y, box_y + 8):
            for x in range(box_x, DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, y, 40, 40, 40)

        # Draw the indicator text (e.g., "1/2") in yellow
        self.manager.draw_text('micro', box_x + 1, 6, Colors.YELLOW, indicator)

    def display_no_game(
        self, game_data: list[dict[str, Any]], game_index: int,
        cycle_content: bool = False
    ) -> None:
        """Display when no game is currently playing"""
        gameid: int = game_data[game_index]['game_id']
        game_date: str = game_data[game_index]['game_date']
        game_time: str = self.manager.format_game_time(game_data, game_index)
        game_type: str = game_data[game_index].get('game_type', 'R')

        # Get opponent info
        game_info: dict[str, Any] = retry_api_call(
            statsapi.get, 'game', {'gamePk': gameid}
        )
        if game_info['gameData']['teams']['home']['abbreviation'] == 'CHC':
            away: str = 'away'
        else:
            away = 'home'
        away_team: str = game_info['gameData']['teams'][away]['name']

        # Create next game text
        pitchers: str = self.manager.get_pitchers(game_data, game_index, gameid)
        if game_type in ('S', 'E'):
            next_game_text: str = f'SPRING TRAINING {game_date[5:]} at {game_time} vs {away_team}     {pitchers}'
        else:
            next_game_text: str = f'NEXT GAME {game_date[5:]} at {game_time} vs {away_team}     {pitchers}'

        # Pre-generate Cubs gradient background (matches Cubs Facts screen)
        gradient_bg: Image.Image = Image.new("RGB", (96, 48))
        pixels = gradient_bg.load()
        for y in range(34):
            blue_intensity = int(102 + (y * 0.5))
            for x in range(96):
                pixels[x, y] = (0, 51, blue_intensity)
        for y in range(34, 48):
            for x in range(96):
                pixels[x, y] = (0, 0, 0)

        # Main display loop
        while True:
            self.manager.clear_canvas()

            # Display Cubs gradient background with marquee image (matches Cubs Facts screen)
            output_image: Image.Image = gradient_bg.copy()
            output_image.paste(self.manager.game_images['marquee'], (0, 0))
            self.manager.canvas.SetImage(output_image.convert("RGB"), 0, 0)

            # Scroll next game text
            self.scroll_position -= 1
            text_length: int = len(next_game_text) * 9
            if self.scroll_position + text_length < 0:
                self.scroll_position = 96

                # Spring training or offseason content mode: return after one scroll pass
                # to cycle through other content
                if game_type in ('S', 'E') or cycle_content:
                    # Still show standings/playoff info before breaking
                    if cycle_content and game_type == 'R':
                        self._display_standings()
                    elif cycle_content and game_type not in ('S', 'E', 'R'):
                        self._display_playoff_info(game_data, game_index)
                    break

                # Show standings for regular season, playoff info for postseason
                if game_type == 'R':
                    self._display_standings()
                else:
                    self._display_playoff_info(game_data, game_index)

                # Check game status
                game_data = self.manager.get_schedule()
                if self._should_transition_state(game_data, game_index):
                    break

            self.manager.draw_text(
                'medium_bold', int(self.scroll_position), 48, Colors.YELLOW, next_game_text)

            # Draw split-squad indicator if active
            if self.manager.split_squad_indicator:
                self._draw_split_squad_indicator()

            self.manager.swap_canvas()
            # Match Cubs Facts scroll speed from config
            try:
                import json, os
                _cfg_path = '/home/pi/config.json'
                if os.path.exists(_cfg_path):
                    with open(_cfg_path, 'r') as _f:
                        _cfg = json.load(_f)
                else:
                    _cfg = {}
            except Exception:
                _cfg = {}
            time.sleep(get_scroll_delay(_cfg.get('scroll_speed_cubs_facts', 5)))

            # Exit if in split-squad mode and it's time to switch games
            if self.manager.split_squad_indicator:
                if time.time() >= self.manager.split_squad_switch_time:
                    break

    def _display_standings(self) -> None:
        """Display division standings"""
        self.manager.clear_canvas()
        self.manager.fill_canvas(*Colors.GREEN)

        # Get standings
        standings: list[dict[str, Any]] = retry_api_call(
            statsapi.get, 'standings', {'leagueId': TeamConfig.NL_LEAGUE_ID}
        )['records'][1]['teamRecords']

        # Draw title
        self.manager.draw_text(
            'tiny_bold', 3, 8, Colors.YELLOW, 'DIVISION STANDINGS')

        # Draw each team
        y_position: int = 15
        for team_record in standings:
            team_id: int = team_record['team']['id']
            team_info: dict[str, Any] = retry_api_call(
                statsapi.get, 'team', {'teamId': team_id}
            )['teams'][0]
            team_abv: str = team_info['abbreviation']

            games_back: str = team_record['gamesBack']
            if games_back == '-':
                games_back = ''

            record: str = f"{team_record['leagueRecord']['wins']}-{team_record['leagueRecord']['losses']} {team_record['leagueRecord']['pct']}"

            self.manager.draw_text(
                'micro', 5, y_position, Colors.WHITE, team_abv)
            self.manager.draw_text(
                'micro', 26, y_position, Colors.WHITE, record)
            self.manager.draw_text(
                'micro', 75, y_position, Colors.WHITE, games_back)

            y_position += 8

        self.manager.swap_canvas()
        time.sleep(GameConfig.NO_GAME_STANDINGS_DISPLAY_TIME)

    def _display_playoff_info(
        self, game_data: list[dict[str, Any]], game_index: int
    ) -> None:
        """Display playoff series information"""
        self.manager.clear_canvas()
        self.manager.fill_canvas(*Colors.CUBS_BLUE)

        # Get game data
        gameid: int = game_data[game_index]['game_id']
        game_type: str = game_data[game_index].get('game_type', 'F')
        series_status: str = game_data[game_index].get('series_status', '')

        # Get full game info
        game_info: dict[str, Any] = retry_api_call(
            statsapi.get, 'game', {'gamePk': gameid}
        )

        # Determine opponent
        if game_info['gameData']['teams']['home']['abbreviation'] == 'CHC':
            opp_team: dict[str, Any] = game_info['gameData']['teams']['away']
        else:
            opp_team = game_info['gameData']['teams']['home']

        opp_name: str = opp_team['name']
        opp_abbr: str = opp_team['abbreviation']

        # Map game type to display name
        game_type_names: dict[str, str] = {
            'F': 'WILD CARD',
            'D': 'DIVISION SERIES',
            'L': 'LEAGUE CHAMPIONSHIP',
            'W': 'WORLD SERIES'
        }
        series_name: str = game_type_names.get(game_type, 'PLAYOFFS')

        # Draw title
        title_x: int = max(2, (96 - len(series_name) * 5) // 2)  # Center the title
        self.manager.draw_text('tiny_bold', title_x, 8,
                               Colors.BRIGHT_YELLOW, series_name)

        # Draw opponent info
        opponent_text: str = f"vs {opp_abbr}"
        opp_x: int = max(2, (96 - len(opponent_text) * 9) // 2)
        self.manager.draw_text('medium_bold', opp_x, 21,
                               Colors.WHITE, opponent_text)

        # Draw series status if available
        if series_status:
            # Parse and display series status
            status_parts: list[str] = series_status.split()
            if len(status_parts) >= 3:
                # Format: "CHC leads 1-0" or "Series tied 1-1"
                team_part: str = status_parts[0]
                status_word: str = status_parts[1]  # "leads" or "tied"
                score_part: str = status_parts[-1]  # "1-0"

                color: RGBColor
                display_text: str
                if team_part == 'CHC':
                    color = Colors.BRIGHT_YELLOW
                    display_text = "CUBS LEAD"
                elif status_word.lower() == 'tied':
                    color = Colors.WHITE
                    display_text = "SERIES TIED"
                else:
                    color = Colors.RED
                    display_text = f"{team_part} LEAD"

                # Display status
                text_x: int = max(2, (96 - len(display_text) * 5) // 2)
                self.manager.draw_text(
                    'tiny_bold', text_x, 33, color, display_text)

                # Display series score
                score_x: int = max(2, (96 - len(score_part) * 7) // 2)
                self.manager.draw_text(
                    'standard_bold', score_x, 45, Colors.WHITE, score_part)
        else:
            # No series status available yet
            series_begins_text: str = 'SERIES BEGINS'
            series_begins_x: int = max(2, (96 - len(series_begins_text) * 5) // 2)
            self.manager.draw_text(
                'tiny', series_begins_x, 31, Colors.WHITE, series_begins_text)

            # Add game date below
            # Get MM-DD from YYYY-MM-DD
            game_date: str = game_data[game_index]['game_date'][5:]
            date_x: int = max(2, (96 - len(game_date) * 9) // 2)
            self.manager.draw_text(
                'medium_bold', date_x, 45, Colors.BRIGHT_YELLOW, game_date)

        self.manager.swap_canvas()
        time.sleep(GameConfig.NO_GAME_STANDINGS_DISPLAY_TIME)

    def _should_transition_state(
        self, game_data: list[dict[str, Any]], game_index: int
    ) -> bool:
        """Check if we should transition to a different game state"""
        status: str = game_data[game_index]['status']
        return status in ['Warmup', 'Pre-Game', 'In Progress', 'Delayed', 'Postponed']

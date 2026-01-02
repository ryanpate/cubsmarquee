"""Handlers for different game states and display modes"""

from __future__ import annotations

import time
import pendulum
import statsapi
from PIL import Image
from rgbmatrix import graphics
from typing import TYPE_CHECKING, Any

from scoreboard_config import Colors, Positions, GameConfig, TeamConfig, RGBColor
from retry import retry_api_call

if TYPE_CHECKING:
    from scoreboard_manager import ScoreboardManager


class GameStateHandler:
    """Handles display for different game states"""

    def __init__(self, scoreboard_manager: ScoreboardManager) -> None:
        """Initialize with reference to main scoreboard manager"""
        self.manager = scoreboard_manager
        self.scroll_position: int = 96  # For scrolling text

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
        """Display delayed game screen"""
        start_time: str = self.manager.format_game_time(game_data, game_index)
        self._display_pregame_base(
            "DELAYED", Colors.DELAY_YELLOW, start_time, lineup or "", game_data, game_index, gameid)

    def display_postponed(
        self,
        game_data: list[dict[str, Any]],
        game_index: int,
        lineup: str | None,
        gameid: int
    ) -> None:
        """Display postponed game screen"""
        start_time: str = self.manager.format_game_time(game_data, game_index)
        self._display_pregame_base(
            "POSTPONED", Colors.POSTPONE_RED, start_time, lineup or "", game_data, game_index, gameid)

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
            self.manager.swap_canvas()

            # Use consistent scroll speed
            time.sleep(GameConfig.SCROLL_SPEED)

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

    def display_no_game(
        self, game_data: list[dict[str, Any]], game_index: int
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
        next_game_text: str = f'NEXT GAME {game_date[5:]} at {game_time} vs {away_team}     {pitchers}'

        # Main display loop
        while True:
            self.manager.clear_canvas()

            # Display marquee image
            output_image: Image.Image = Image.new("RGB", (96, 48))
            output_image.paste(self.manager.game_images['marquee'], (0, 0))
            self.manager.canvas.SetImage(output_image.convert("RGB"), 0, 0)

            # Scroll next game text
            self.scroll_position -= 1
            text_length: int = len(next_game_text) * 7
            if self.scroll_position + text_length < 0:
                self.scroll_position = 96

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
                'standard_bold', self.scroll_position, 46, Colors.YELLOW, next_game_text)
            self.manager.swap_canvas()
            time.sleep(GameConfig.SCROLL_SPEED)

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

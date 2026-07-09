"""Playoff race display - Cubs division and wild card position"""

from __future__ import annotations

import time
import pendulum
import statsapi
from PIL import Image
from typing import TYPE_CHECKING, Any

from scoreboard_config import Colors, DisplayConfig, TeamConfig
from retry import retry_api_call
from logger import get_logger

logger = get_logger("playoff_race")

if TYPE_CHECKING:
    from scoreboard_manager import ScoreboardManager

RACE_CACHE_SECONDS = 1800  # standings barely move within a half hour


class PlayoffRaceDisplay:
    """Shows the Cubs' playoff position during the second half of the season"""

    def __init__(self, scoreboard_manager: ScoreboardManager) -> None:
        self.manager = scoreboard_manager
        self._race_cache: dict[str, Any] | None = None
        self._race_cached_at: float = 0.0

    @staticmethod
    def is_race_season() -> bool:
        """Second half of the regular season (July through September)"""
        return pendulum.now('America/Chicago').month in (7, 8, 9)

    @staticmethod
    def _ordinal(rank: int) -> str:
        return {1: '1ST', 2: '2ND', 3: '3RD'}.get(rank, f'{rank}TH')

    @staticmethod
    def _parse_race_data(standings: dict[str, Any]) -> dict[str, Any] | None:
        """Extract the Cubs' division/wild-card position from a standings
        API response, or None if the Cubs aren't in it."""
        for record in standings.get('records', []):
            for team_record in record.get('teamRecords', []):
                if (team_record.get('team', {}).get('id')
                        != TeamConfig.CUBS_TEAM_ID):
                    continue
                wc_rank = team_record.get('wildCardRank')
                return {
                    'div_rank': int(team_record['divisionRank']),
                    'gb': team_record.get('gamesBack', '-'),
                    'wc_rank': int(wc_rank) if wc_rank else None,
                    'wc_gb': team_record.get('wildCardGamesBack', '-'),
                    'magic': team_record.get('magicNumber'),
                    'wins': team_record.get('wins', 0),
                    'losses': team_record.get('losses', 0),
                }
        return None

    def _format_race_lines(self, race: dict[str, Any]) -> list[str]:
        """The three text rows of the playoff race screen"""
        if race['div_rank'] == 1:
            div_line = 'NL CENT: 1ST'
            middle = (f"MAGIC NUMBER: {race['magic']}" if race['magic']
                      else 'DIVISION LEADER')
        else:
            div_line = f"NL CENT: {self._ordinal(race['div_rank'])} -{race['gb']}"
            if race['wc_rank']:
                wc_gb = str(race['wc_gb'])
                if not wc_gb.startswith('+'):
                    wc_gb = f"-{wc_gb}"
                middle = f"WILD CARD: {self._ordinal(race['wc_rank'])} {wc_gb}"
            else:
                middle = 'WILD CARD: OUT'

        return [div_line, middle, f"RECORD: {race['wins']}-{race['losses']}"]

    def _get_race_data(self) -> dict[str, Any] | None:
        """Fetch (and cache) the Cubs' current race position"""
        now = time.time()
        if (self._race_cache is not None
                and now - self._race_cached_at < RACE_CACHE_SECONDS):
            return self._race_cache

        try:
            standings = retry_api_call(
                statsapi.get, 'standings',
                {'leagueId': TeamConfig.NL_LEAGUE_ID,
                 'season': pendulum.now().year},
            )
            self._race_cache = self._parse_race_data(standings)
            self._race_cached_at = now
        except Exception as e:
            logger.warning("Could not fetch standings for playoff race: %s", e)
        return self._race_cache

    def display_playoff_race(self, duration: int = 120) -> None:
        """Show the playoff race screen for the given duration"""
        race = self._get_race_data()
        if not race:
            print("Playoff race data unavailable - skipping")
            return

        lines = self._format_race_lines(race)
        print(f"Displaying playoff race: {lines}")

        start = time.time()
        while time.time() - start < duration:
            self._draw_race_screen(lines)
            time.sleep(1)

    def _draw_race_screen(self, lines: list[str]) -> None:
        """Draw the title and the three race lines on a Cubs blue field"""
        self.manager.clear_canvas()
        background = Image.new(
            'RGB', (DisplayConfig.MATRIX_COLS, DisplayConfig.MATRIX_ROWS),
            Colors.CUBS_BLUE)
        self.manager.set_image(background, 0, 0)

        title = 'PLAYOFF RACE'
        title_x = max(0, (DisplayConfig.MATRIX_COLS - len(title) * 6) // 2)
        self.manager.draw_text('small_bold', title_x, 10, Colors.YELLOW, title)
        for x in range(8, DisplayConfig.MATRIX_COLS - 8):
            self.manager.draw_pixel(x, 13, 255, 223, 0)

        for line, y in zip(lines, (25, 35, 45)):
            self.manager.draw_text('micro', 3, y, Colors.WHITE, line)

        self.manager.swap_canvas()

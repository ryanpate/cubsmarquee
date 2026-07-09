"""Playoff race display - Cubs division and wild card position"""

from __future__ import annotations

import time
import pendulum
import statsapi
from PIL import Image
from typing import TYPE_CHECKING, Any

from scoreboard_config import Colors, DisplayConfig, GameConfig, TeamConfig
from retry import retry_api_call
from logger import get_logger

logger = get_logger("playoff_race")

if TYPE_CHECKING:
    from scoreboard_manager import ScoreboardManager

RACE_CACHE_SECONDS = 1800  # standings barely move within a half hour

GB_GREEN = (60, 200, 90)
GB_RED = (255, 90, 90)
MARQUEE_RED = (196, 30, 58)
STRIP_RED = (170, 30, 30)
STRIP_NAVY = (10, 25, 55)


class PlayoffRaceDisplay:
    """Shows the Cubs' playoff position during the second half of the season"""

    def __init__(self, scoreboard_manager: ScoreboardManager) -> None:
        self.manager = scoreboard_manager
        self._race_cache: dict[str, Any] | None = None
        self._race_cached_at: float = 0.0
        self._abbr_cache: dict[int, str] = {}
        self._logo_cache: dict[tuple[str, int], Image.Image | None] = {}

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
            team_records = record.get('teamRecords', [])
            cubs = next(
                (tr for tr in team_records
                 if tr.get('team', {}).get('id') == TeamConfig.CUBS_TEAM_ID),
                None)
            if cubs is None:
                continue
            leader = next(
                (tr for tr in team_records
                 if tr.get('divisionRank') == '1'), None)
            wc_rank = cubs.get('wildCardRank')
            return {
                'div_rank': int(cubs['divisionRank']),
                'gb': cubs.get('gamesBack', '-'),
                'wc_rank': int(wc_rank) if wc_rank else None,
                'wc_gb': cubs.get('wildCardGamesBack', '-'),
                'magic': cubs.get('magicNumber'),
                'wins': cubs.get('wins', 0),
                'losses': cubs.get('losses', 0),
                'leader_id': (leader or {}).get('team', {}).get('id'),
            }
        return None

    def _format_race_rows(
        self, race: dict[str, Any]
    ) -> list[tuple[str, str, str]]:
        """The three (label, value, games-back) rows of the race screen"""
        if race['div_rank'] == 1:
            div_row = ('NL CENT', '1ST', '')
            middle = ('MAGIC #', str(race['magic']) if race['magic'] else '--', '')
        else:
            # Games back is unsigned when behind (color carries direction),
            # '+' when ahead - standard scoreboard convention
            div_row = ('NL CENT', self._ordinal(race['div_rank']),
                       str(race['gb']))
            wc_gb = str(race['wc_gb'])
            try:
                deficit = 0.0 if wc_gb.startswith('+') else float(wc_gb)
            except ValueError:
                deficit = 0.0
            # Double-digit rank or deficit: effectively out (and too wide)
            if race['wc_rank'] and race['wc_rank'] < 10 and deficit < 10:
                middle = ('WILDCARD', self._ordinal(race['wc_rank']), wc_gb)
            else:
                middle = ('WILDCARD', 'OUT', '')

        return [div_row, middle,
                ('RECORD', f"{race['wins']}-{race['losses']}", '')]

    @staticmethod
    def _in_playoff_position(race: dict[str, Any]) -> bool:
        """Would the Cubs be in the postseason if the season ended today?"""
        if race['div_rank'] == 1:
            return True
        return race['wc_rank'] is not None and race['wc_rank'] <= 3

    def _leader_abbr(self, team_id: int | None) -> str | None:
        """Abbreviation for a team id (cached; None when unavailable)"""
        if not team_id:
            return None
        if team_id in self._abbr_cache:
            return self._abbr_cache[team_id]
        try:
            team = retry_api_call(
                statsapi.get, 'team', {'teamId': team_id})['teams'][0]
            self._abbr_cache[team_id] = team['abbreviation']
            return self._abbr_cache[team_id]
        except Exception as e:
            logger.warning("Could not fetch team %s: %s", team_id, e)
            return None

    def _load_logo(self, name: str, size: int) -> Image.Image | None:
        """Team logo scaled to fit a size x size box (cached)"""
        key = (name, size)
        if key not in self._logo_cache:
            try:
                logo = Image.open(f'./logos/{name}.png').convert('RGBA')
                logo.thumbnail((size, size), Image.LANCZOS)
                self._logo_cache[key] = logo
            except OSError:
                self._logo_cache[key] = None
        return self._logo_cache[key]

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

    def display_playoff_race(
        self, duration: int = GameConfig.PLAYOFF_RACE_DISPLAY_TIME
    ) -> None:
        """Show the playoff race screen for the given duration"""
        race = self._get_race_data()
        if not race:
            print("Playoff race data unavailable - skipping")
            return

        print(f"Displaying playoff race: {self._format_race_rows(race)}")
        start = time.time()
        while time.time() - start < duration:
            self._draw_race_frame(race)
            time.sleep(1)

    @staticmethod
    def _chase_strip_visible(race: dict[str, Any], tick: float) -> bool:
        """Alternate the bottom strip toward the chase view every 5 seconds
        (division leaders have no one to chase)"""
        return race['div_rank'] > 1 and int(tick / 5) % 2 == 1

    def _draw_race_frame(
        self, race: dict[str, Any], tick: float | None = None
    ) -> None:
        """Cubs logo, color-coded standings rows, and a playoff status strip"""
        self.manager.clear_canvas()
        background = Image.new(
            'RGB', (DisplayConfig.MATRIX_COLS, DisplayConfig.MATRIX_ROWS),
            Colors.CUBS_BLUE)
        self.manager.set_image(background, 0, 0)

        # Wrigley marquee-style header: white letters on a red band
        for y in range(0, 11):
            for x in range(DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, y, *MARQUEE_RED)
        title = 'PLAYOFF RACE'
        title_x = max(0, (DisplayConfig.MATRIX_COLS - len(title) * 6) // 2)
        self.manager.draw_text('small_bold', title_x, 9, Colors.WHITE, title)

        # Cubs logo anchors the left side, record underneath
        cubs_logo = self._load_logo('cubs', 22)
        if cubs_logo:
            self._paste_logo(cubs_logo, 3, 13)
        rows = self._format_race_rows(race)
        record = rows[2][1]
        record_x = 14 - len(record) * 2  # centered under the logo
        self.manager.draw_text('micro', record_x, 45, Colors.WHITE, record)

        # Division and wild card rows, games-back colored by direction
        for (label, value, gb), y in zip(rows[:2], (21, 32)):
            self.manager.draw_text('micro', 28, y, Colors.WHITE, label)
            self.manager.draw_text('tiny_bold', 61, y, Colors.YELLOW, value)
            if gb:
                color = GB_GREEN if gb.startswith('+') else GB_RED
                self.manager.draw_text(
                    'micro', 96 - len(gb) * 4, y, color, gb)

        if tick is None:
            tick = time.time()
        chase_drawn = (self._chase_strip_visible(race, tick)
                       and self._draw_chase_strip(race))
        if not chase_drawn:
            self._draw_status_strip(race)
        self.manager.swap_canvas()

    def _draw_status_strip(self, race: dict[str, Any]) -> None:
        """Green 'in' / red 'out' banner across the bottom right"""
        in_position = self._in_playoff_position(race)
        strip_color = GB_GREEN if in_position else STRIP_RED
        text_color = Colors.BLACK if in_position else Colors.WHITE
        if race['div_rank'] == 1:
            text = 'DIV LEADER!'
        elif in_position:
            text = 'PLAYOFF SPOT!'
        else:
            text = 'OUT - GO CUBS'

        self._fill_strip(strip_color)
        text_x = 28 + max(0, (DisplayConfig.MATRIX_COLS - 28 - len(text) * 4) // 2)
        self.manager.draw_text('micro', text_x, 45, text_color, text)

    def _draw_chase_strip(self, race: dict[str, Any]) -> bool:
        """'X.X GB [leader logo]' chase view; False if the logo is missing"""
        abbr = self._leader_abbr(race.get('leader_id'))
        logo = self._load_logo(abbr, 10) if abbr else None
        if logo is None:
            return False

        self._fill_strip(STRIP_NAVY)
        text = f"{race['gb']} GB OF"
        content_width = len(text) * 4 + 3 + logo.width
        x = 28 + max(0, (DisplayConfig.MATRIX_COLS - 28 - content_width) // 2)
        self.manager.draw_text('micro', x, 45, Colors.WHITE, text)
        base = Image.new('RGB', logo.size, STRIP_NAVY)
        base.paste(logo, (0, 0), logo)
        self.manager.set_image(base, x + len(text) * 4 + 3, 38)
        return True

    def _fill_strip(self, color: tuple[int, int, int]) -> None:
        for y in range(38, 48):
            for x in range(28, DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, y, *color)

    def _paste_logo(self, logo: Image.Image, x: int, y: int) -> None:
        """Paste a transparent logo over the current frame background"""
        base = Image.new('RGB', logo.size, Colors.CUBS_BLUE)
        base.paste(logo, (0, 0), logo)
        self.manager.set_image(base, x, y)

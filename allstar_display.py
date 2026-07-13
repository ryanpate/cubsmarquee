"""All-Star break display - Derby promo, ASG countdown, live AL vs NL score"""

from __future__ import annotations

import time
import pendulum
import statsapi
from PIL import Image
from typing import TYPE_CHECKING, Any

from scoreboard_config import (
    Colors, DisplayConfig, Fonts, RGBColor, TeamConfig,
)
from bears_display import format_countdown, countdown_color, format_kickoff_time
from retry import retry_api_call

if TYPE_CHECKING:
    from scoreboard_manager import ScoreboardManager

# Updated by hand each July (no public API exists for the Derby). The Derby
# screen self-disables unless this date is exactly one day before the ASG
# date from the live schedule lookup, so a stale year never shows the wrong
# field (see _derby_active).
DERBY_INFO: dict[str, Any] = {
    'date': '2026-07-13',
    'start_hour': 19,               # 7 PM America/Chicago
    'venue': 'CITIZENS BANK PARK',
    'field': [
        'SCHWARBER PHI', 'HARPER PHI', 'CAMINERO TB', 'RICE NYY',
        'CONTRERAS BOS', 'WALKER STL', 'CAGLIANONE KC', 'MURAKAMI CWS',
    ],
}

AL_RED: RGBColor = (191, 13, 62)
NL_BLUE: RGBColor = (10, 35, 120)
GOLD: RGBColor = (255, 215, 0)
DARK_BG: RGBColor = (8, 10, 28)
PANEL_BG: RGBColor = (5, 15, 40)
DIM_GRAY: RGBColor = (120, 120, 120)


class AllStarDisplay:
    """All-Star break screens: Derby promo, ASG pregame countdown,
    live AL vs NL scoreboard, and final screen."""

    ASG_CACHE_SECONDS = 3600
    ASG_CACHE_SECONDS_GAMEDAY = 60
    FEED_CACHE_SECONDS_LIVE = 20
    FEED_CACHE_SECONDS_PREGAME = 1800

    def __init__(self, scoreboard_manager: ScoreboardManager) -> None:
        self.manager = scoreboard_manager
        self._asg_cache: dict[str, Any] | None = None
        self._asg_cached_at: float = 0.0
        self._feed_cache: dict[str, Any] | None = None
        self._feed_cached_at: float = 0.0

    # ------------------------------------------------------------ data

    def fetch_asg_info(self) -> dict[str, Any] | None:
        """This season's All-Star Game from the schedule API, cached.
        Cache drops to 60s within an hour of first pitch so the live
        takeover reacts quickly."""
        ttl = self.ASG_CACHE_SECONDS
        if self._asg_cache and self._asg_cache.get('date'):
            game_dt = self._asg_cache['date']
            now_local = pendulum.now('America/Chicago')
            if (game_dt.date() == now_local.date()
                    and now_local >= game_dt.subtract(hours=1)):
                ttl = self.ASG_CACHE_SECONDS_GAMEDAY
        if self._asg_cache is not None and time.time() - self._asg_cached_at < ttl:
            return self._asg_cache

        year = pendulum.now('America/Chicago').year
        try:
            data = retry_api_call(
                statsapi.get, 'schedule',
                {'sportId': 1, 'gameTypes': 'A',
                 'startDate': f'{year}-07-01', 'endDate': f'{year}-07-31'})
            self._asg_cache = self._parse_asg_schedule(data)
            self._asg_cached_at = time.time()
        except Exception as e:
            print(f"ASG schedule fetch failed: {e}")
        return self._asg_cache

    @staticmethod
    def _parse_asg_schedule(data: dict[str, Any]) -> dict[str, Any] | None:
        for day in data.get('dates', []):
            for game in day.get('games', []):
                return {
                    'game_pk': game['gamePk'],
                    'date': pendulum.parse(
                        game['gameDate']).in_timezone('America/Chicago'),
                    'venue': game.get('venue', {}).get('name', ''),
                    'status': game.get('status', {}).get('detailedState', ''),
                    'abstract': game.get('status', {}).get(
                        'abstractGameState', ''),
                }
        return None

    def is_allstar_window(self, now: pendulum.DateTime | None = None) -> bool:
        """True on Derby day (ASG - 1) and ASG day."""
        info = self.fetch_asg_info()
        if not info:
            return False
        today = (now or pendulum.now('America/Chicago')).date()
        asg_dt = info['date']
        return today in (asg_dt.date(), asg_dt.subtract(days=1).date())

    def asg_is_live(self) -> bool:
        info = self.fetch_asg_info()
        return bool(info) and info.get('abstract') == 'Live'

    def _derby_active(self, now: pendulum.DateTime | None = None) -> bool:
        """Derby promo window: DERBY_INFO date matches ASG - 1 (guards a
        stale constant) and it's that day before 11 PM."""
        info = self.fetch_asg_info()
        if not info:
            return False
        now = now or pendulum.now('America/Chicago')
        derby_date = pendulum.parse(
            DERBY_INFO['date'], tz='America/Chicago').date()
        if derby_date != info['date'].subtract(days=1).date():
            return False
        return now.date() == derby_date and now.hour < 23

    def _fetch_feed(self, game_pk: int, ttl: float) -> dict[str, Any] | None:
        if (self._feed_cache is not None
                and time.time() - self._feed_cached_at < ttl):
            return self._feed_cache
        try:
            self._feed_cache = retry_api_call(
                statsapi.get, 'game', {'gamePk': game_pk})
            self._feed_cached_at = time.time()
        except Exception as e:
            print(f"ASG feed fetch failed: {e}")
        return self._feed_cache

    @staticmethod
    def _cubs_allstars_from_boxscore(feed: dict[str, Any]) -> list[str]:
        names = []
        teams = feed.get('liveData', {}).get('boxscore', {}).get('teams', {})
        for side in ('away', 'home'):
            for player in teams.get(side, {}).get('players', {}).values():
                if player.get('parentTeamId') == TeamConfig.CUBS_TEAM_ID:
                    name = player.get('person', {}).get('fullName', '')
                    if name:
                        names.append(name)
        return names

    @staticmethod
    def _extract_live_state(feed: dict[str, Any]) -> dict[str, Any]:
        live = feed.get('liveData', {})
        linescore = live.get('linescore', {})
        offense = linescore.get('offense', {})
        batter = (live.get('plays', {}).get('currentPlay', {})
                  .get('matchup', {}).get('batter', {}))
        parent_team = None
        if batter.get('id'):
            for side in ('away', 'home'):
                player = (live.get('boxscore', {}).get('teams', {})
                          .get(side, {}).get('players', {})
                          .get(f"ID{batter['id']}"))
                if player:
                    parent_team = player.get('parentTeamId')
                    break
        return {
            'away_runs': linescore.get('teams', {}).get('away', {}).get('runs', 0),
            'home_runs': linescore.get('teams', {}).get('home', {}).get('runs', 0),
            'inning': linescore.get('currentInning', 1),
            'inning_state': linescore.get('inningState', ''),
            'outs': linescore.get('outs', 0),
            'bases': {base: base in offense
                      for base in ('first', 'second', 'third')},
            'batter_name': batter.get('fullName', ''),
            'batter_is_cub': parent_team == TeamConfig.CUBS_TEAM_ID,
            'is_final': feed.get('gameData', {}).get('status', {}).get(
                'abstractGameState') == 'Final',
        }

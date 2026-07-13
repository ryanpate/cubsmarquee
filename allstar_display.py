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

    # --------------------------------------------------------- promo

    @staticmethod
    def _center_x(text: str, char_width: int) -> int:
        return max(0, (DisplayConfig.MATRIX_COLS - len(text) * char_width) // 2)

    def display_promo(self, duration: int) -> None:
        """Rotation segment: Derby promo on Derby evening, ASG pregame
        countdown otherwise. No-op outside the All-Star window or once
        the game has started (the live takeover handles that)."""
        info = self.fetch_asg_info()
        if not info or not self.is_allstar_window():
            return
        if self._derby_active():
            self._display_derby_promo(duration)
        elif info.get('abstract') == 'Preview':
            self._display_asg_pregame(duration, info)

    def _display_derby_promo(self, duration: int) -> None:
        tz = 'America/Chicago'
        derby_start = pendulum.parse(DERBY_INFO['date'], tz=tz).add(
            hours=DERBY_INFO['start_hour'])
        field_text = '  *  '.join(DERBY_INFO['field'])
        field_width = len(field_text) * Fonts.CHAR_WIDTH_MICRO
        scroll_x = float(DisplayConfig.MATRIX_COLS)
        start = time.time()

        while time.time() - start < duration:
            self.manager.clear_canvas()
            self.manager.fill_canvas(*DARK_BG)
            for x in range(DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, 0, *GOLD)

            title = 'HOME RUN DERBY'
            self.manager.draw_text(
                'tiny_bold', self._center_x(title, Fonts.CHAR_WIDTH_TINY),
                10, GOLD, title)

            seconds = (derby_start - pendulum.now(tz)).total_seconds()
            if seconds > 0:
                line = f'TONIGHT {format_countdown(seconds)}'
                color = countdown_color(seconds, yellow_under=3 * 3600,
                                        orange_under=30 * 60)
            else:
                line, color = 'UNDERWAY', GOLD
            self.manager.draw_text(
                'micro', self._center_x(line, Fonts.CHAR_WIDTH_MICRO),
                20, color, line)

            venue = DERBY_INFO['venue']
            self.manager.draw_text(
                'micro', self._center_x(venue, Fonts.CHAR_WIDTH_MICRO),
                28, (150, 150, 150), venue)

            self.manager.draw_text(
                'micro', int(scroll_x), 40, Colors.WHITE, field_text)
            scroll_x -= 1
            if scroll_x < -field_width:
                scroll_x = float(DisplayConfig.MATRIX_COLS)

            self.manager.swap_canvas()
            time.sleep(0.05)

    def _get_cubs_allstars(self, game_pk: int) -> list[str]:
        feed = self._fetch_feed(game_pk, self.FEED_CACHE_SECONDS_PREGAME)
        if not feed:
            return []
        return self._cubs_allstars_from_boxscore(feed)

    def _display_asg_pregame(self, duration: int, info: dict) -> None:
        tz = 'America/Chicago'
        cubs_stars = self._get_cubs_allstars(info['game_pk'])
        stars_text = ('CUBS ALL-STARS: ' + ', '.join(cubs_stars).upper()
                      if cubs_stars else '')
        stars_width = len(stars_text) * Fonts.CHAR_WIDTH_MICRO
        scroll_x = float(DisplayConfig.MATRIX_COLS)
        game_dt = info['date']
        date_line = (f"{game_dt.format('ddd').upper()} "
                     f"{format_kickoff_time(game_dt)}")
        start = time.time()

        while time.time() - start < duration:
            self.manager.clear_canvas()
            self.manager.fill_canvas(*DARK_BG)
            for x in range(DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, 0, *GOLD)

            title = 'ALL-STAR GAME'
            self.manager.draw_text(
                'tiny_bold', self._center_x(title, Fonts.CHAR_WIDTH_TINY),
                10, GOLD, title)

            self.manager.draw_text('tiny_bold', 30, 19, AL_RED, 'AL')
            self.manager.draw_text('tiny_bold', 43, 19, Colors.WHITE, 'VS')
            self.manager.draw_text('tiny_bold', 56, 19, NL_BLUE, 'NL')

            seconds = (game_dt - pendulum.now(tz)).total_seconds()
            if seconds > 0:
                line = f'FIRST PITCH {format_countdown(seconds)}'
                color = countdown_color(seconds, yellow_under=3 * 3600,
                                        orange_under=30 * 60)
            else:
                line, color = 'STARTING SOON', GOLD
            self.manager.draw_text(
                'micro', self._center_x(line, Fonts.CHAR_WIDTH_MICRO),
                27, color, line)

            self.manager.draw_text(
                'micro', self._center_x(date_line, Fonts.CHAR_WIDTH_MICRO),
                35, (150, 150, 150), date_line)

            if stars_text:
                self.manager.draw_text(
                    'micro', int(scroll_x), 45, Colors.YELLOW, stars_text)
                scroll_x -= 1
                if scroll_x < -stars_width:
                    scroll_x = float(DisplayConfig.MATRIX_COLS)

            self.manager.swap_canvas()
            time.sleep(0.05)

    # ---------------------------------------------------------- live

    def display_live_game(self, display_time: int) -> bool:
        """Run the live AL vs NL screen for display_time seconds.
        Returns True as soon as the feed reports the game is over."""
        info = self.fetch_asg_info()
        if not info:
            return False
        start = time.time()
        while time.time() - start < display_time:
            feed = self._fetch_feed(info['game_pk'],
                                    self.FEED_CACHE_SECONDS_LIVE)
            if not feed:
                return False
            state = self._extract_live_state(feed)
            if state['is_final']:
                return True
            self._render_live_frame(state)
            time.sleep(0.5)
        return False

    def _draw_league_tiles(self) -> Image.Image:
        """Base image mirroring the live-game layout: league tiles in the
        16px logo column, white score boxes, dark info panel."""
        base = Image.new('RGB', (96, 48))
        px = base.load()
        for y in range(0, 15):
            for x in range(0, 16):
                px[x, y] = AL_RED
        for y in range(16, 31):
            for x in range(0, 16):
                px[x, y] = NL_BLUE
        for x in range(17, 32):
            for y in range(0, 31):
                px[x, y] = (255, 255, 255) if y != 15 else (0, 0, 0)
        for x in range(32, 96):
            for y in range(0, 31):
                px[x, y] = PANEL_BG
        return base

    def _draw_star(self, x: int, y: int) -> None:
        for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
            self.manager.draw_pixel(x + dx, y + dy, *GOLD)

    def _draw_bases(self, cx: int, cy: int, bases: dict[str, bool]) -> None:
        spots = {'second': (cx, cy - 4), 'first': (cx + 4, cy),
                 'third': (cx - 4, cy)}
        for name, (bx, by) in spots.items():
            color = Colors.YELLOW if bases[name] else (70, 70, 90)
            for dx in range(2):
                for dy in range(2):
                    self.manager.draw_pixel(bx + dx, by + dy, *color)

    def _render_live_frame(self, state: dict) -> None:
        m = self.manager
        m.clear_canvas()
        m.set_image(self._draw_league_tiles(), 0, 0)

        m.draw_text('tiny_bold', 3, 11, Colors.WHITE, 'AL')
        m.draw_text('tiny_bold', 3, 27, Colors.WHITE, 'NL')
        self._draw_star(13, 3)
        self._draw_star(13, 19)

        for runs, y in ((state['away_runs'], 11), (state['home_runs'], 27)):
            text = str(runs)
            x = 17 + max(0, (15 - len(text) * Fonts.CHAR_WIDTH_STANDARD) // 2)
            m.draw_text('standard_bold', x, y, (0, 0, 0), text)

        title = 'ALL-STAR GAME'
        title_x = 32 + max(0, (64 - len(title) * Fonts.CHAR_WIDTH_MICRO) // 2)
        m.draw_text('micro', title_x, 7, GOLD, title)

        inning_line = f"{state['inning_state'][:3].upper()} {state['inning']}"
        m.draw_text('tiny', 38, 18, Colors.WHITE, inning_line)
        for i in range(3):
            color = (255, 60, 60) if i < state['outs'] else (70, 70, 90)
            for dx in range(2):
                for dy in range(2):
                    m.draw_pixel(40 + i * 6 + dx, 23 + dy, *color)
        self._draw_bases(80, 20, state['bases'])

        name = state['batter_name'].upper()
        if name:
            if state['batter_is_cub'] and int(time.time()) % 4 < 2:
                for y in range(33, 48):
                    for x in range(0, 96):
                        m.draw_pixel(x, y, *Colors.YELLOW)
                banner = 'CUBS STAR AT BAT'
                m.draw_text(
                    'micro', self._center_x(banner, Fonts.CHAR_WIDTH_MICRO),
                    39, Colors.CUBS_BLUE, banner)
                m.draw_text(
                    'micro', self._center_x(name, Fonts.CHAR_WIDTH_MICRO),
                    46, Colors.CUBS_BLUE, name)
            else:
                m.draw_text('micro', 2, 39, (150, 150, 150), 'AT BAT')
                if len(name) * Fonts.CHAR_WIDTH_TINY > 94:
                    name = name.split()[-1]
                m.draw_text('tiny', 2, 46, Colors.WHITE, name)

        m.swap_canvas()

    def display_final(self, duration: int) -> None:
        info = self.fetch_asg_info()
        if not info:
            return
        feed = self._fetch_feed(info['game_pk'], self.FEED_CACHE_SECONDS_LIVE)
        if not feed:
            return
        state = self._extract_live_state(feed)
        away, home = state['away_runs'], state['home_runs']
        al_color = Colors.WHITE if away > home else DIM_GRAY
        nl_color = Colors.WHITE if home > away else DIM_GRAY

        start = time.time()
        while time.time() - start < duration:
            self.manager.clear_canvas()
            self.manager.fill_canvas(*DARK_BG)
            for x in range(DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, 0, *GOLD)

            title = 'ALL-STAR GAME'
            self.manager.draw_text(
                'tiny_bold', self._center_x(title, Fonts.CHAR_WIDTH_TINY),
                10, GOLD, title)
            self.manager.draw_text(
                'tiny_bold', self._center_x('FINAL', Fonts.CHAR_WIDTH_TINY),
                21, Colors.WHITE, 'FINAL')
            self.manager.draw_text('tiny_bold', 18, 34, al_color,
                                   f'AL {away}')
            self.manager.draw_text('tiny_bold', 54, 34, nl_color,
                                   f'NL {home}')

            self.manager.swap_canvas()
            time.sleep(0.1)

        # Force the next asg_is_live() to re-check the schedule so the
        # takeover loop exits promptly after the final screen.
        self._asg_cached_at = 0.0

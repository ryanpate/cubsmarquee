"""All-Star break display - Derby promo, ASG countdown, live AL vs NL score"""

from __future__ import annotations

import math
import time
import pendulum
import requests
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

# Deterministic (no random) so the fake clock in tests reproduces frames.
# Stars live in the promo scene's sky band (rows 13-39).
_STARS: list[tuple[int, int, int]] = [
    ((i * 37 + 11) % DisplayConfig.MATRIX_COLS,
     13 + (i * 19 + 3) % 27, i)
    for i in range(18)
]
FIREWORK_COLORS: list[RGBColor] = [
    (255, 120, 40), (80, 160, 255), (255, 215, 0),
]


class AllStarDisplay:
    """All-Star break screens: Derby promo, ASG pregame countdown,
    live AL vs NL scoreboard, and final screen."""

    ASG_CACHE_SECONDS = 3600
    ASG_CACHE_SECONDS_GAMEDAY = 60
    FEED_CACHE_SECONDS_LIVE = 20
    FEED_CACHE_SECONDS_PREGAME = 1800
    DERBY_POLL_SECONDS = 15
    DERBY_DISCOVERY_RETRY_SECONDS = 120
    DERBY_LIVE_SEGMENT_SECONDS = 300
    BALL_PERIOD_SECONDS = 4.0
    BALL_FLIGHT_SECONDS = 1.5
    BURST_SECONDS = 1.0

    def __init__(self, scoreboard_manager: ScoreboardManager) -> None:
        self.manager = scoreboard_manager
        self._asg_cache: dict[str, Any] | None = None
        self._asg_cached_at: float = 0.0
        self._feed_cache: dict[str, Any] | None = None
        self._feed_cached_at: float = 0.0
        self._derby_pk: int | None = None
        self._derby_pk_checked_at: float = 0.0
        self._derby_cache: dict[str, Any] | None = None
        self._derby_cached_at: float = 0.0
        self._derby_prev_hrs: dict[str, int] = {}
        self._derby_burst: tuple[float, int] | None = None

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

    # --------------------------------------------------------- derby data

    def _derby_event_candidates(self) -> list[int]:
        """Possible Derby gamePks. MLB has no stable discovery path: try
        gameTypes=D games first (the documented shape), then July events
        named 'Home Run Derby' from the events schedule (their ids serve as
        homeRunDerby gamePks - verified against the 2017 derby, id 511101)."""
        year = pendulum.now('America/Chicago').year
        ids: list[int] = []
        try:
            data = statsapi.get(
                'schedule',
                {'sportId': 1, 'gameTypes': 'D',
                 'startDate': f'{year}-07-01', 'endDate': f'{year}-07-31'})
            for day in data.get('dates', []):
                for game in day.get('games', []):
                    ids.append(game['gamePk'])
        except Exception as e:
            print(f"Derby gameTypes=D lookup failed: {e}")
        try:
            # The statsapi wrapper doesn't allow scheduleTypes, so hit the
            # schedule endpoint directly for non-game events
            resp = requests.get(
                'https://statsapi.mlb.com/api/v1/schedule',
                params={'sportId': 1, 'scheduleTypes': 'events',
                        'startDate': f'{year}-07-01',
                        'endDate': f'{year}-07-31'},
                timeout=10)
            resp.raise_for_status()
            events = []
            for day in resp.json().get('dates', []):
                for event in day.get('events', []):
                    name = event.get('name', '').lower()
                    if ('home run derby' in name
                            and 'batting practice' not in name
                            and 'test' not in name):
                        events.append(event['id'])
            ids.extend(events)
        except Exception as e:
            print(f"Derby event lookup failed: {e}")
        return list(dict.fromkeys(ids))

    def fetch_derby_data(self) -> dict[str, Any] | None:
        """Live Derby bracket, or None while MLB hasn't published it yet
        (the endpoint 404s until around event time)."""
        now = time.time()
        if (self._derby_cache is not None
                and now - self._derby_cached_at < self.DERBY_POLL_SECONDS):
            return self._derby_cache

        if self._derby_pk is not None:
            candidates = [self._derby_pk]
        else:
            # Discovery is 2+ requests; don't hammer it while unpublished
            if now - self._derby_pk_checked_at < self.DERBY_DISCOVERY_RETRY_SECONDS:
                return self._derby_cache
            self._derby_pk_checked_at = now
            candidates = self._derby_event_candidates()

        for pk in candidates:
            try:
                data = statsapi.get('homeRunDerby', {'gamePk': str(pk)})
            except Exception:
                continue
            if data.get('rounds') and self._derby_payload_is_real(data):
                self._derby_pk = pk
                self._derby_cache = data
                self._derby_cached_at = now
                return data
        return self._derby_cache

    def _derby_payload_is_real(self, data: dict[str, Any]) -> bool:
        """Reject MLB's rehearsal derbies: the API serves 'Home Run Derby
        Test #N' events (seen July 2026) full of junk data. Real payloads
        aren't named test and fall on Derby day (ASG - 1)."""
        info = data.get('info', {})
        if 'test' in info.get('name', '').lower():
            return False
        asg = self.fetch_asg_info()
        if asg and info.get('eventDate'):
            try:
                event_day = pendulum.parse(info['eventDate']).in_timezone(
                    'America/Chicago').date()
                return event_day == asg['date'].subtract(days=1).date()
            except Exception:
                return True
        return True

    @staticmethod
    def _last_name(full_name: str) -> str:
        return full_name.split()[-1].upper() if full_name else ''

    @staticmethod
    def _parse_derby(data: dict[str, Any]) -> dict[str, Any]:
        """Flatten the bracket into what the screen needs: the active
        matchup, who's swinging, completed results, and the champion."""
        status = data.get('status', {})
        rounds = data.get('rounds', [])
        total_rounds = len(rounds)
        state: dict[str, Any] = {
            'state': status.get('state', ''),
            'round': status.get('currentRound') or 1,
            'total_rounds': total_rounds,
            'clock': status.get('currentRoundTimeLeft', ''),
            'matchup': None,
            'batter': None,
            'results': [],
            'champion': None,
        }
        for rnd in rounds:
            for mu in rnd.get('matchups', []):
                seeds = []
                for key in ('topSeed', 'bottomSeed'):
                    seed = mu.get(key, {})
                    seeds.append({
                        'name': AllStarDisplay._last_name(
                            seed.get('player', {}).get('fullName', '')),
                        'hrs': seed.get('numHomeRuns', 0),
                        'started': seed.get('isStarted', False),
                        'complete': seed.get('isComplete', False),
                        'winner': seed.get('isWinner', False),
                    })
                a, b = seeds
                if a['complete'] and b['complete']:
                    winner, loser = (a, b) if (
                        a['winner'] or a['hrs'] >= b['hrs']) else (b, a)
                    state['results'].append(
                        f"{winner['name']} {winner['hrs']} "
                        f"DEF {loser['name']} {loser['hrs']}")
                    if rnd.get('round') == total_rounds:
                        state['champion'] = winner
                elif state['matchup'] is None:
                    state['matchup'] = (a, b)
                    for seed in (a, b):
                        if seed['started'] and not seed['complete']:
                            state['batter'] = seed['name']
        return state

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
            if self.fetch_derby_data():
                # Live bracket published: track it, with a longer slot
                # than a plain promo segment
                self._display_derby_live(
                    max(duration, self.DERBY_LIVE_SEGMENT_SECONDS))
            else:
                self._display_derby_promo(duration)
        elif info.get('abstract') == 'Preview':
            self._display_asg_pregame(duration, info)

    # ----------------------------------------------------------- flair

    def _draw_star_field(self, tick: float) -> None:
        """Twinkling stars behind the promo text, each fading on its
        own phase; every fourth star is gold"""
        for x, y, i in _STARS:
            phase = tick * (1.0 + (i % 5) * 0.35) + i * 0.7
            level = 0.5 + 0.5 * math.sin(phase)
            v = int(50 + 170 * level)
            if i % 4 == 0:
                self.manager.draw_pixel(x, y, v, int(v * 0.85), 0)
            else:
                self.manager.draw_pixel(x, y, v, v, v)

    def _draw_hr_ball(self, tick: float) -> None:
        """A home-run ball launching from the lower left and arcing
        across the sky with a short fading trail"""
        t = tick % self.BALL_PERIOD_SECONDS
        if t >= self.BALL_FLIGHT_SECONDS:
            return
        for lag, color, size in (
                (0.10, (55, 55, 55), 1), (0.05, (110, 110, 110), 1),
                (0.0, (255, 255, 255), 2)):
            p = (t - lag) / self.BALL_FLIGHT_SECONDS
            if p < 0:
                continue
            x = int(p * (DisplayConfig.MATRIX_COLS + 6)) - 3
            y = int(39 - 80 * p + 56 * p * p)
            for dx in range(size):
                for dy in range(size):
                    px, py = x + dx, y + dy
                    if (0 <= px < DisplayConfig.MATRIX_COLS
                            and 11 < py < 41):     # stay in the sky band
                        self.manager.draw_pixel(px, py, *color)

    def _draw_hr_burst(self, cx: int, cy: int, age: float) -> None:
        """Gold radial burst around a hitter's HR count when it rises"""
        radius = 1 + age * 8
        fade = max(0.0, 1.0 - age / self.BURST_SECONDS)
        color = tuple(int(c * fade) for c in GOLD)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1),
                       (1, 1), (1, -1), (-1, 1), (-1, -1)):
            scale = 0.7 if dx and dy else 1.0
            px = cx + int(round(dx * radius * scale))
            py = cy + int(round(dy * radius * scale))
            if (0 <= px < DisplayConfig.MATRIX_COLS
                    and 0 < py < DisplayConfig.MATRIX_ROWS):
                self.manager.draw_pixel(px, py, *color)

    def _draw_fireworks(self, tick: float) -> None:
        """Staggered firework bursts behind the CHAMPION screen"""
        for j, (cx, cy, stagger) in enumerate(
                ((20, 14, 0.0), (74, 12, 0.8), (48, 38, 1.6))):
            age = (tick + stagger) % 2.4
            if age >= 1.2:
                continue
            radius = age * 9
            fade = 1.0 - age / 1.2
            color = tuple(int(c * fade) for c in FIREWORK_COLORS[j])
            for k in range(12):
                ang = k * math.pi / 6
                px = cx + int(round(radius * math.cos(ang)))
                py = cy + int(round(radius * math.sin(ang)))
                if (0 <= px < DisplayConfig.MATRIX_COLS
                        and 0 < py < DisplayConfig.MATRIX_ROWS):
                    self.manager.draw_pixel(px, py, *color)

    def _derby_scene_background(self, baseballs: bool = True) -> Image.Image:
        """Derby scene: gold banner with AL/NL stripes, night sky, and
        outfield grass with mow stripes; the promo adds a baseball on
        each side (the tracker needs that room for matchup rows)"""
        img = Image.new('RGB', (DisplayConfig.MATRIX_COLS,
                                DisplayConfig.MATRIX_ROWS), DARK_BG)
        px = img.load()
        for x in range(DisplayConfig.MATRIX_COLS):
            for y in range(10):
                px[x, y] = GOLD
            px[x, 10] = AL_RED
            px[x, 11] = NL_BLUE
            px[x, 41] = (6, 40, 18)
            grass = (10, 70, 30) if (x // 8) % 2 == 0 else (8, 56, 24)
            for y in range(42, DisplayConfig.MATRIX_ROWS):
                px[x, y] = grass
        for cx in ((11, 84) if baseballs else ()):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    if dx * dx + dy * dy <= 16:
                        px[cx + dx, 33 + dy] = (235, 235, 230)
            for dy in range(-3, 4):
                off = 2 if abs(dy) <= 1 else 1
                px[cx - off, 33 + dy] = AL_RED
                px[cx + off, 33 + dy] = AL_RED
        return img

    def _display_derby_promo(self, duration: int) -> None:
        tz = 'America/Chicago'
        derby_start = pendulum.parse(DERBY_INFO['date'], tz=tz).add(
            hours=DERBY_INFO['start_hour'])
        field_text = '  *  '.join(DERBY_INFO['field'])
        field_width = len(field_text) * Fonts.CHAR_WIDTH_MICRO
        scroll_x = float(DisplayConfig.MATRIX_COLS)
        background = self._derby_scene_background()
        start = time.time()

        while time.time() - start < duration:
            self.manager.clear_canvas()
            self.manager.set_image(background, 0, 0)

            tick = time.time() - start
            self._draw_star_field(tick)

            title = 'HOME RUN DERBY'
            self.manager.draw_text(
                'tiny_bold', self._center_x(title, Fonts.CHAR_WIDTH_TINY),
                8, DARK_BG, title)

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
                'micro', int(scroll_x), 46, Colors.WHITE, field_text)
            scroll_x -= 1
            if scroll_x < -field_width:
                scroll_x = float(DisplayConfig.MATRIX_COLS)

            self._draw_hr_ball(tick)

            self.manager.swap_canvas()
            time.sleep(0.05)

    def _display_derby_live(self, duration: int) -> None:
        """Live Derby tracker: current matchup with HR counts and the
        round clock, active hitter highlighted, completed results
        scrolling along the bottom, champion screen at the end."""
        scroll_x = float(DisplayConfig.MATRIX_COLS)
        background = self._derby_scene_background(baseballs=False)
        start = time.time()

        while time.time() - start < duration:
            data = self.fetch_derby_data()
            if not data:
                return
            state = self._parse_derby(data)
            m = self.manager

            # Fire a gold burst by a hitter's HR count when it rises
            if state['matchup']:
                for hitter, row_y in zip(state['matchup'], (22, 32)):
                    prev = self._derby_prev_hrs.get(hitter['name'])
                    if prev is not None and hitter['hrs'] > prev:
                        self._derby_burst = (time.time(), row_y - 2)
                    self._derby_prev_hrs[hitter['name']] = hitter['hrs']

            m.clear_canvas()
            m.set_image(background, 0, 0)

            m.draw_text('tiny_bold', 2, 8, DARK_BG, 'HR DERBY')
            if state['champion'] or (state['total_rounds']
                                     and state['round'] >= state['total_rounds']):
                tag = 'FINAL'
            else:
                tag = f"RD {state['round']}"
            m.draw_text('micro',
                        DisplayConfig.MATRIX_COLS - len(tag)
                        * Fonts.CHAR_WIDTH_MICRO - 2,
                        8, DARK_BG, tag)

            if state['champion'] and state['state'] == 'Final':
                self._draw_fireworks(time.time() - start)
                champ = state['champion']
                m.draw_text(
                    'tiny_bold',
                    self._center_x('CHAMPION', Fonts.CHAR_WIDTH_TINY),
                    21, GOLD, 'CHAMPION')
                m.draw_text(
                    'tiny_bold',
                    self._center_x(champ['name'], Fonts.CHAR_WIDTH_TINY),
                    31, Colors.WHITE, champ['name'])
                hr_line = f"{champ['hrs']} HR"
                m.draw_text(
                    'micro', self._center_x(hr_line, Fonts.CHAR_WIDTH_MICRO),
                    39, (150, 150, 150), hr_line)
            elif state['matchup']:
                a, b = state['matchup']
                for hitter, y in ((a, 22), (b, 32)):
                    active = (state['batter'] == hitter['name']
                              and hitter['name'])
                    name_color = Colors.YELLOW if active else Colors.WHITE
                    if active and int(time.time()) % 2 == 0:
                        m.draw_text('micro', 1, y, Colors.YELLOW, '>')
                    m.draw_text('tiny', 6, y, name_color,
                                hitter['name'][:13])
                    hrs = str(hitter['hrs'])
                    m.draw_text(
                        'small_bold',
                        DisplayConfig.MATRIX_COLS - len(hrs)
                        * Fonts.CHAR_WIDTH_SMALL - 2,
                        y, GOLD if active else Colors.WHITE, hrs)
                if state['clock']:
                    m.draw_text(
                        'micro',
                        self._center_x(state['clock'],
                                       Fonts.CHAR_WIDTH_MICRO),
                        40, (150, 150, 150), state['clock'])
                if self._derby_burst:
                    burst_age = time.time() - self._derby_burst[0]
                    if burst_age < self.BURST_SECONDS:
                        self._draw_hr_burst(
                            DisplayConfig.MATRIX_COLS - 8,
                            self._derby_burst[1], burst_age)
                    else:
                        self._derby_burst = None

            if state['results']:
                ticker = '  *  '.join(state['results'])
                ticker_width = len(ticker) * Fonts.CHAR_WIDTH_MICRO
                m.draw_text('micro', int(scroll_x), 47,
                            Colors.WHITE, ticker)
                scroll_x -= 1
                if scroll_x < -ticker_width:
                    scroll_x = float(DisplayConfig.MATRIX_COLS)

            m.swap_canvas()
            time.sleep(0.1)

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

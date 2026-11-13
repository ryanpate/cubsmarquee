"""College basketball screens, themed by the active NCAAB team pack.

Five screens, all from ESPN's public endpoints:
  - game: next-game card, game-day countdown, live score, final box score
  - rankings: the team's poll card, then the AP Top 25 a page at a time
  - standings: conference table a page at a time
  - news: scrolling team headlines
  - facts: scrolling program facts from the pack's JSON file
"""

from __future__ import annotations

import json
import random
import time
from typing import TYPE_CHECKING, Any

import pendulum
from PIL import Image

from bears_display import (
    TAKEOVER_MAX_SECONDS, _centred_x, _score_pair, countdown_color,
    extract_broadcast, format_countdown, format_kickoff_time,
    is_shutdown_requested)
from retry import retry_http_request
from rss_fetch import fetch_feed, is_probably_english
from scoreboard_config import (
    Colors, Fonts, GameConfig, RGBColor, get_scroll_delay, load_user_config)
from teams import data_path_candidates, get_active_ncaab_team

if TYPE_CHECKING:
    from scoreboard_manager import ScoreboardManager

ESPN_SITE = ('https://site.api.espn.com/apis/site/v2/sports/basketball/'
             'mens-college-basketball')
ESPN_STANDINGS = ('https://site.api.espn.com/apis/v2/sports/basketball/'
                  'mens-college-basketball/standings')
# League-wide feed, keyword-filtered; only used when the team feed is empty
FALLBACK_NEWS_RSS = 'https://www.espn.com/espn/rss/ncb/news'

# ESPN's rank for a team outside the poll
UNRANKED = 99

# Scores move far faster than football's, so the live poll is tighter than
# GameConfig.LIVE_SCORE_UPDATE_INTERVAL
LIVE_UPDATE_SECONDS = 20
PREGAME_UPDATE_SECONDS = 60

# A late West Coast tip ends after midnight Central. Without this the game
# stops being "today's" at 12:00 and the live screen drops mid-game.
RECENT_START_HOURS = 4

FRAME_SECONDS = 0.5
# How long a live takeover lingers on the final score before releasing
FINAL_HOLD_SECONDS = 60
PAGE_SECONDS = 5
ROWS_PER_PAGE = 5


# --- Parsing (pure functions, no display) ---------------------------------

def basketball_month_gate() -> bool:
    """Fallback season window when the schedule cannot be reached:
    November through April, which covers the NCAA tournament. Returning
    False there would hide every screen on a network blip."""
    month = pendulum.now().month
    return month >= 11 or month <= 4


def competitor_rank(competitor: dict) -> int | None:
    """Poll rank for a competitor, or None when unranked"""
    rank = (competitor.get('curatedRank') or {}).get('current')
    if not rank or rank >= UNRANKED:
        return None
    return int(rank)


def competitor_score(competitor: dict) -> str:
    """Score as a display string. The schedule endpoint sends a
    {value, displayValue} dict, the scoreboard a bare string."""
    score = competitor.get('score')
    if isinstance(score, dict):
        return str(score.get('displayValue', '0'))
    if score is None or score == '':
        return '0'
    try:
        return str(int(float(score)))
    except (ValueError, TypeError):
        return '0'


def split_competitors(competition: dict, team_id: str) -> tuple[dict, dict]:
    """(team, opponent) from a competition, matched on ESPN team id.

    Ids, not abbreviations: ~365 schools share a small abbreviation space.
    """
    competitors = competition['competitors']
    for index, competitor in enumerate(competitors[:2]):
        ids = (str(competitor.get('id')),
               str((competitor.get('team') or {}).get('id')))
        if str(team_id) in ids:
            return competitor, competitors[1 - index]
    raise ValueError(f'team {team_id} is not in this game')


def site_label(competition: dict, team: dict) -> str:
    """'VS' at home or on a neutral floor, 'AT' on the road"""
    if competition.get('neutralSite'):
        return 'VS'
    return 'VS' if team.get('homeAway') == 'home' else 'AT'


def extract_half_scores(competitor: dict) -> list[str]:
    """Per-half points; every overtime sums into one trailing column so
    the box score stays three columns wide however long the game runs."""
    values = []
    for period in competitor.get('linescores') or []:
        display = period.get('displayValue')
        if display is None:
            display = int(float(period.get('value', 0)))
        values.append(str(display))
    if len(values) > 2:
        values = values[:2] + [str(sum(int(v) for v in values[2:]))]
    return values


def extract_stats(competitor: dict) -> dict[str, str]:
    """Team stat name -> display value from a scoreboard competitor"""
    return {stat.get('name'): stat.get('displayValue')
            for stat in competitor.get('statistics') or []
            if stat.get('name') and stat.get('displayValue') is not None}


def lead_text(team_abbr: str, team_score, opp_abbr: str, opp_score) -> str:
    """'ILL BY 7', 'DUKE BY 3' or 'TIED'; '' when a score will not parse"""
    team_int, opp_int = _score_pair(team_score, opp_score)
    if team_int is None:
        return ''
    if team_int == opp_int:
        return 'TIED'
    leader = team_abbr if team_int > opp_int else opp_abbr
    return f'{leader} BY {abs(team_int - opp_int)}'


def short_note(competition: dict) -> str:
    """Event label for tournament games, squeezed for one micro line:
    'NCAA Men's Basketball Championship - South Region - Sweet 16'
    becomes 'NCAA SWEET 16'. '' for an ordinary game."""
    notes = competition.get('notes') or []
    headline = (notes[0].get('headline') or '') if notes else ''
    if not headline:
        return ''
    parts = [part.strip() for part in headline.split(' - ')]
    if parts[0].upper().startswith('NCAA'):
        text = f'NCAA {parts[-1]}' if len(parts) > 1 else 'NCAA TOURNAMENT'
    elif len(parts) > 1:
        text = f"{parts[0].replace('Tournament', 'Tourn')} {parts[-1]}"
    else:
        text = parts[0]
    return text.upper()[:24]


def fit_name(candidates: list[str | None], max_chars: int) -> str:
    """First candidate that fits, else the last one truncated"""
    names = [name for name in candidates if name]
    for name in names:
        if len(name) <= max_chars:
            return name.upper()
    return names[-1].upper()[:max_chars] if names else ''


def parse_trend(trend) -> int:
    """ESPN's '+3' / '-2' / '-' poll movement as a signed int"""
    try:
        return int(str(trend).replace('+', ''))
    except (ValueError, TypeError):
        return 0


def parse_rankings(payload: dict, team_id: str) -> dict[str, Any]:
    """Reduce the rankings payload to what the two ranking screens draw.

    Returns {'poll_name', 'rows': [...], 'team': {...}}; rows are the
    first poll's Top 25. team['ap'] / team['coaches'] are None when the
    team is outside that poll, and team['votes'] is its points when it is
    only receiving votes.
    """
    polls = payload.get('rankings') or []
    result: dict[str, Any] = {
        'poll_name': 'AP TOP 25', 'rows': [],
        'team': {'ap': None, 'coaches': None, 'trend': 0, 'votes': None},
    }

    def find(poll_type: str) -> dict | None:
        for poll in polls:
            if poll.get('type') == poll_type:
                return poll
        return None

    ap = find('ap') or (polls[0] if polls else None)
    if ap is None:
        return result
    result['poll_name'] = (ap.get('name') or 'AP Top 25').upper()

    for entry in ap.get('ranks') or []:
        team = entry.get('team') or {}
        is_team = str(team.get('id')) == str(team_id)
        result['rows'].append({
            'rank': entry.get('current'),
            'trend': parse_trend(entry.get('trend')),
            'names': [team.get('location'), team.get('nickname'),
                      team.get('abbreviation')],
            'record': entry.get('recordSummary') or '',
            'is_team': is_team,
        })
        if is_team:
            result['team']['ap'] = entry.get('current')
            result['team']['trend'] = parse_trend(entry.get('trend'))

    if result['team']['ap'] is None:
        for entry in ap.get('others') or []:
            if str((entry.get('team') or {}).get('id')) == str(team_id):
                result['team']['votes'] = int(entry.get('points') or 0)

    coaches = find('usa')
    for entry in (coaches or {}).get('ranks') or []:
        if str((entry.get('team') or {}).get('id')) == str(team_id):
            result['team']['coaches'] = entry.get('current')
    return result


def _record_pct(record: str) -> float:
    """'12-3' -> 0.8; an unplayed or unparseable record sorts as .000"""
    try:
        wins, losses = (int(part) for part in record.split('-')[:2])
        return wins / (wins + losses) if wins + losses else 0.0
    except (ValueError, AttributeError):
        return 0.0


def parse_standings(payload: dict, team_id: str) -> list[dict[str, Any]]:
    """Conference table, best first: conference record, then overall.

    ESPN returns the entries unordered (and every seed as 0 until league
    play starts), so the order is computed here. The sort is stable, so
    full ties keep ESPN's order.
    """
    standings = payload.get('standings')
    if standings is None:
        children = payload.get('children') or []
        standings = children[0].get('standings') if children else None
    rows = []
    for entry in (standings or {}).get('entries') or []:
        team = entry.get('team') or {}
        stats = {stat.get('name'): stat.get('displayValue')
                 for stat in entry.get('stats') or []}
        rows.append({
            'abbrev': (team.get('abbreviation') or '').upper(),
            'conf': stats.get('vs. Conf.') or '0-0',
            'overall': stats.get('overall') or '0-0',
            'is_team': str(team.get('id')) == str(team_id),
        })
    rows.sort(key=lambda row: (-_record_pct(row['conf']),
                               -_record_pct(row['overall'])))
    for position, row in enumerate(rows, start=1):
        row['position'] = position
    return rows


def page_count(row_count: int, per_page: int = ROWS_PER_PAGE) -> int:
    return max(1, -(-row_count // per_page))


# --- Display --------------------------------------------------------------

class CollegeBasketballDisplay:
    """College basketball screens for the configured team"""

    def __init__(self, scoreboard_manager: ScoreboardManager) -> None:
        self.manager = scoreboard_manager
        self.team = get_active_ncaab_team()

        self.PRIMARY: RGBColor = self.team.primary_color
        self.ACCENT: RGBColor = self.team.accent_color
        self.TEXT_WHITE: RGBColor = Colors.WHITE
        self.TEXT_GRAY: RGBColor = (170, 170, 170)
        self.LOSS_RED: RGBColor = (220, 60, 60)
        self.UP_GREEN: RGBColor = (60, 210, 90)

        self.schedule: dict[str, Any] | None = None
        self.last_schedule_update: float | None = None
        self.schedule_interval: int = GameConfig.SCHEDULE_UPDATE_INTERVAL

        # Polls move weekly and standings nightly; an hour is plenty
        self._rankings: dict[str, Any] | None = None
        self._rankings_at: float = 0.0
        self._standings: list[dict[str, Any]] | None = None
        self._standings_at: float = 0.0

        self._news: list[str] | None = None
        self._news_at: float = 0.0

        self.facts: list[str] = self._load_facts()
        self._shuffled_facts: list[str] = random.sample(
            self.facts, len(self.facts))
        self._fact_index: int = 0

        # Logos keyed by ESPN team id; None = file missing
        self._logo_cache: dict[str, Image.Image | None] = {}
        self._header_bg: Image.Image = self._make_background(12)
        self._compact_bg: Image.Image = self._make_background(9)

    # --- Data ---

    def _load_facts(self) -> list[str]:
        for path in data_path_candidates(self.team.facts_basename):
            try:
                with open(path, 'r') as f:
                    facts = json.load(f).get('facts', [])
                if facts:
                    return facts
            except (OSError, json.JSONDecodeError):
                continue
        return [f'GO {self.team.short_name.upper()}!']

    def _get_json(self, url: str) -> dict:
        return retry_http_request(url, timeout=10).json()

    def _fetch_schedule(self) -> bool:
        """Regular season plus postseason. ESPN serves the NCAA
        tournament from a separate season type, so one request would end
        the schedule on Selection Sunday."""
        base = f'{ESPN_SITE}/teams/{self.team.espn_team_id}/schedule'
        try:
            data = self._get_json(base)
        except Exception as e:
            print(f'Error fetching {self.team.short_name} schedule: {e}')
            return False

        events = list(data.get('events') or [])
        try:
            post = self._get_json(f'{base}?seasontype=3')
            seen = {event.get('id') for event in events}
            events += [event for event in post.get('events') or []
                       if event.get('id') not in seen]
        except Exception as e:
            print(f'Postseason schedule unavailable: {e}')
        events.sort(key=lambda event: event.get('date', ''))
        data['events'] = events

        self.schedule = data
        self.last_schedule_update = time.time()
        print(f'{self.team.short_name} basketball schedule updated '
              f'({len(events)} games)')
        return True

    def _schedule_stale(self) -> bool:
        if not self.schedule or not self.last_schedule_update:
            return True
        return time.time() - self.last_schedule_update > self.schedule_interval

    def _ensure_schedule(self) -> bool:
        if self._schedule_stale():
            self._fetch_schedule()
        return bool(self.schedule)

    def _events(self) -> list[dict]:
        return (self.schedule or {}).get('events') or []

    def _get_todays_game(self) -> dict | None:
        """The game on today's Central date, or one that tipped off in the
        last few hours (a late game that has run past midnight)."""
        now = pendulum.now('America/Chicago')
        today = now.format('YYYY-MM-DD')
        recent = None
        try:
            for event in self._events():
                tip = pendulum.parse(event['date']).in_timezone(
                    'America/Chicago')
                if tip.format('YYYY-MM-DD') == today:
                    return event
                if now.subtract(hours=RECENT_START_HOURS) <= tip <= now:
                    recent = event
        except Exception as e:
            print(f'Error finding today\'s basketball game: {e}')
        return recent

    def _get_next_game(self) -> dict | None:
        now = pendulum.now()
        try:
            for event in self._events():
                if pendulum.parse(event['date']) > now:
                    return event
        except Exception as e:
            print(f'Error finding next basketball game: {e}')
        return None

    def has_game_within(self, days_back: int = 3,
                        days_ahead: int = 14) -> bool:
        """True when the schedule holds a game in the recent past or near
        future - the season test for every basketball screen. Schedule
        driven, so exhibitions and the postseason count without a code
        change; the window stays narrow because ESPN keeps last season's
        schedule up all summer."""
        try:
            if not self._ensure_schedule():
                return basketball_month_gate()
            now = pendulum.now('America/Chicago')
            start = now.subtract(days=days_back)
            end = now.add(days=days_ahead)
            for event in self._events():
                tip = pendulum.parse(event['date']).in_timezone(
                    'America/Chicago')
                if start <= tip <= end:
                    return True
            return False
        except Exception as e:
            print(f'Basketball schedule window check failed: {e}')
            return basketball_month_gate()

    def _fetch_live_event(self, game_id) -> dict | None:
        """One game in scoreboard shape. The league scoreboard only lists
        ranked and featured games by default, so the game is asked for by
        id instead of being searched for."""
        try:
            event = self._get_json(f'{ESPN_SITE}/scoreboard/{game_id}')
            return event if event.get('competitions') else None
        except Exception as e:
            print(f'Error fetching live basketball score: {e}')
            return None

    def live_game(self) -> dict | None:
        """Today's game when ESPN reports it in progress, else None.
        Read from the scoreboard, not the hour-old cached schedule."""
        try:
            if not self._ensure_schedule():
                return None
            game = self._get_todays_game()
            if not game:
                return None
            fresh = self._fetch_live_event(game.get('id')) or game
            state = fresh['competitions'][0]['status']['type']['state']
            return game if state == 'in' else None
        except Exception as e:
            print(f'Basketball live check failed: {e}')
            return None

    def _get_current_scores(self, game: dict) -> dict[str, Any] | None:
        """Everything the game-day screens draw, from the freshest source
        available (scoreboard, falling back to the cached schedule event)."""
        try:
            event = self._fetch_live_event(game.get('id')) or game
            competition = event['competitions'][0]
            team, opponent = split_competitors(
                competition, self.team.espn_team_id)
            status_type = competition['status']['type']
            opp_team = opponent.get('team') or {}
            return {
                'status': status_type.get('name'),
                'state': status_type.get('state'),
                'detail': (status_type.get('shortDetail') or '').upper(),
                'team_score': competitor_score(team),
                'opp_score': competitor_score(opponent),
                'opp_abbr': (opp_team.get('abbreviation') or 'OPP').upper(),
                'opp_id': str(opp_team.get('id') or opponent.get('id')),
                'team_lines': extract_half_scores(team),
                'opp_lines': extract_half_scores(opponent),
                'team_stats': extract_stats(team),
                'opp_stats': extract_stats(opponent),
            }
        except Exception as e:
            print(f'Error reading basketball score: {e}')
            return None

    def _get_rankings(self) -> dict[str, Any] | None:
        if (self._rankings is None
                or time.time() - self._rankings_at > self.schedule_interval):
            try:
                self._rankings = parse_rankings(
                    self._get_json(f'{ESPN_SITE}/rankings'),
                    self.team.espn_team_id)
                self._rankings_at = time.time()
            except Exception as e:
                print(f'Error fetching basketball rankings: {e}')
        return self._rankings

    def _get_standings(self) -> list[dict[str, Any]] | None:
        if (self._standings is None
                or time.time() - self._standings_at > self.schedule_interval):
            try:
                self._standings = parse_standings(
                    self._get_json(
                        f'{ESPN_STANDINGS}?group={self.team.conference_id}'),
                    self.team.espn_team_id)
                self._standings_at = time.time()
            except Exception as e:
                print(f'Error fetching basketball standings: {e}')
        return self._standings

    def _fetch_news(self) -> list[str]:
        """Team headlines from ESPN's team news feed; when that is empty,
        the league-wide RSS feed filtered by the pack's keywords."""
        prefix = f'{self.team.short_name.upper()} NEWS - '
        headlines: list[str] = []
        try:
            data = self._get_json(
                f'{ESPN_SITE}/news?team={self.team.espn_team_id}&limit=15')
            for article in data.get('articles') or []:
                headline = (article.get('headline') or '').strip().upper()
                if headline and prefix + headline not in headlines:
                    headlines.append(prefix + headline)
        except Exception as e:
            print(f'Error fetching {self.team.short_name} news: {e}')

        if not headlines:
            try:
                for entry in fetch_feed(FALLBACK_NEWS_RSS).entries[:30]:
                    headline = entry.title.strip().upper()
                    if (any(key in headline
                            for key in self.team.news_keywords)
                            and is_probably_english(headline)
                            and prefix + headline not in headlines):
                        headlines.append(prefix + headline)
            except Exception as e:
                print(f'Error fetching college basketball RSS: {e}')
        return headlines[:12]

    def _get_news(self) -> list[str]:
        if (not self._news
                or time.time() - self._news_at
                > GameConfig.NEWS_UPDATE_INTERVAL):
            self._draw_loading('FETCHING NEWS...')
            self._news = self._fetch_news()
            self._news_at = time.time()
        return self._news or []

    # --- Shared drawing ---

    def _make_background(self, stripe_y: int) -> Image.Image:
        """Full frame in the primary color with accent stripes framing a
        header band: rows 0-1 and stripe_y-1..stripe_y for the full header,
        a single rule at stripe_y for the compact one."""
        img = Image.new('RGB', (96, 48), self.PRIMARY)
        pixels = img.load()
        rows = (0, 1, stripe_y - 1, stripe_y) if stripe_y >= 12 else (stripe_y,)
        for y in rows:
            for x in range(96):
                pixels[x, y] = self.ACCENT
        return img

    def _draw_header(self, title: str | None = None) -> None:
        """Full header (y0-12); content draws from y13 down"""
        self.manager.set_image(self._header_bg, 0, 0)
        title = title or self.team.header_name
        if len(title) * Fonts.CHAR_WIDTH_STANDARD <= 96:
            x = max(0, (96 - len(title) * Fonts.CHAR_WIDTH_STANDARD) // 2)
            # Drawn twice 1px apart: faux-bold thickens the hinted stems
            self.manager.draw_text('standard_bold', x, 11,
                                   self.TEXT_WHITE, title)
            self.manager.draw_text('standard_bold', x + 1, 11,
                                   self.TEXT_WHITE, title)
        else:
            x = max(0, (96 - len(title) * Fonts.CHAR_WIDTH_TINY) // 2)
            self.manager.draw_text('tiny_bold', x, 10, self.TEXT_WHITE, title)

    def _draw_compact_header(self, title: str, right: str = '') -> None:
        """One-line header (y0-9) for the table screens, which need the
        rows a full header would take: title left, column labels right."""
        self.manager.set_image(self._compact_bg, 0, 0)
        self.manager.draw_text('tiny_bold', 2, 7, self.TEXT_WHITE, title)
        if right:
            x = 96 - len(right) * Fonts.CHAR_WIDTH_MICRO
            self.manager.draw_text('micro', x, 7, self.ACCENT, right)

    def _draw_centred(self, text: str, baseline: int, color: RGBColor,
                      font: str = 'tiny') -> None:
        """Centred line in tiny (or tiny_bold); drops to micro when the
        text is wider than the panel."""
        if len(text) * Fonts.CHAR_WIDTH_TINY - 1 > 96:
            font, width = 'micro', Fonts.CHAR_WIDTH_MICRO
        else:
            width = Fonts.CHAR_WIDTH_TINY
        self.manager.draw_text(font, _centred_x(text, width), baseline,
                               color, text)

    def _draw_loading(self, message: str) -> None:
        self.manager.clear_canvas()
        self._draw_header()
        self._draw_centred(message, 33, self.TEXT_WHITE)
        self.manager.swap_canvas()

    def _get_logo(self, team_id) -> Image.Image | None:
        """20x20 logo flattened onto the background color, or None"""
        key = str(team_id)
        if key not in self._logo_cache:
            try:
                logo = Image.open(f'./logos/ncaab/{key}.png').convert('RGBA')
                if logo.size != (20, 20):
                    logo = logo.resize((20, 20), Image.LANCZOS)
                flat = Image.new('RGB', (20, 20), self.PRIMARY)
                flat.paste(logo, (0, 0), logo)
                self._logo_cache[key] = flat
            except OSError:
                self._logo_cache[key] = None
        return self._logo_cache[key]

    def _draw_trend(self, x: int, baseline: int, trend: int) -> None:
        """3px poll-movement arrow: green up, red down, nothing if flat"""
        if trend > 0:
            color, rows = self.UP_GREEN, ((1,), (0, 1, 2))
        elif trend < 0:
            color, rows = self.LOSS_RED, ((0, 1, 2), (1,))
        else:
            return
        for dy, columns in enumerate(rows):
            for dx in columns:
                self.manager.draw_pixel(x + dx, baseline - 4 + dy, *color)

    def _sleep_frame(self) -> None:
        time.sleep(FRAME_SECONDS)

    # --- Game screens ---

    def display_game_info(self, duration=120, loop_until_final=False,
                          force_scheduled=False, yield_to=None) -> None:
        """Game day (countdown, live score, final) or the next-game card.

        loop_until_final: hold the live game on screen until it ends.
        force_scheduled: show today's game as an upcoming card rather
            than live scores, because another sport owns the screen.
        yield_to: optional callable polled at each score refresh;
            returning True hands the screen back.
        """
        if not self._ensure_schedule():
            return
        todays_game = self._get_todays_game()
        if todays_game and not force_scheduled:
            self._display_game_day(todays_game, duration,
                                   loop_until_final, yield_to)
            return
        game = todays_game or self._get_next_game()
        if game:
            self._display_matchup(game, duration)

    def _display_matchup(self, game: dict, duration: float) -> None:
        start = time.time()
        frame = 0
        try:
            while time.time() - start < duration:
                self.manager.clear_canvas()
                self._draw_header()
                self._draw_matchup_card(game, frame)
                self.manager.swap_canvas()
                frame += 1
                self._sleep_frame()
        except Exception as e:
            print(f'Error displaying basketball matchup: {e}')

    def _draw_matchup_card(self, game: dict, frame: int) -> None:
        """Ranks and crests either side of NEXT / TODAY, the opponent
        named underneath, and a bottom line that rotates between the tip
        time, the TV countdown and (tournament games) the round."""
        competition = game['competitions'][0]
        team, opponent = split_competitors(
            competition, self.team.espn_team_id)
        opp_team = opponent.get('team') or {}
        tip = pendulum.parse(game['date']).in_timezone('America/Chicago')
        now = pendulum.now('America/Chicago')
        is_today = tip.format('YYYY-MM-DD') == now.format('YYYY-MM-DD')
        seconds = (tip - now).total_seconds()

        label = 'TODAY' if is_today else 'NEXT'
        self.manager.draw_text(
            'ultra_micro',
            _centred_x(label, Fonts.CHAR_WIDTH_ULTRA_MICRO), 20,
            self.TEXT_GRAY, label)
        vs_at = site_label(competition, team)
        self.manager.draw_text(
            'tiny_bold', _centred_x(vs_at, Fonts.CHAR_WIDTH_TINY), 30,
            self.TEXT_WHITE, vs_at)

        self._draw_card_side(self.team.espn_team_id, self.team.abbrev,
                             competitor_rank(team), left=True)
        self._draw_card_side(opp_team.get('id'),
                             opp_team.get('abbreviation') or '',
                             competitor_rank(opponent), left=False)

        name = fit_name([opp_team.get('shortDisplayName'),
                         opp_team.get('location'),
                         opp_team.get('abbreviation')], 19)
        self._draw_centred(name, 40, self.ACCENT, font='tiny_bold')

        time_text = format_kickoff_time(tip)
        date_line = (time_text if is_today
                     else f"{tip.format('ddd MMM D').upper()} {time_text}")
        lines = [(date_line, self.TEXT_WHITE)]
        network = (extract_broadcast(competition) or '').upper()
        if seconds > 0:
            countdown = format_countdown(seconds)
            text = (f'{network} IN {countdown}' if network
                    else f'TIPOFF IN {countdown}')
            if is_today:
                color = countdown_color(seconds, 3 * 3600, 3600)
            else:
                color = countdown_color(seconds, 24 * 3600, 3 * 3600)
            lines.append((text, color))
        elif network:
            lines.append((network, self.TEXT_GRAY))
        note = short_note(competition)
        if note:
            lines.append((note, self.TEXT_GRAY))

        # Each line holds for four seconds
        text, color = lines[(frame // 8) % len(lines)]
        self._draw_centred(text, 47, color)

    def _draw_card_side(self, team_id, abbrev: str, rank: int | None,
                        left: bool) -> None:
        """Crest with its poll rank on the outside edge"""
        logo_x = 16 if left else 60
        logo = self._get_logo(team_id)
        if logo is not None:
            self.manager.set_image(logo, logo_x, 13)
        else:
            text = abbrev.upper()[:4]
            x = _centred_x(text, Fonts.CHAR_WIDTH_TINY, span=20,
                           origin=logo_x)
            self.manager.draw_text('tiny_bold', x, 27, self.TEXT_WHITE, text)
        if rank is not None:
            # tiny: the '#' in the two smaller fonts is an unreadable blob.
            # '#25' is 15px, which is all the room outside either crest.
            text = f'#{rank}'
            width = len(text) * Fonts.CHAR_WIDTH_TINY
            x = (logo_x - 1 - width) if left else (logo_x + 21)
            self.manager.draw_text('tiny', x, 27, self.ACCENT, text)

    def _display_game_day(self, game: dict, duration: float,
                          loop_until_final: bool, yield_to) -> None:
        start = time.time()
        last_update = time.time()
        frame = 0
        celebrated = False
        try:
            score_data = self._get_current_scores(game)
            if not score_data:
                return
            print(f"Basketball game status: {score_data['status']} "
                  f"({score_data['detail']})")

            while True:
                state = score_data.get('state')
                if loop_until_final:
                    # Entered on state 'in', so left on anything else:
                    # 'post' also covers a postponed or cancelled game
                    # that never reaches STATUS_FINAL.
                    if (state != 'in' or is_shutdown_requested()
                            or time.time() - start >= TAKEOVER_MAX_SECONDS):
                        break
                elif time.time() - start >= duration:
                    break

                interval = (LIVE_UPDATE_SECONDS if state == 'in'
                            else PREGAME_UPDATE_SECONDS)
                if state != 'post' and time.time() - last_update >= interval:
                    score_data = (self._get_current_scores(game)
                                  or score_data)
                    last_update = time.time()
                    if yield_to is not None and yield_to():
                        break
                    continue

                if state == 'post' and not celebrated:
                    celebrated = True
                    self._celebrate_if_won(score_data)

                self.manager.clear_canvas()
                self._draw_header()
                if state == 'in':
                    self._draw_live_content(score_data, frame)
                elif score_data['status'] == 'STATUS_FINAL':
                    self._draw_final_content(score_data, frame)
                else:
                    self._draw_matchup_card(game, frame)
                self.manager.swap_canvas()
                frame += 1
                self._sleep_frame()

            # A takeover that ran to the final horn shows the result
            # before handing the screen back, rather than cutting from a
            # live score straight to whatever the rotation has next.
            if (loop_until_final and score_data['status'] == 'STATUS_FINAL'
                    and not is_shutdown_requested()):
                self._celebrate_if_won(score_data)
                for frame in range(int(FINAL_HOLD_SECONDS / FRAME_SECONDS)):
                    self.manager.clear_canvas()
                    self._draw_header()
                    self._draw_final_content(score_data, frame)
                    self.manager.swap_canvas()
                    self._sleep_frame()
        except Exception as e:
            print(f'Error displaying basketball game: {e}')
            import traceback
            traceback.print_exc()

    def _celebrate_if_won(self, score_data: dict) -> None:
        team_int, opp_int = _score_pair(
            score_data['team_score'], score_data['opp_score'])
        if (score_data['status'] == 'STATUS_FINAL'
                and team_int is not None and team_int > opp_int):
            self._play_win_celebration()

    def _draw_live_content(self, score_data: dict, frame: int) -> None:
        """Crest and score per half of the panel, a line that rotates the
        lead with team stats, and the clock on the bottom strip."""
        team_score = str(score_data['team_score'])
        opp_score = str(score_data['opp_score'])
        # Three digits in the big font would run into the other crest
        if max(len(team_score), len(opp_score)) >= 3:
            font, baseline = 'standard_bold', 28
        else:
            font, baseline = 'medium_bold', 29

        for half_x, team_id, abbrev, score in (
                (0, self.team.espn_team_id, self.team.abbrev, team_score),
                (48, score_data['opp_id'], score_data['opp_abbr'],
                 opp_score)):
            logo = self._get_logo(team_id)
            if logo is not None:
                self.manager.set_image(logo, half_x + 2, 13)
                self.manager.draw_text(font, half_x + 24, baseline,
                                       self.TEXT_WHITE, score)
            else:
                self.manager.draw_text(
                    'tiny_bold', half_x + 2, 21, self.TEXT_GRAY,
                    abbrev[:4])
                self.manager.draw_text('standard_bold', half_x + 2, 32,
                                       self.TEXT_WHITE, score)

        lines = self._live_lines(score_data)
        if lines:
            text, color = lines[(frame // 8) % len(lines)]
            self._draw_centred(text, 39, color)

        detail = score_data.get('detail') or ''
        if detail:
            self._draw_centred(detail, 47, self.TEXT_WHITE)

    def _live_lines(self, score_data: dict) -> list[tuple[str, RGBColor]]:
        """Middle-line rotation: the lead holds two of every four slots,
        shooting and rebounding take one each when ESPN sends them."""
        lead = lead_text(self.team.abbrev, score_data['team_score'],
                         score_data['opp_abbr'], score_data['opp_score'])
        if not lead:
            return []
        lead_color = (self.ACCENT if lead.startswith(self.team.abbrev + ' ')
                      else self.TEXT_WHITE)
        lines = [(lead, lead_color), (lead, lead_color)]
        team_stats = score_data.get('team_stats') or {}
        opp_stats = score_data.get('opp_stats') or {}
        # 'FG PCT', whole numbers: tiny's '%' is an unreadable smudge
        for stat, label in (('fieldGoalPct', 'FG PCT'), ('rebounds', 'REB')):
            mine = _whole(team_stats.get(stat))
            theirs = _whole(opp_stats.get(stat))
            if mine and theirs:
                lines.append((f'{label} {mine} - {theirs}', self.TEXT_GRAY))
        return lines

    # Final-screen box score: half-by-half grid with the result badge to
    # its right, the same arrangement as the NFL final.
    BOX_LABEL_X = 2
    BOX_GRID_RIGHT = 66
    BOX_ROW_Y = (33, 40, 47)
    BADGE_X = 72
    BADGE_W = 22

    def _draw_final_content(self, score_data: dict, frame: int) -> None:
        team_score = str(score_data['team_score'])
        opp_score = str(score_data['opp_score'])
        team_int, opp_int = _score_pair(team_score, opp_score)
        team_color = opp_color = self.TEXT_WHITE
        if team_int is not None and team_int != opp_int:
            if team_int < opp_int:
                team_color = self.TEXT_GRAY
            else:
                opp_color = self.TEXT_GRAY

        # Crests on the outside, scores mirrored about the centre
        width = Fonts.CHAR_WIDTH_STANDARD
        for logo_x, text_x, team_id, abbrev, score, color in (
                (2, 48 - 4 - len(team_score) * width,
                 self.team.espn_team_id, self.team.abbrev, team_score,
                 team_color),
                (74, 52, score_data['opp_id'], score_data['opp_abbr'],
                 opp_score, opp_color)):
            logo = self._get_logo(team_id)
            if logo is not None:
                self.manager.set_image(logo, logo_x, 13)
            else:
                self.manager.draw_text('tiny_bold', logo_x, 21,
                                       self.TEXT_GRAY, abbrev[:4])
            self.manager.draw_text('standard_bold', text_x, 27, color, score)

        team_lines = score_data.get('team_lines') or []
        opp_lines = score_data.get('opp_lines') or []
        has_box = bool(team_lines) and bool(opp_lines)
        if has_box:
            self._draw_box_score(score_data, team_lines, opp_lines)

        went_to_ot = max(len(team_lines), len(opp_lines)) > 2
        self._draw_result_badge(team_int, opp_int, frame,
                                'F/OT' if went_to_ot else 'FINAL',
                                in_slot=has_box)

    def _draw_box_score(self, score_data: dict, team_lines: list[str],
                        opp_lines: list[str]) -> None:
        columns = max(len(team_lines), len(opp_lines))
        headers = ['1', '2'][:columns] + (['OT'] if columns > 2 else [])
        pitch = 14

        def cell_x(index: int, text: str) -> int:
            right = self.BOX_GRID_RIGHT - (columns - 1 - index) * pitch
            return right - len(text) * Fonts.CHAR_WIDTH_ULTRA_MICRO

        head_y, team_y, opp_y = self.BOX_ROW_Y
        for i, head in enumerate(headers):
            self.manager.draw_text('ultra_micro', cell_x(i, head), head_y,
                                   self.ACCENT, head)
        for label, values, y in (
                (self.team.abbrev, team_lines, team_y),
                (score_data['opp_abbr'], opp_lines, opp_y)):
            self.manager.draw_text('tiny', self.BOX_LABEL_X, y,
                                   self.TEXT_GRAY, label[:4])
            for i, value in enumerate(values):
                self.manager.draw_text('ultra_micro', cell_x(i, value), y,
                                       self.TEXT_WHITE, value)

    def _draw_result_badge(self, team_int, opp_int, frame: int,
                           final_text: str, in_slot: bool) -> None:
        """WIN!/LOSS over FINAL: beside the box score, or centred when
        the payload carried no half scores."""
        span, origin = (self.BADGE_W, self.BADGE_X) if in_slot else (96, 0)
        result = None
        if team_int is not None and team_int > opp_int:
            color = self.ACCENT if (frame // 2) % 2 == 0 else self.TEXT_WHITE
            result = ('WIN!', color)
        elif team_int is not None and team_int < opp_int:
            result = ('LOSS', self.LOSS_RED)
        if result:
            text, color = result
            self.manager.draw_text(
                'tiny_bold',
                _centred_x(text, Fonts.CHAR_WIDTH_TINY, span, origin),
                40, color, text)
        self.manager.draw_text(
            'ultra_micro',
            _centred_x(final_text, Fonts.CHAR_WIDTH_ULTRA_MICRO, span,
                       origin),
            47, self.ACCENT, final_text)

    def _play_win_celebration(self) -> None:
        """Flash the pack's chant, then the win banner"""
        chant = self.team.win_chant
        beats = [chant[i % len(chant)] for i in range(len(chant) * 3)]
        banner = f'{self.team.short_name.upper()} WIN!'
        for index, text in enumerate(beats + [banner] * 4):
            color = self.ACCENT if index % 2 == 0 else self.TEXT_WHITE
            self.manager.clear_canvas()
            self._draw_header()
            if len(text) * Fonts.CHAR_WIDTH_LARGE <= 96:
                font, width, baseline = 'large_bold', Fonts.CHAR_WIDTH_LARGE, 38
            else:
                font, width, baseline = 'medium_bold', Fonts.CHAR_WIDTH_MEDIUM, 37
            self.manager.draw_text(font, _centred_x(text, width), baseline,
                                   color, text)
            self.manager.swap_canvas()
            time.sleep(0.7)

    # --- Rankings ---

    def display_rankings(self, duration=60) -> bool:
        """The team's poll card, then the Top 25 five rows at a time.
        Returns False (drawing nothing) when no poll is available."""
        rankings = self._get_rankings()
        if not rankings or not rankings['rows']:
            return False
        standings = self._get_standings() or []
        # Before league play every team is 0-0 and the table is ordered
        # by overall record alone - not a conference place worth quoting
        conference_position = next(
            (row['position'] for row in standings
             if row['is_team'] and row['conf'] != '0-0'), None)

        pages = page_count(len(rankings['rows']))
        start = time.time()
        frame = 0
        frames_per_page = int(PAGE_SECONDS / FRAME_SECONDS)
        try:
            while time.time() - start < duration:
                # Slot 0 is the team card; the poll pages follow
                slot = (frame // frames_per_page) % (pages + 1)
                self.manager.clear_canvas()
                if slot == 0:
                    self._draw_header()
                    self._draw_rank_card(rankings, conference_position)
                else:
                    self._draw_rankings_page(rankings, slot - 1, pages)
                self.manager.swap_canvas()
                frame += 1
                self._sleep_frame()
        except Exception as e:
            print(f'Error displaying basketball rankings: {e}')
        return True

    def _draw_rank_card(self, rankings: dict,
                        conference_position: int | None) -> None:
        """Crest, the AP rank in the big font, coaches poll beneath, and
        record plus conference place along the bottom."""
        team = rankings['team']
        logo = self._get_logo(self.team.espn_team_id)
        if logo is not None:
            self.manager.set_image(logo, 5, 15)

        if team['ap'] is not None:
            rank_text = f"#{team['ap']}"
            self.manager.draw_text('large_bold', 31, 32, self.ACCENT,
                                   rank_text)
            label_x = 31 + len(rank_text) * Fonts.CHAR_WIDTH_LARGE + 4
            self.manager.draw_text('tiny', label_x, 23, self.TEXT_WHITE,
                                   'AP')
            self.manager.draw_text('tiny', label_x, 31, self.TEXT_WHITE,
                                   'TOP 25')
            self._draw_trend(label_x + 13, 23, team['trend'])
        else:
            self.manager.draw_text('tiny_bold', 31, 23, self.TEXT_WHITE,
                                   'UNRANKED')
            votes = team.get('votes')
            sub = f'{votes} AP VOTES' if votes else 'AP TOP 25'
            self.manager.draw_text('tiny', 31, 31, self.TEXT_GRAY, sub)

        if team['coaches'] is not None:
            self.manager.draw_text('tiny', 31, 40, self.TEXT_GRAY,
                                   f"COACHES #{team['coaches']}")

        parts = []
        record = ((self.schedule or {}).get('team') or {}).get(
            'recordSummary')
        if record:
            parts.append(record)
        if conference_position is not None:
            parts.append(f'{_ordinal(conference_position)} IN '
                         f'{self.team.conference_name}')
        if parts:
            self._draw_centred('  '.join(parts), 47, self.TEXT_WHITE)

    def _draw_rankings_page(self, rankings: dict, page: int,
                            pages: int) -> None:
        self._draw_compact_header(rankings['poll_name'],
                                  f'{page + 1}/{pages}')
        rows = rankings['rows'][page * ROWS_PER_PAGE:
                                (page + 1) * ROWS_PER_PAGE]
        for index, row in enumerate(rows):
            baseline = 17 + index * 7
            color = self.ACCENT if row['is_team'] else self.TEXT_WHITE
            rank = str(row['rank'])
            self.manager.draw_text(
                'tiny', 11 - len(rank) * Fonts.CHAR_WIDTH_TINY, baseline,
                color, rank)
            self._draw_trend(12, baseline, row['trend'])
            record = row['record']
            record_x = 96 - len(record) * Fonts.CHAR_WIDTH_TINY
            max_chars = (record_x - 2 - 17) // Fonts.CHAR_WIDTH_TINY
            self.manager.draw_text('tiny', 17, baseline, color,
                                   fit_name(row['names'], max_chars))
            self.manager.draw_text(
                'tiny', record_x, baseline,
                color if row['is_team'] else self.TEXT_GRAY, record)

    # --- Standings ---

    def display_standings(self, duration=60) -> bool:
        """Conference table, five rows at a time, opening on the page
        that holds the team. Returns False when unavailable."""
        rows = self._get_standings()
        if not rows:
            return False
        pages = page_count(len(rows))
        team_page = next((index // ROWS_PER_PAGE
                          for index, row in enumerate(rows)
                          if row['is_team']), 0)
        start = time.time()
        frame = 0
        frames_per_page = int(PAGE_SECONDS / FRAME_SECONDS)
        try:
            while time.time() - start < duration:
                page = (team_page + frame // frames_per_page) % pages
                self.manager.clear_canvas()
                self._draw_standings_page(rows, page)
                self.manager.swap_canvas()
                frame += 1
                self._sleep_frame()
        except Exception as e:
            print(f'Error displaying basketball standings: {e}')
        return True

    def _draw_standings_page(self, rows: list[dict], page: int) -> None:
        self._draw_compact_header(self.team.conference_name, 'CONF   ALL')
        for index, row in enumerate(
                rows[page * ROWS_PER_PAGE:(page + 1) * ROWS_PER_PAGE]):
            baseline = 17 + index * 7
            color = self.ACCENT if row['is_team'] else self.TEXT_WHITE
            position = str(row['position'])
            self.manager.draw_text(
                'tiny', 11 - len(position) * Fonts.CHAR_WIDTH_TINY,
                baseline, self.TEXT_GRAY if not row['is_team'] else color,
                position)
            self.manager.draw_text('tiny', 15, baseline, color,
                                   row['abbrev'][:5])
            for text, right in ((row['conf'], 68), (row['overall'], 96)):
                self.manager.draw_text(
                    'tiny', right - len(text) * Fonts.CHAR_WIDTH_TINY,
                    baseline, color, text)

    # --- News and facts ---

    def display_news(self, duration=120) -> None:
        news = self._get_news() or [
            f'{self.team.short_name.upper()} NEWS - STAY TUNED FOR THE '
            f'LATEST {self.team.short_name.upper()} UPDATES!']
        self._scroll_messages(lambda index: news[index % len(news)],
                              duration, 'scroll_speed_ncaab_news')

    def display_facts(self, duration=120) -> None:
        def next_fact(_index: int) -> str:
            if self._fact_index >= len(self._shuffled_facts):
                self._shuffled_facts = random.sample(
                    self.facts, len(self.facts))
                self._fact_index = 0
            fact = self._shuffled_facts[self._fact_index]
            self._fact_index += 1
            return fact

        self._scroll_messages(next_fact, duration, 'scroll_speed_ncaab_facts')

    def _scroll_messages(self, message_at, duration: float,
                         speed_key: str) -> None:
        """Scroll messages one after another under the full header;
        message_at(n) supplies the nth message of this pass."""
        start = time.time()
        index = 0
        message = message_at(index)
        scroll_x = 96
        while time.time() - start < duration:
            try:
                self.manager.clear_canvas()
                self._draw_header()
                scroll_x -= 1
                if scroll_x + len(message) * Fonts.CHAR_WIDTH_MEDIUM < 0:
                    scroll_x = 96
                    index += 1
                    message = message_at(index)
                self.manager.draw_text('medium_bold', scroll_x, 38,
                                       self.TEXT_WHITE, message)
                self.manager.swap_canvas()
                time.sleep(get_scroll_delay(
                    load_user_config().get(speed_key, 5)))
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f'Error in basketball scroll display: {e}')
                time.sleep(1)


def _whole(value) -> str:
    """'48.2' -> '48'; '' when the stat is missing or will not parse"""
    try:
        return str(round(float(value)))
    except (ValueError, TypeError):
        return ''


def _ordinal(number: int) -> str:
    """1 -> '1ST', 2 -> '2ND', 11 -> '11TH'"""
    if 10 <= number % 100 <= 20:
        suffix = 'TH'
    else:
        suffix = {1: 'ST', 2: 'ND', 3: 'RD'}.get(number % 10, 'TH')
    return f'{number}{suffix}'

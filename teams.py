"""Team packs: per-team identity, colors, assets, and content sources.

The active team is selected by the "team" key in /home/pi/config.json
(written by the admin panel). Missing or unknown values fall back to the
Cubs so existing boards behave exactly as before.
"""

from __future__ import annotations

from dataclasses import dataclass

from scoreboard_config import RGBColor, load_user_config

DEFAULT_TEAM_SLUG = 'cubs'

# Content that only makes sense for a Chicago board; defaults to off for
# other teams unless the user explicitly re-enables it in the admin panel.
NON_DEFAULT_OFF_KEYS: tuple[str, ...] = (
    'enable_bears', 'enable_bears_news', 'enable_clock')


@dataclass(frozen=True)
class TeamPack:
    """Everything the display needs to brand itself for one MLB team"""
    slug: str
    mlb_team_id: int
    name: str
    short_name: str
    abbrev: str
    matchup_name: str          # "X VS OPPONENT" pre-game text
    primary_color: RGBColor
    secondary_color: RGBColor
    logo_path: str
    marquee_path: str
    celebration_path: str      # animated GIF shown after a win
    facts_basename: str        # resolved via data_path_candidates()
    history_basename: str      # resolved via data_path_candidates()
    news_rss_url: str


TEAMS: dict[str, TeamPack] = {
    'cubs': TeamPack(
        slug='cubs',
        mlb_team_id=112,
        name='Chicago Cubs',
        short_name='Cubs',
        abbrev='CHC',
        matchup_name='CHICAGO CUBS',
        primary_color=(0, 51, 102),
        secondary_color=(204, 52, 51),
        logo_path='./logos/cubs.png',
        marquee_path='./marquee.png',
        celebration_path='./W.gif',
        facts_basename='cubs_facts.json',
        history_basename='cubs_history.json',
        news_rss_url='https://www.mlb.com/cubs/feeds/news/rss.xml',
    ),
    'cardinals': TeamPack(
        slug='cardinals',
        mlb_team_id=138,
        name='St. Louis Cardinals',
        short_name='Cardinals',
        abbrev='STL',
        matchup_name='ST LOUIS CARDINALS',
        primary_color=(196, 30, 58),
        secondary_color=(12, 35, 64),
        logo_path='./logos/STL.png',
        marquee_path='./cardinals_marquee.png',
        celebration_path='./cards_win.gif',
        facts_basename='cardinals_facts.json',
        history_basename='cardinals_history.json',
        news_rss_url='https://www.mlb.com/cardinals/feeds/news/rss.xml',
    ),
}


def get_active_team(config: dict | None = None) -> TeamPack:
    """Resolve the active team pack from config (or the user config file)"""
    if config is None:
        config = load_user_config()
    slug = config.get('team', DEFAULT_TEAM_SLUG)
    return TEAMS.get(slug, TEAMS[DEFAULT_TEAM_SLUG])


def apply_team_defaults(defaults: dict, user_config: dict) -> dict:
    """Return a copy of defaults adjusted for the active team.

    Chicago-specific content defaults to off for non-Cubs teams, but an
    explicit user setting always wins.
    """
    adjusted = dict(defaults)
    if user_config.get('team', DEFAULT_TEAM_SLUG) != DEFAULT_TEAM_SLUG:
        for key in NON_DEFAULT_OFF_KEYS:
            if key not in user_config:
                adjusted[key] = False
    return adjusted


def data_path_candidates(basename: str) -> list[str]:
    """Lookup locations for team data files, repo dir first then Pi home"""
    return [f'./{basename}', f'/home/pi/{basename}']

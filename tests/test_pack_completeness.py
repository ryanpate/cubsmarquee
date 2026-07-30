"""Every path a team pack references must exist in the repo"""

import os

import pytest
from PIL import Image

from teams import TEAMS, NFL_TEAMS


@pytest.mark.parametrize('slug', sorted(TEAMS))
def test_all_pack_paths_exist(slug):
    pack = TEAMS[slug]
    for path in (pack.logo_path, pack.marquee_path, pack.celebration_path,
                 f'./{pack.facts_basename}', f'./{pack.history_basename}'):
        assert os.path.exists(path), f'{slug}: missing {path}'


@pytest.mark.parametrize('slug', sorted(TEAMS))
def test_celebration_gif_is_animated(slug):
    gif = Image.open(TEAMS[slug].celebration_path)
    assert getattr(gif, 'n_frames', 1) > 1
    assert gif.info.get('duration', 0) > 0


# ESPN competitor abbreviations for all 32 NFL teams (uppercase of the
# CDN slug used by dev/fetch_nfl_logos.py)
NFL_ABBREVS = [
    'ARI', 'ATL', 'BAL', 'BUF', 'CAR', 'CHI', 'CIN', 'CLE',
    'DAL', 'DEN', 'DET', 'GB', 'HOU', 'IND', 'JAX', 'KC',
    'LAC', 'LAR', 'LV', 'MIA', 'MIN', 'NE', 'NO', 'NYG',
    'NYJ', 'PHI', 'PIT', 'SEA', 'SF', 'TB', 'TEN', 'WSH',
]


class TestNflLogos:
    def test_all_32_logos_exist_and_open(self):
        for abbrev in NFL_ABBREVS:
            path = f'./logos/nfl/{abbrev}.png'
            assert os.path.exists(path), f'missing {path}'
            with Image.open(path) as img:
                assert img.size == (20, 20), f'{path} is {img.size}'
                assert img.mode == 'RGBA', f'{path} is {img.mode}'

    def test_pack_logo_paths_exist(self):
        for pack in NFL_TEAMS.values():
            assert os.path.exists(pack.logo_path)
            assert pack.abbrev in {
                os.path.splitext(f)[0] for f in os.listdir('./logos/nfl')}


class TestOpponentLogos:
    def test_every_pack_team_has_an_opponent_logo(self):
        """Any pack team can appear as the OTHER board's opponent, which is
        looked up by abbreviation at logos/{abbrev}.png (see
        scoreboard_manager.load_game_images)."""
        from teams import TEAMS
        for pack in TEAMS.values():
            path = f'./logos/{pack.abbrev}.png'
            assert os.path.exists(path), (
                f'{pack.slug} has no opponent logo at {path}')

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


class TestRunScoredSprites:
    def test_every_pack_has_a_run_scored_sprite(self):
        from teams import TEAMS
        for pack in TEAMS.values():
            assert os.path.exists(pack.run_scored_path), (
                f'{pack.slug} missing run sprite at {pack.run_scored_path}')
            with Image.open(pack.run_scored_path) as img:
                assert img.size == (21, 24), f'{pack.run_scored_path} is {img.size}'
                assert img.mode == 'RGBA'


class TestNflCelebrationGifs:
    def test_all_pack_gifs_exist_and_animate(self):
        from teams import NFL_TEAMS
        for pack in NFL_TEAMS.values():
            assert os.path.exists(pack.celebration_path), (
                f'{pack.slug} missing win GIF at {pack.celebration_path}')
            with Image.open(pack.celebration_path) as gif:
                assert gif.size == (96, 48)
                frames = 1
                try:
                    while True:
                        gif.seek(gif.tell() + 1)
                        frames += 1
                except EOFError:
                    pass
                assert frames >= 2, f'{pack.celebration_path} is not animated'

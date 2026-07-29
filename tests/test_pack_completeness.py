"""Every path a team pack references must exist in the repo"""

import os

import pytest
from PIL import Image

from teams import TEAMS


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

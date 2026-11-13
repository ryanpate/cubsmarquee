#!/usr/bin/env python3
"""Render one PNG frame of each college basketball screen for review.

Runs headless: rgbmatrix is mocked exactly like tests/conftest.py, and
frames are captured from ScoreboardManager's PIL preview mirror. Data is
the recorded ESPN payloads in tests/data, so no network is needed.

Usage (from repo root): python3 tools/render_ncaab_previews.py
Output: ncaab_previews/<screen>.png plus 8x nearest-neighbor upscales.
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)  # code uses relative ./fonts and ./logos paths

sys.modules['rgbmatrix'] = MagicMock()
sys.modules['rgbmatrix.graphics'] = MagicMock()

from PIL import Image  # noqa: E402

OUT_DIR = os.path.join(REPO_ROOT, 'ncaab_previews')


def _fixture(name: str) -> dict:
    with open(os.path.join(REPO_ROOT, 'tests', 'data', name)) as f:
        return json.load(f)


def _save(manager, name: str) -> None:
    frame = manager.get_frame_copy()
    frame.save(os.path.join(OUT_DIR, f'{name}.png'))
    frame.resize((96 * 8, 48 * 8), Image.NEAREST).save(
        os.path.join(OUT_DIR, f'{name}@8x.png'))
    print(f'  wrote {name}.png')


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    import ncaab_display as nd
    from scoreboard_manager import ScoreboardManager

    manager = ScoreboardManager()
    d = nd.CollegeBasketballDisplay(manager)
    d.schedule = _fixture('ncaab_schedule.json')
    team_id = d.team.espn_team_id
    rankings = nd.parse_rankings(_fixture('ncaab_rankings.json'), team_id)
    standings = nd.parse_standings(_fixture('ncaab_standings.json'), team_id)
    events = d.schedule['events']
    ranked_road_game = next(e for e in events if 'DUKE' in e['shortName'])

    def shot(name: str, draw, header: bool = True) -> None:
        manager.clear_canvas()
        if header:
            d._draw_header()
        draw()
        _save(manager, name)

    shot('next_game', lambda: d._draw_matchup_card(ranked_road_game, 0))
    shot('next_game_countdown',
         lambda: d._draw_matchup_card(ranked_road_game, 8))

    live = {
        'status': 'STATUS_IN_PROGRESS', 'state': 'in',
        'detail': '7:42 - 2ND HALF', 'team_score': '68', 'opp_score': '61',
        'opp_abbr': 'DUKE', 'opp_id': '150',
        'team_stats': {'fieldGoalPct': '48.2', 'rebounds': '31'},
        'opp_stats': {'fieldGoalPct': '44.0', 'rebounds': '27'},
    }
    shot('live', lambda: d._draw_live_content(live, 0))
    shot('live_stats', lambda: d._draw_live_content(live, 16))
    shot('live_100', lambda: d._draw_live_content(
        dict(live, team_score='104', opp_score='99', detail='0:42 - OT'), 0))

    final = dict(live, status='STATUS_FINAL', state='post', detail='FINAL',
                 team_score='84', opp_score='78',
                 team_lines=['39', '45'], opp_lines=['41', '37'])
    shot('final_win', lambda: d._draw_final_content(final, 0))
    shot('final_ot_loss', lambda: d._draw_final_content(
        dict(final, team_score='88', opp_score='91',
             team_lines=['39', '40', '9'], opp_lines=['41', '38', '12']), 0))

    shot('rank_card', lambda: d._draw_rank_card(rankings, 3))
    for page in range(nd.page_count(len(rankings['rows']))):
        shot(f'top25_page{page + 1}',
             lambda: d._draw_rankings_page(rankings, page, 5), header=False)
    for page in range(nd.page_count(len(standings))):
        shot(f'standings_page{page + 1}',
             lambda: d._draw_standings_page(standings, page), header=False)

    shot('news', lambda: manager.draw_text(
        'medium_bold', 6, 38, d.TEXT_WHITE, 'ILLINI NEWS - SAM HOUSTON'))
    print(f'Done. Previews in {OUT_DIR}')


if __name__ == '__main__':
    main()

"""Drive the NFL screens on the real matrix for a given team pack.

Usage (on the Pi, with cubs-scoreboard stopped):
    sudo python3 dev/nfl_screens_demo.py [slug]

Cycles: live game (fake data, both logo sides), red-zone blink,
scoring celebrations, final/WIN screen, next-game card (real ESPN
schedule), breaking news (real RSS). Reboot afterward to restore the
normal display.
"""

import os
import sys
import time

sys.path.insert(0, '.')

# Under sudo, HOME points at root, hiding the invoking user's pip
# --user packages (feedparser etc.) - add them back explicitly.
sudo_user = os.environ.get('SUDO_USER')
if sudo_user:
    sys.path.append(
        f'/home/{sudo_user}/.local/lib/'
        f'python{sys.version_info.major}.{sys.version_info.minor}/site-packages')

import teams
from scoreboard_config import load_user_config as _real_load

SLUG = sys.argv[1] if len(sys.argv) > 1 else 'chiefs'
teams.load_user_config = lambda: {**_real_load(), 'nfl_team': SLUG}

from scoreboard_manager import ScoreboardManager  # noqa: E402
from bears_display import BearsDisplay  # noqa: E402

manager = ScoreboardManager()
display = BearsDisplay(manager)
print(f'Demo pack: {display.nfl_team.name}')


def show(title, seconds, frame_fn):
    print(f'--- {title} ({seconds}s)')
    start = time.time()
    frame = 0
    while time.time() - start < seconds:
        manager.clear_canvas()
        display._draw_sweater_header()
        frame_fn(frame)
        manager.swap_canvas()
        frame += 1
        time.sleep(0.5)


live = {
    'status': 'STATUS_IN_PROGRESS', 'game_time': 'Q3 8:42',
    'bears_score': '21', 'opp_score': '17',
    'opponent_abbr': 'LV', 'opponent_name': 'Las Vegas Raiders',
    'possession': 'team', 'down_distance': '3RD & 4 KC 35',
    'is_red_zone': False, 'last_play': None,
}
show('Live game', 10, lambda f: display._draw_live_content(live, f))

red_zone = dict(live, is_red_zone=True, down_distance='1ST & GOAL LV 8',
                possession='opponent')
show('Red-zone blink', 8, lambda f: display._draw_live_content(red_zone, f))

print('--- Touchdown celebration')
display._play_scoring_celebration(7)
print('--- Generic score celebration')
display._play_scoring_celebration(1)

final = dict(live, status='STATUS_FINAL', bears_score='27', opp_score='24',
             opponent_abbr='DEN')
show('Final / WIN screen', 10, lambda f: display._draw_final_content(final, f))

print('--- Next-game card (real ESPN schedule)')
try:
    display.display_bears_info(duration=20)
except Exception as e:
    print(f'next-game card failed: {e}')

print('--- Breaking news (real RSS)')
try:
    from off_season_handler import OffSeasonHandler
    handler = OffSeasonHandler(manager)
    handler.display_bears_news(duration=30)
except Exception as e:
    print(f'news screen failed: {e}')

manager.clear_canvas()
manager.swap_canvas()
print('Demo done - reboot to restore the scoreboard.')

"""Drive the flight display on the real matrix for quick visual review.

Usage (on the Pi, with cubs-scoreboard stopped):
    sudo python3 dev/flight_demo.py [minutes]

Runs the real flight rotation (live ADS-B data) for the given number of
minutes (default 10). Reboot afterward to restore the normal display.
"""

import os
import sys

sys.path.insert(0, '.')

# Under sudo, HOME points at root, hiding the invoking user's pip
# --user packages - add them back explicitly.
sudo_user = os.environ.get('SUDO_USER')
if sudo_user:
    sys.path.append(
        f'/home/{sudo_user}/.local/lib/'
        f'python{sys.version_info.major}.{sys.version_info.minor}/site-packages')

from scoreboard_manager import ScoreboardManager  # noqa: E402
# Import BEFORE the matrix exists: rgbmatrix drops the process from root
# to 'daemon' at init, and pi's 0700 site-packages is untraversable after
# the drop. main.py orders it the same way.
from flight_display import FlightDisplay  # noqa: E402

MINUTES = int(sys.argv[1]) if len(sys.argv) > 1 else 10

manager = ScoreboardManager()
display = FlightDisplay(manager)
print(f'Flight demo for {MINUTES} minute(s) - Ctrl-C to stop')
try:
    display.display_flight_info(duration=MINUTES * 60)
finally:
    manager.clear_canvas()
    manager.swap_canvas()

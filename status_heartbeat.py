"""Heartbeat file: what the scoreboard is showing, read by the admin panel"""

from __future__ import annotations

import json
import time

STATUS_FILE = '/var/tmp/scoreboard_status.json'


def write_status_heartbeat(state: str, detail: str = '') -> None:
    """Record what the scoreboard is currently showing (best-effort)"""
    try:
        with open(STATUS_FILE, 'w') as f:
            json.dump({
                'timestamp': time.time(),
                'state': state,
                'detail': detail,
            }, f)
    except OSError:
        pass  # status reporting must never break the display

"""Setup-mode display: shows on-matrix instructions until first-time configuration is complete."""
from __future__ import annotations

import os
import subprocess

CONFIG_PATH = "/home/pi/config.json"


def needs_setup() -> bool:
    """Return True if the unit has not yet been configured.

    A unit needs setup when either the user config file is missing,
    or the Pi is not currently associated with a WiFi network.
    """
    if not os.path.exists(CONFIG_PATH):
        return True
    try:
        result = subprocess.run(
            ["iwgetid", "-r"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return not result.stdout.strip()
    except Exception:
        return True

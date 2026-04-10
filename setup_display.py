"""Setup-mode display: shows on-matrix instructions until first-time configuration is complete."""
from __future__ import annotations

import os
import subprocess
import time
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont

from logger import get_logger
from scoreboard_config import Colors, DisplayConfig

if TYPE_CHECKING:
    from scoreboard_manager import ScoreboardManager


logger = get_logger("setup_display")

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
        return result.returncode != 0 or not result.stdout.strip()
    except Exception as e:
        logger.warning("iwgetid check failed, assuming setup needed: %s", e)
        return True


def is_shutdown_requested() -> bool:
    """Lazy import to avoid circular dependency with main.py."""
    try:
        from main import is_shutdown_requested as _check
        return _check()
    except Exception:
        return False


SETUP_MESSAGE = "Connect phone to WiFi: CubsMarquee-Setup    Open: cubsmarquee.local/admin"
HEADER_TEXT = "SETUP"


class SetupDisplay:
    """Shows scrolling setup instructions on the LED matrix until WiFi and config are present."""

    def __init__(self, manager: "ScoreboardManager", poll_interval: float = 10.0) -> None:
        self.manager = manager
        self.poll_interval = poll_interval
        self.scroll_x: int = DisplayConfig.MATRIX_COLS
        try:
            self.font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 8
            )
        except Exception:
            self.font = ImageFont.load_default()

    def _render_frame(self) -> Image.Image:
        img = Image.new("RGB", (DisplayConfig.MATRIX_COLS, DisplayConfig.MATRIX_ROWS), Colors.BLACK)
        draw = ImageDraw.Draw(img)

        draw.rectangle([(0, 0), (DisplayConfig.MATRIX_COLS - 1, 9)], fill=Colors.CUBS_BLUE)
        bbox = draw.textbbox((0, 0), HEADER_TEXT, font=self.font)
        text_w = bbox[2] - bbox[0]
        draw.text(
            ((DisplayConfig.MATRIX_COLS - text_w) // 2, 0),
            HEADER_TEXT,
            font=self.font,
            fill=Colors.YELLOW,
        )

        draw.text((self.scroll_x, 18), SETUP_MESSAGE, font=self.font, fill=Colors.YELLOW)
        bbox = draw.textbbox((0, 0), SETUP_MESSAGE, font=self.font)
        msg_w = bbox[2] - bbox[0]

        self.scroll_x -= 1
        if self.scroll_x < -msg_w:
            self.scroll_x = DisplayConfig.MATRIX_COLS

        return img

    def run_until_configured(self) -> None:
        """Block until both config.json exists and WiFi is connected, then return."""
        logger.info("Entering setup display mode")
        last_check = 0.0
        while True:
            if is_shutdown_requested():
                logger.info("Shutdown requested during setup display")
                return

            now = time.time()
            if now - last_check >= self.poll_interval:
                if not needs_setup():
                    logger.info("Setup complete - exiting setup display")
                    return
                last_check = now

            img = self._render_frame()
            self.manager.canvas.SetImage(img)
            self.manager.canvas = self.manager.matrix.SwapOnVSync(self.manager.canvas)
            time.sleep(0.03)

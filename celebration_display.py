"""Celebration days - birthdays and holidays take over the marquee"""

from __future__ import annotations

import time
import pendulum
from PIL import Image
from typing import TYPE_CHECKING, Any

from scoreboard_config import Colors, DisplayConfig, load_user_config

if TYPE_CHECKING:
    from scoreboard_manager import ScoreboardManager

NIGHT_BLUE = (12, 18, 48)
CONFETTI_COLORS = [
    (255, 90, 90), (255, 210, 60), (90, 200, 255),
    (120, 230, 120), (240, 130, 240), (255, 160, 60),
]


class CelebrationDisplay:
    """Confetti and a message on configured special days"""

    def __init__(self, scoreboard_manager: ScoreboardManager) -> None:
        self.manager = scoreboard_manager

    @staticmethod
    def _todays_celebrations(
        config: dict[str, Any], today: pendulum.DateTime
    ) -> list[dict[str, Any]]:
        """Entries from config whose MM-DD date matches today"""
        key = today.format('MM-DD')
        matches = []
        for entry in config.get('celebrations', []):
            if isinstance(entry, dict) and entry.get('date') == key \
                    and entry.get('name'):
                matches.append(entry)
        return matches

    @staticmethod
    def _message_for(entry: dict[str, Any]) -> str:
        kind = entry.get('type', 'birthday')
        name = entry.get('name', '')
        if kind == 'holiday':
            return f'HAPPY {name}!'
        return f'HAPPY {kind.upper()} {name}!'

    def _draw_confetti(self, tick: float) -> None:
        """Deterministic falling confetti, two pixels per piece"""
        for i in range(30):
            speed = 6 + (i * 7) % 9
            x = (i * 29 + 13) % DisplayConfig.MATRIX_COLS
            y = int(i * 11 + tick * speed) % DisplayConfig.MATRIX_ROWS
            color = CONFETTI_COLORS[i % len(CONFETTI_COLORS)]
            self.manager.draw_pixel(x, y, *color)
            self.manager.draw_pixel(
                x, (y + 1) % DisplayConfig.MATRIX_ROWS, *color)

    def _draw_celebration_frame(
        self, entry: dict[str, Any], tick: float | None = None
    ) -> None:
        if tick is None:
            tick = time.time()
        self.manager.clear_canvas()
        background = Image.new(
            'RGB', (DisplayConfig.MATRIX_COLS, DisplayConfig.MATRIX_ROWS),
            NIGHT_BLUE)
        self.manager.set_image(background, 0, 0)

        self._draw_confetti(tick)

        kind = entry.get('type', 'birthday')
        first = 'HAPPY'
        second = kind.upper() if kind != 'holiday' else ''
        name = f"{entry.get('name', '')}!"
        lines = [line for line in (first, second, name) if line]
        baselines = {1: (30,), 2: (22, 38), 3: (17, 29, 43)}[len(lines)]
        for line, baseline in zip(lines, baselines):
            width = len(line) * 6
            x = max(0, (DisplayConfig.MATRIX_COLS - width) // 2)
            color = Colors.YELLOW if line == name else Colors.WHITE
            self.manager.draw_text('small_bold', x, baseline, color, line)

        self.manager.swap_canvas()

    def display_celebrations(self, duration: int = 120) -> bool:
        """Show today's celebrations; False when there are none"""
        celebrations = self._todays_celebrations(
            load_user_config(), pendulum.now('America/Chicago'))
        if not celebrations:
            return False

        print(f"Displaying celebrations: "
              f"{[c['name'] for c in celebrations]}")
        per_entry = max(15, duration // len(celebrations))
        start = time.time()
        for entry in celebrations:
            entry_start = time.time()
            while (time.time() - entry_start < per_entry
                   and time.time() - start < duration):
                self._draw_celebration_frame(entry)
                time.sleep(0.15)  # keep the confetti falling smoothly
        return True

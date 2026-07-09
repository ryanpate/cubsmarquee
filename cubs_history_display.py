"""Today in Cubs history - date-keyed moments from franchise history"""

from __future__ import annotations

import json
import time
import pendulum
from PIL import Image
from typing import TYPE_CHECKING, Any

from scoreboard_config import Colors, DisplayConfig

if TYPE_CHECKING:
    from scoreboard_manager import ScoreboardManager

HISTORY_PATHS = ['./cubs_history.json', '/home/pi/cubs_history.json']
SEPIA_BG = (32, 22, 10)
SEPIA_BAND = (168, 124, 48)
SEPIA_TEXT = (235, 215, 170)


class CubsHistoryDisplay:
    """Shows what happened on today's date in Cubs history"""

    def __init__(self, scoreboard_manager: ScoreboardManager) -> None:
        self.manager = scoreboard_manager
        self.history: dict[str, list[dict[str, Any]]] = self._load_history()

    @staticmethod
    def _load_history() -> dict[str, list[dict[str, Any]]]:
        for path in HISTORY_PATHS:
            try:
                with open(path) as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
        print("cubs_history.json not found")
        return {}

    def _entries_for(self, month: int, day: int) -> list[dict[str, Any]]:
        return self.history.get(f'{month:02d}-{day:02d}', [])

    @staticmethod
    def _wrap(text: str, width: int) -> list[str]:
        """Wrap text into lines of at most width characters"""
        lines: list[str] = []
        current = ''
        for word in text.split():
            candidate = f'{current} {word}'.strip()
            if len(candidate) <= width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    def _draw_entry_frame(self, entry: dict[str, Any]) -> None:
        """Vintage gold-on-sepia card for one historical moment"""
        self.manager.clear_canvas()
        background = Image.new(
            'RGB', (DisplayConfig.MATRIX_COLS, DisplayConfig.MATRIX_ROWS),
            SEPIA_BG)
        self.manager.set_image(background, 0, 0)

        # Gold band with the screen title
        for y in range(0, 9):
            for x in range(DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, y, *SEPIA_BAND)
        title = 'CUBS HISTORY'
        title_x = (DisplayConfig.MATRIX_COLS - len(title) * 4) // 2
        self.manager.draw_text('micro', title_x, 7, SEPIA_BG, title)

        # The year, big, with the story wrapped beneath
        year = str(entry.get('year', ''))
        year_x = (DisplayConfig.MATRIX_COLS - len(year) * 6) // 2
        self.manager.draw_text(
            'small_bold', year_x, 18, Colors.YELLOW, year)

        lines = self._wrap(entry.get('text', ''), 23)[:4]
        for line, baseline in zip(lines, (26, 33, 40, 47)):
            line_x = (DisplayConfig.MATRIX_COLS - len(line) * 4) // 2
            self.manager.draw_text(
                'micro', max(0, line_x), baseline, SEPIA_TEXT, line)

        self.manager.swap_canvas()

    def display_history(self, duration: int = 120) -> bool:
        """Show today's entries; False when there is nothing for this date"""
        now = pendulum.now('America/Chicago')
        entries = self._entries_for(now.month, now.day)
        if not entries:
            print(f"No Cubs history entry for {now.format('MM-DD')}")
            return False

        print(f"Displaying Cubs history for {now.format('MM-DD')}")
        per_entry = max(20, duration // len(entries))
        start = time.time()
        for entry in entries:
            if time.time() - start >= duration:
                break
            self._draw_entry_frame(entry)
            time.sleep(min(per_entry, max(1, duration - (time.time() - start))))
        return True

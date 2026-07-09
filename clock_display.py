"""Wrigley Field marquee clock - analog face with the date alongside"""

from __future__ import annotations

import math
import time
import pendulum
from PIL import Image
from typing import TYPE_CHECKING

from scoreboard_config import Colors, DisplayConfig

if TYPE_CHECKING:
    from scoreboard_manager import ScoreboardManager

MARQUEE_RED = (196, 30, 58)
FACE_GREEN = (14, 60, 40)   # scoreboard green behind the clock face
HAND_WHITE = (235, 235, 235)
SECOND_RED = (255, 90, 90)
TICK_GRAY = (150, 160, 150)


class WrigleyClockDisplay:
    """The centerfield scoreboard clock, marquee style"""

    def __init__(self, scoreboard_manager: ScoreboardManager) -> None:
        self.manager = scoreboard_manager

    @staticmethod
    def _hand_angles(hour: int, minute: int, second: int) -> tuple[float, float, float]:
        """Clock hand bearings in degrees (0 = twelve o'clock)"""
        hour_deg = ((hour % 12) + minute / 60) * 30.0
        minute_deg = minute * 6.0
        second_deg = second * 6.0
        return (hour_deg, minute_deg, second_deg)

    def _draw_hand(
        self, cx: int, cy: int, angle_deg: float, length: int,
        color: tuple[int, int, int]
    ) -> None:
        rad = math.radians(angle_deg)
        for r in range(1, length + 1):
            x = cx + round(r * math.sin(rad))
            y = cy - round(r * math.cos(rad))
            self.manager.draw_pixel(x, y, *color)

    def _draw_clock_frame(self, now: pendulum.DateTime | None = None) -> None:
        """Red marquee band, analog face on the left, date/time right"""
        if now is None:
            now = pendulum.now('America/Chicago')
        self.manager.clear_canvas()

        background = Image.new(
            'RGB', (DisplayConfig.MATRIX_COLS, DisplayConfig.MATRIX_ROWS),
            FACE_GREEN)
        self.manager.set_image(background, 0, 0)

        # Wrigley marquee header
        for y in range(0, 11):
            for x in range(DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, y, *MARQUEE_RED)
        title = 'WRIGLEY FIELD'
        title_x = max(0, (DisplayConfig.MATRIX_COLS - len(title) * 6) // 2)
        self.manager.draw_text('small_bold', title_x, 10, Colors.WHITE, title)

        # Analog face
        cx, cy, radius = 24, 29, 15
        for angle in range(0, 360, 3):
            rad = math.radians(angle)
            self.manager.draw_pixel(
                cx + round(radius * math.sin(rad)),
                cy - round(radius * math.cos(rad)), *HAND_WHITE)
        for hour_mark in range(12):  # hour ticks just inside the ring
            rad = math.radians(hour_mark * 30)
            self.manager.draw_pixel(
                cx + round((radius - 2) * math.sin(rad)),
                cy - round((radius - 2) * math.cos(rad)), *TICK_GRAY)

        hour_deg, minute_deg, second_deg = self._hand_angles(
            now.hour, now.minute, now.second)
        self._draw_hand(cx, cy, hour_deg, 7, HAND_WHITE)
        self._draw_hand(cx, cy, minute_deg, 11, HAND_WHITE)
        self._draw_hand(cx, cy, second_deg, 12, SECOND_RED)
        self.manager.draw_pixel(cx, cy, *Colors.YELLOW)

        # Digital time and date on the right
        time_str = now.format('h:mm')
        ampm = now.format('A')
        time_x = 68 - len(time_str) * 6 // 2 - 6
        self.manager.draw_text(
            'small_bold', time_x, 25, Colors.YELLOW, time_str)
        self.manager.draw_text(
            'micro', 68 - 4, 32, TICK_GRAY, ampm)
        date_str = now.format('ddd MMM D').upper()
        date_x = 68 - len(date_str) * 4 // 2
        self.manager.draw_text(
            'micro', max(44, date_x), 42, Colors.WHITE, date_str)

        self.manager.swap_canvas()

    def display_clock(self, duration: int = 60) -> None:
        """Show the clock for the given duration"""
        print("Displaying Wrigley clock...")
        start = time.time()
        while time.time() - start < duration:
            self._draw_clock_frame()
            time.sleep(1)

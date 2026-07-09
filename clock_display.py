"""Wrigley clock - the top of the centerfield scoreboard against a live sky"""

from __future__ import annotations

import math
import time
import pendulum
from PIL import Image
from typing import TYPE_CHECKING

from scoreboard_config import Colors, DisplayConfig

if TYPE_CHECKING:
    from scoreboard_manager import ScoreboardManager
    from weather_display import WeatherDisplay

BOARD_GREEN = (18, 52, 38)
BOARD_EDGE = (58, 105, 78)
FACE_WHITE = (235, 235, 222)
HAND_GREEN = (18, 52, 38)
SECOND_RED = (200, 50, 50)
PENNANT_BLUE = (40, 95, 180)

TWILIGHT_SECONDS = 1800  # dawn/dusk window around sunrise/sunset

SKY_GRADIENTS = {
    ('day', 'clear'): ((70, 140, 215), (150, 200, 235)),
    ('day', 'clouds'): ((105, 118, 138), (165, 172, 182)),
    ('day', 'rain'): ((70, 80, 95), (120, 128, 140)),
    ('day', 'snow'): ((150, 155, 170), (205, 208, 218)),
    ('dawn', None): ((95, 70, 135), (245, 150, 85)),
    ('dusk', None): ((60, 45, 110), (235, 120, 70)),
    ('night', 'clear'): ((5, 9, 26), (18, 28, 58)),
    ('night', None): ((16, 18, 28), (34, 38, 52)),
}


class WrigleyClockDisplay:
    """The centerfield scoreboard clock under the actual sky"""

    def __init__(
        self, scoreboard_manager: ScoreboardManager,
        weather_display: WeatherDisplay | None = None
    ) -> None:
        self.manager = scoreboard_manager
        self.weather_display = weather_display

    @staticmethod
    def _hand_angles(hour: int, minute: int, second: int) -> tuple[float, float, float]:
        """Clock hand bearings in degrees (0 = twelve o'clock)"""
        hour_deg = ((hour % 12) + minute / 60) * 30.0
        minute_deg = minute * 6.0
        second_deg = second * 6.0
        return (hour_deg, minute_deg, second_deg)

    @staticmethod
    def _sky_phase(
        now_ts: float, sunrise_ts: float | None, sunset_ts: float | None
    ) -> str:
        """'dawn' / 'day' / 'dusk' / 'night' for the current moment"""
        if not sunrise_ts or not sunset_ts:
            hour = pendulum.from_timestamp(now_ts, tz='America/Chicago').hour
            if 6 <= hour < 8:
                return 'dawn'
            if 8 <= hour < 19:
                return 'day'
            if 19 <= hour < 21:
                return 'dusk'
            return 'night'
        if abs(now_ts - sunrise_ts) <= TWILIGHT_SECONDS:
            return 'dawn'
        if abs(now_ts - sunset_ts) <= TWILIGHT_SECONDS:
            return 'dusk'
        if sunrise_ts < now_ts < sunset_ts:
            return 'day'
        return 'night'

    @staticmethod
    def _condition_group(condition: str) -> str:
        if condition in ('Rain', 'Drizzle', 'Thunderstorm'):
            return 'rain'
        if condition == 'Snow':
            return 'snow'
        if condition in ('Clouds', 'Mist', 'Fog', 'Haze', 'Smoke'):
            return 'clouds'
        return 'clear'

    @classmethod
    def _sky_colors(
        cls, phase: str, condition: str
    ) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
        """(zenith, horizon) gradient for this phase and weather"""
        group = cls._condition_group(condition)
        for key in ((phase, group), (phase, None)):
            if key in SKY_GRADIENTS:
                return SKY_GRADIENTS[key]
        return SKY_GRADIENTS[('day', 'clear')]

    def _current_weather(self) -> tuple[str, float | None, float | None]:
        """(condition, sunrise_ts, sunset_ts) from the cached weather data"""
        data = getattr(self.weather_display, 'weather_data', None) or {}
        try:
            condition = data['weather'][0]['main']
        except (KeyError, IndexError, TypeError):
            condition = 'Clear'
        sys_data = data.get('sys', {})
        return (condition, sys_data.get('sunrise'), sys_data.get('sunset'))

    def _draw_sky(self, phase: str, condition: str) -> None:
        top, bottom = self._sky_colors(phase, condition)
        img = Image.new(
            'RGB', (DisplayConfig.MATRIX_COLS, DisplayConfig.MATRIX_ROWS))
        pixels = img.load()
        for y in range(DisplayConfig.MATRIX_ROWS):
            t = y / (DisplayConfig.MATRIX_ROWS - 1)
            color = tuple(int(a + (b - a) * t) for a, b in zip(top, bottom))
            for x in range(DisplayConfig.MATRIX_COLS):
                pixels[x, y] = color
        self.manager.set_image(img, 0, 0)

    def _draw_weather_effects(
        self, phase: str, condition: str, tick: float
    ) -> None:
        """Sun, stars, clouds, rain or snow layered over the sky"""
        group = self._condition_group(condition)

        if phase == 'night' and group == 'clear':
            for i in range(18):
                x = (i * 37 + 11) % DisplayConfig.MATRIX_COLS
                y = (i * 13 + 2) % 26
                level = 80 if (i + int(tick)) % 5 else 210
                self.manager.draw_pixel(x, y, level, level, level)
        elif phase == 'day' and group == 'clear':
            for dx in range(-3, 4):  # sun high in the sky
                for dy in range(-3, 4):
                    if dx * dx + dy * dy <= 9:
                        self.manager.draw_pixel(
                            80 + dx, 8 + dy, 255, 220, 90)
        elif phase in ('dawn', 'dusk') and group == 'clear':
            sun_x = 14 if phase == 'dawn' else 82
            for dx in range(-4, 5):  # sun sitting on the horizon
                for dy in range(-4, 1):
                    if dx * dx + dy * dy <= 16:
                        self.manager.draw_pixel(
                            sun_x + dx, 29 + dy, 255, 170, 70)

        if group in ('clouds', 'rain', 'snow'):
            cloud = (200, 205, 215) if group != 'rain' else (140, 148, 160)
            for i, (base_x, y, width) in enumerate(
                    ((6, 6, 14), (44, 11, 18), (74, 4, 12))):
                x0 = int(base_x + tick * (2 + i)) % 120 - 12
                for dx in range(width):
                    self.manager.draw_pixel(x0 + dx, y, *cloud)
                    if 2 <= dx < width - 2:
                        self.manager.draw_pixel(x0 + dx, y - 1, *cloud)
                        self.manager.draw_pixel(x0 + dx, y + 1, *cloud)

        if group == 'rain':
            for i in range(14):
                x = (i * 23 + 5) % DisplayConfig.MATRIX_COLS
                y = int(i * 9 + tick * 26) % 26 + 2
                self.manager.draw_pixel(x, y, 165, 190, 215)
                self.manager.draw_pixel(x, y + 1, 165, 190, 215)
        elif group == 'snow':
            for i in range(12):
                x = (i * 29 + 9 + int(tick * 2) % 3) % DisplayConfig.MATRIX_COLS
                y = int(i * 11 + tick * 8) % 26 + 2
                self.manager.draw_pixel(x, y, 240, 240, 245)

    def _draw_scoreboard(self, now: pendulum.DateTime, tick: float) -> None:
        """The green board, its clock housing, hands, and the pennant"""
        # Board mass across the bottom with a lit top edge
        for y in range(31, DisplayConfig.MATRIX_ROWS):
            for x in range(DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, y, *BOARD_GREEN)
        for x in range(DisplayConfig.MATRIX_COLS):
            self.manager.draw_pixel(x, 30, *BOARD_EDGE)

        # Clock housing rising above the board
        for y in range(5, 31):
            for x in range(34, 63):
                self.manager.draw_pixel(x, y, *BOARD_GREEN)
        for x in range(34, 63):  # housing border
            self.manager.draw_pixel(x, 5, *BOARD_EDGE)
        for y in range(5, 31):
            self.manager.draw_pixel(34, y, *BOARD_EDGE)
            self.manager.draw_pixel(62, y, *BOARD_EDGE)

        # Clock face
        cx, cy, radius = 48, 18, 11
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx * dx + dy * dy <= radius * radius:
                    self.manager.draw_pixel(cx + dx, cy + dy, *FACE_WHITE)
        for hour_mark in range(12):
            rad = math.radians(hour_mark * 30)
            self.manager.draw_pixel(
                cx + round((radius - 1) * math.sin(rad)),
                cy - round((radius - 1) * math.cos(rad)), *HAND_GREEN)

        hour_deg, minute_deg, second_deg = self._hand_angles(
            now.hour, now.minute, now.second)
        self._draw_hand(cx, cy, hour_deg, 5, HAND_GREEN)
        self._draw_hand(cx, cy, minute_deg, 8, HAND_GREEN)
        self._draw_hand(cx, cy, second_deg, 9, SECOND_RED)

        # Flagpole and a waving Cubs pennant
        for y in range(0, 5):
            self.manager.draw_pixel(48, y, 150, 150, 150)
        wave = int(tick * 2) % 2
        for dx in range(1, 6 - wave):
            for dy in range(0, 2 if dx < 4 else 1):
                self.manager.draw_pixel(48 + dx, 1 + dy + wave, *PENNANT_BLUE)

        # Date and time painted on the board
        date_top, date_bottom = now.format('ddd').upper(), now.format('MMM D').upper()
        self.manager.draw_text(
            'micro', 16 - len(date_top) * 2, 39, Colors.WHITE, date_top)
        self.manager.draw_text(
            'micro', 16 - len(date_bottom) * 2, 46, Colors.WHITE, date_bottom)
        time_str = now.format('h:mm')
        self.manager.draw_text(
            'tiny_bold', 79 - len(time_str) * 3, 40, Colors.YELLOW, time_str)
        ampm = now.format('A')
        self.manager.draw_text(
            'micro', 79 - len(ampm) * 2, 47, (180, 190, 180), ampm)

    def _draw_hand(
        self, cx: int, cy: int, angle_deg: float, length: int,
        color: tuple[int, int, int]
    ) -> None:
        rad = math.radians(angle_deg)
        for r in range(1, length + 1):
            x = cx + round(r * math.sin(rad))
            y = cy - round(r * math.cos(rad))
            self.manager.draw_pixel(x, y, *color)

    def _draw_clock_frame(
        self, now: pendulum.DateTime | None = None, tick: float | None = None
    ) -> None:
        if now is None:
            now = pendulum.now('America/Chicago')
        if tick is None:
            tick = time.time()

        condition, sunrise, sunset = self._current_weather()
        phase = self._sky_phase(now.timestamp(), sunrise, sunset)

        self.manager.clear_canvas()
        self._draw_sky(phase, condition)
        self._draw_weather_effects(phase, condition, tick)
        self._draw_scoreboard(now, tick)
        self.manager.swap_canvas()

    def display_clock(self, duration: int = 60) -> None:
        """Show the clock for the given duration"""
        print("Displaying Wrigley clock...")
        start = time.time()
        while time.time() - start < duration:
            self._draw_clock_frame()
            time.sleep(0.25)

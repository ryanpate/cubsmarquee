"""Wrigley clock - the full centerfield scoreboard against a live sky"""

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
OUTLINE_WHITE = (205, 210, 200)
FACE_WHITE = (235, 235, 222)
HAND_GREEN = (18, 52, 38)
SECOND_RED = (200, 50, 50)
NAME_WHITE = (150, 160, 148)
GRID_GREEN = (50, 86, 64)
SCORE_WHITE = (210, 216, 205)
RED_LINE = (180, 45, 45)

BOARD_TOP = 18  # first row of the board proper
CLOCK_CX, CLOCK_CY, CLOCK_R = 48, 10, 10

# Dash widths standing in for the painted team names (too small to letter)
NL_ROWS = (14, 12, 9, 13, 11, 12)  # six rows, then the red line, then CUBS
AL_ROWS = (10, 13, 12, 9, 11, 10, 12, 8, 11)

# A few lit "score" cells in each inning grid: (x, y) on the matrix
NL_SCORE_DOTS = ((24, 31), (28, 35), (32, 29), (36, 37), (24, 39))
AL_SCORE_DOTS = ((80, 29), (84, 33), (88, 31), (80, 41), (84, 45), (88, 39))

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
    """The centerfield scoreboard under the actual sky"""

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
        """Sun, stars, clouds, rain or snow in the sky band above the board"""
        group = self._condition_group(condition)

        if phase == 'night' and group == 'clear':
            for i in range(18):
                x = (i * 37 + 11) % DisplayConfig.MATRIX_COLS
                y = (i * 13 + 2) % 16
                level = 80 if (i + int(tick)) % 5 else 210
                self.manager.draw_pixel(x, y, level, level, level)
        elif phase == 'day' and group == 'clear':
            for dx in range(-3, 4):  # sun high in the sky
                for dy in range(-3, 4):
                    if dx * dx + dy * dy <= 9:
                        self.manager.draw_pixel(
                            80 + dx, 7 + dy, 255, 220, 90)
        elif phase in ('dawn', 'dusk') and group == 'clear':
            sun_x = 14 if phase == 'dawn' else 82
            for dx in range(-4, 5):  # sun sitting on the board's shoulder
                for dy in range(-4, 1):
                    if dx * dx + dy * dy <= 16:
                        self.manager.draw_pixel(
                            sun_x + dx, 17 + dy, 255, 170, 70)

        if group in ('clouds', 'rain', 'snow'):
            cloud = (200, 205, 215) if group != 'rain' else (140, 148, 160)
            for i, (base_x, y, width) in enumerate(
                    ((6, 5, 14), (44, 10, 18), (74, 3, 12))):
                x0 = int(base_x + tick * (2 + i)) % 120 - 12
                for dx in range(width):
                    self.manager.draw_pixel(x0 + dx, y, *cloud)
                    if 2 <= dx < width - 2:
                        self.manager.draw_pixel(x0 + dx, y - 1, *cloud)
                        self.manager.draw_pixel(x0 + dx, y + 1, *cloud)

        if group == 'rain':
            for i in range(14):
                x = (i * 23 + 5) % DisplayConfig.MATRIX_COLS
                y = int(i * 9 + tick * 26) % 14 + 2
                self.manager.draw_pixel(x, y, 165, 190, 215)
                self.manager.draw_pixel(x, y + 1, 165, 190, 215)
        elif group == 'snow':
            for i in range(12):
                x = (i * 29 + 9 + int(tick * 2) % 3) % DisplayConfig.MATRIX_COLS
                y = int(i * 11 + tick * 8) % 14 + 2
                self.manager.draw_pixel(x, y, 240, 240, 245)

    @staticmethod
    def _board_span(y: int) -> tuple[int, int]:
        """Left/right extent of the board at this row (beveled top corners)"""
        if y == 18:
            return (5, 90)
        if y == 19:
            return (4, 91)
        if y == 20:
            return (3, 92)
        return (1, 94)

    def _draw_board_shell(self) -> None:
        """The green board mass with its white outline"""
        for y in range(BOARD_TOP, DisplayConfig.MATRIX_ROWS):
            x0, x1 = self._board_span(y)
            for x in range(x0, x1 + 1):
                self.manager.draw_pixel(x, y, *BOARD_GREEN)
        for y in range(BOARD_TOP, DisplayConfig.MATRIX_ROWS):
            x0, x1 = self._board_span(y)
            self.manager.draw_pixel(x0, y, *OUTLINE_WHITE)
            self.manager.draw_pixel(x1, y, *OUTLINE_WHITE)
        for x in range(5, 91):  # top edge
            self.manager.draw_pixel(x, BOARD_TOP, *OUTLINE_WHITE)
        for x in range(1, 95):  # bottom edge
            self.manager.draw_pixel(x, 47, *OUTLINE_WHITE)

    def _draw_clock_housing(self, now: pendulum.DateTime) -> None:
        """The round clock rising from the top of the board"""
        for dy in range(-CLOCK_R, CLOCK_R + 1):
            y = CLOCK_CY + dy
            if y > BOARD_TOP:
                break  # below the top edge it merges into the board
            for dx in range(-CLOCK_R, CLOCK_R + 1):
                dist = math.sqrt(dx * dx + dy * dy)
                if round(dist) == CLOCK_R:
                    self.manager.draw_pixel(
                        CLOCK_CX + dx, y, *OUTLINE_WHITE)
                elif dist < CLOCK_R:
                    self.manager.draw_pixel(
                        CLOCK_CX + dx, y, *BOARD_GREEN)

        face_r = 7
        for dy in range(-face_r, face_r + 1):
            for dx in range(-face_r, face_r + 1):
                if dx * dx + dy * dy <= face_r * face_r:
                    self.manager.draw_pixel(
                        CLOCK_CX + dx, CLOCK_CY + dy, *FACE_WHITE)
        for hour_mark in range(12):
            rad = math.radians(hour_mark * 30)
            self.manager.draw_pixel(
                CLOCK_CX + round(6 * math.sin(rad)),
                CLOCK_CY - round(6 * math.cos(rad)), *HAND_GREEN)

        hour_deg, minute_deg, second_deg = self._hand_angles(
            now.hour, now.minute, now.second)
        self._draw_hand(CLOCK_CX, CLOCK_CY, hour_deg, 4, HAND_GREEN)
        self._draw_hand(CLOCK_CX, CLOCK_CY, minute_deg, 6, HAND_GREEN)
        self._draw_hand(CLOCK_CX, CLOCK_CY, second_deg, 6, SECOND_RED)

    def _draw_league_panels(self) -> None:
        """NATIONAL and AMERICAN team lists with their inning grids"""
        self.manager.draw_text(
            'ultra_micro', 5, 25, OUTLINE_WHITE, 'NATIONAL')
        self.manager.draw_text(
            'ultra_micro', 60, 25, OUTLINE_WHITE, 'AMERICAN')
        for x in range(4, 37):  # rules under the league headers
            self.manager.draw_pixel(x, 27, *GRID_GREEN)
        for x in range(60, 93):
            self.manager.draw_pixel(x, 27, *GRID_GREEN)

        # Inning grid columns on the right of each panel
        for grid_x in (22, 26, 30, 34):
            for y in range(28, 39):
                self.manager.draw_pixel(grid_x, y, *GRID_GREEN)
        for grid_x in (78, 82, 86, 90):
            for y in range(28, 47):
                self.manager.draw_pixel(grid_x, y, *GRID_GREEN)

        # Team name rows as painted dashes
        for i, width in enumerate(NL_ROWS):
            y = 29 + i * 2
            for x in range(4, 4 + width):
                self.manager.draw_pixel(x, y, *NAME_WHITE)
        for i, width in enumerate(AL_ROWS):
            y = 29 + i * 2
            for x in range(60, 60 + width):
                self.manager.draw_pixel(x, y, *NAME_WHITE)

        for x, y in NL_SCORE_DOTS:
            self.manager.draw_pixel(x, y, *SCORE_WHITE)
        for x, y in AL_SCORE_DOTS:
            self.manager.draw_pixel(x, y, *SCORE_WHITE)

        # The red stripe over the Cubs line, then the Cubs themselves
        for x in range(3, 38):
            self.manager.draw_pixel(x, 40, *RED_LINE)
        self.manager.draw_text('ultra_micro', 4, 47, Colors.YELLOW, 'CUBS')

    def _draw_center_column(self, now: pendulum.DateTime) -> None:
        """Time and date where the batter/count lamps live on the real board"""
        time_str = now.format('h:mm')
        x = 48 - (len(time_str) * 4 - 1) // 2
        self.manager.draw_text('ultra_micro', x, 34, Colors.YELLOW, time_str)
        date_str = now.format('MMM D').upper()
        x = 48 - (len(date_str) * 4 - 1) // 2
        self.manager.draw_text('ultra_micro', x, 42, NAME_WHITE, date_str)

        # The VIS / HITS / CUBS lamps as three yellow ticks
        for x0, x1 in ((39, 41), (44, 47), (50, 53)):
            for x in range(x0, x1 + 1):
                self.manager.draw_pixel(x, 45, *Colors.YELLOW)

    def _draw_scoreboard(self, now: pendulum.DateTime) -> None:
        """The full green board: shell, clock, league panels, center column"""
        self._draw_board_shell()
        self._draw_clock_housing(now)
        self._draw_league_panels()
        self._draw_center_column(now)

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
        self._draw_scoreboard(now)
        self.manager.swap_canvas()

    def display_clock(self, duration: int = 60) -> None:
        """Show the clock for the given duration"""
        print("Displaying Wrigley clock...")
        start = time.time()
        while time.time() - start < duration:
            self._draw_clock_frame()
            time.sleep(0.25)

"""Sun, moon and sky - sunrise/sunset arc by day, moon phase by night"""

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

# Reference new moon and mean lunar month for the phase calculation
NEW_MOON_EPOCH = pendulum.datetime(2000, 1, 6, 18, 14, tz='UTC')
SYNODIC_DAYS = 29.530588853

PHASE_NAMES = [
    'NEW MOON', 'WAXING CRESCENT', 'FIRST QUARTER', 'WAXING GIBBOUS',
    'FULL MOON', 'WANING GIBBOUS', 'LAST QUARTER', 'WANING CRESCENT',
]

DAY_SKY_TOP = (55, 110, 180)
DAY_SKY_BOTTOM = (150, 190, 230)
NIGHT_SKY_TOP = (4, 6, 20)
NIGHT_SKY_BOTTOM = (18, 24, 52)
SUN_YELLOW = (255, 210, 60)
ARC_GRAY = (120, 130, 150)
MOON_LIT = (225, 225, 210)
MOON_DARK = (45, 50, 70)


class SkyDisplay:
    """Shows where the sun is in its arc, or tonight's moon"""

    def __init__(
        self, scoreboard_manager: ScoreboardManager,
        weather_display: WeatherDisplay
    ) -> None:
        self.manager = scoreboard_manager
        self.weather_display = weather_display

    @staticmethod
    def _moon_phase(when: pendulum.DateTime) -> tuple[float, str]:
        """Moon phase as (cycle fraction, name); 0 = new, 0.5 = full"""
        days = (when - NEW_MOON_EPOCH).total_seconds() / 86400
        fraction = (days / SYNODIC_DAYS) % 1.0
        index = int((fraction * 8) + 0.5) % 8
        return (fraction, PHASE_NAMES[index])

    @staticmethod
    def _sun_fraction(
        now_ts: float, sunrise_ts: float, sunset_ts: float
    ) -> float | None:
        """Progress through daylight 0..1, or None outside daylight"""
        if sunset_ts <= sunrise_ts or not (sunrise_ts <= now_ts < sunset_ts):
            return None
        return (now_ts - sunrise_ts) / (sunset_ts - sunrise_ts)

    def _sun_times(self) -> tuple[float, float] | None:
        """Sunrise/sunset timestamps from the cached weather data"""
        data = self.weather_display.weather_data or {}
        sunrise = data.get('sys', {}).get('sunrise')
        sunset = data.get('sys', {}).get('sunset')
        if sunrise and sunset:
            return (float(sunrise), float(sunset))
        return None

    def _draw_gradient(self, top: tuple, bottom: tuple) -> None:
        img = Image.new(
            'RGB', (DisplayConfig.MATRIX_COLS, DisplayConfig.MATRIX_ROWS))
        pixels = img.load()
        for y in range(DisplayConfig.MATRIX_ROWS):
            t = y / (DisplayConfig.MATRIX_ROWS - 1)
            color = tuple(
                int(a + (b - a) * t) for a, b in zip(top, bottom))
            for x in range(DisplayConfig.MATRIX_COLS):
                pixels[x, y] = color
        self.manager.set_image(img, 0, 0)

    @staticmethod
    def _arc_point(fraction: float) -> tuple[int, int]:
        """Point along the sun's arc: horizon ends, apex mid-screen"""
        x = 8 + fraction * 80
        y = 38 - math.sin(fraction * math.pi) * 22
        return (int(x), int(y))

    def _draw_day_frame(
        self, fraction: float, sunrise: pendulum.DateTime,
        sunset: pendulum.DateTime
    ) -> None:
        """Sun climbing its arc between today's sunrise and sunset"""
        self.manager.clear_canvas()
        self._draw_gradient(DAY_SKY_TOP, DAY_SKY_BOTTOM)

        # Dotted arc from horizon to horizon
        for i in range(0, 41):
            ax, ay = self._arc_point(i / 40)
            if i % 2 == 0:
                self.manager.draw_pixel(ax, ay, *ARC_GRAY)
        # Horizon line
        for x in range(DisplayConfig.MATRIX_COLS):
            self.manager.draw_pixel(x, 39, 90, 120, 90)

        # The sun, with little rays
        sx, sy = self._arc_point(fraction)
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                if dx * dx + dy * dy <= 5:
                    self.manager.draw_pixel(sx + dx, sy + dy, *SUN_YELLOW)
        for dx, dy in ((-4, 0), (4, 0), (0, -4), (-3, -3), (3, -3)):
            self.manager.draw_pixel(sx + dx, sy + dy, 255, 235, 140)

        self.manager.draw_text(
            'micro', 2, 46, Colors.WHITE, sunrise.format('h:mmA'))
        sunset_str = sunset.format('h:mmA')
        self.manager.draw_text(
            'micro', 94 - len(sunset_str) * 4, 46, Colors.WHITE, sunset_str)
        title = 'SUN & SKY'
        self.manager.draw_text(
            'micro', (96 - len(title) * 4) // 2, 6, Colors.WHITE, title)
        self.manager.swap_canvas()

    def _draw_night_frame(
        self, phase_fraction: float, phase_name: str,
        sunrise: pendulum.DateTime | None, tick: float | None = None
    ) -> None:
        """Tonight's moon over a starfield"""
        if tick is None:
            tick = time.time()
        self.manager.clear_canvas()
        self._draw_gradient(NIGHT_SKY_TOP, NIGHT_SKY_BOTTOM)

        # Deterministic starfield with a slow twinkle
        for i in range(28):
            x = (i * 37 + 11) % DisplayConfig.MATRIX_COLS
            y = (i * 17 + 5) % 38
            level = 90 if (i + int(tick)) % 5 else 220
            self.manager.draw_pixel(x, y, level, level, level)

        # Moon: lit disc with a same-size shadow disc slid across it.
        # Waxing: shadow retreats to the left; waning: returns from the
        # right. Offset 0 = new moon (covered), +/-2r = full (clear).
        cx, cy, radius = 48, 22, 9
        if phase_fraction < 0.5:
            shadow_center = -4 * radius * phase_fraction
        else:
            shadow_center = 4 * radius * (1 - phase_fraction)
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx * dx + dy * dy > radius * radius:
                    continue
                sdx = dx - shadow_center
                in_shadow = sdx * sdx + dy * dy <= radius * radius
                color = MOON_DARK if in_shadow else MOON_LIT
                self.manager.draw_pixel(cx + dx, cy + dy, *color)

        title = 'TONIGHT'
        self.manager.draw_text(
            'micro', (96 - len(title) * 4) // 2, 6, ARC_GRAY, title)
        name_x = (96 - len(phase_name) * 4) // 2
        self.manager.draw_text(
            'micro', max(0, name_x), 40, Colors.WHITE, phase_name)
        if sunrise is not None:
            rise_str = f"SUNRISE {sunrise.format('h:mmA')}"
            rise_x = (96 - len(rise_str) * 4) // 2
            self.manager.draw_text(
                'micro', max(0, rise_x), 47, ARC_GRAY, rise_str)
        self.manager.swap_canvas()

    def display_sky(self, duration: int = 90) -> None:
        """Sun arc during the day, moon phase after dark"""
        times = self._sun_times()
        print("Displaying sun & sky...")
        start = time.time()
        while time.time() - start < duration:
            now = pendulum.now('America/Chicago')
            fraction = (self._sun_fraction(
                now.timestamp(), times[0], times[1]) if times else None)
            if fraction is not None:
                self._draw_day_frame(
                    fraction,
                    pendulum.from_timestamp(times[0], tz='America/Chicago'),
                    pendulum.from_timestamp(times[1], tz='America/Chicago'))
            else:
                phase_fraction, phase_name = self._moon_phase(now)
                sunrise = None
                if times:
                    sunrise = pendulum.from_timestamp(
                        times[0], tz='America/Chicago')
                self._draw_night_frame(phase_fraction, phase_name, sunrise)
            time.sleep(1)

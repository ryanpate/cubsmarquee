"""Sun, moon and sky - sunrise/sunset arc by day, moon phase by night"""

from __future__ import annotations

import math
import random
import time
import pendulum
from PIL import Image
from typing import TYPE_CHECKING, Any

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
# Golden-hour sky used near sunrise and sunset
LOW_SUN_SKY_TOP = (40, 55, 110)
LOW_SUN_SKY_BOTTOM = (235, 130, 55)
NIGHT_SKY_TOP = (4, 6, 20)
NIGHT_SKY_BOTTOM = (18, 24, 52)
SUN_YELLOW = (255, 210, 60)
SUN_TRAIL = (215, 165, 55)
ARC_GRAY = (120, 130, 150)
GRASS_TOP = (40, 105, 45)
GRASS_BOTTOM = (12, 45, 18)
MOON_LIT = (225, 225, 210)
MOON_DARK = (45, 50, 70)
MOON_CRATER = (185, 185, 168)
MOON_GLOW = (70, 80, 115)

# Crater spots on the lit face (offsets from moon center)
MOON_CRATERS = ((-3, -3), (2, -5), (4, 2), (-2, 4), (1, 0), (-5, 1))


class SkyDisplay:
    """Shows where the sun is in its arc, or tonight's moon"""

    def __init__(
        self, scoreboard_manager: ScoreboardManager,
        weather_display: WeatherDisplay
    ) -> None:
        self.manager = scoreboard_manager
        self.weather_display = weather_display
        self.clouds: list[dict[str, Any]] = []
        self.shooting_star: dict[str, Any] | None = None

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

    @staticmethod
    def _blend(a: tuple, b: tuple, t: float) -> tuple:
        """Linear blend between two RGB colors, t=0 -> a, t=1 -> b"""
        return tuple(int(ca + (cb - ca) * t) for ca, cb in zip(a, b))

    def _init_clouds(self) -> None:
        self.clouds = []
        for _ in range(2):
            self.clouds.append({
                'x': float(random.randint(0, 90)),
                'y': random.randint(4, 14),
                'width': random.randint(10, 16),
                'speed': random.uniform(0.08, 0.18),
            })

    def _draw_cloud(self, cloud: dict[str, Any]) -> None:
        """Small puffy cloud in the weather-screen style"""
        x_start = int(cloud['x'])
        y = cloud['y']
        width = cloud['width']
        for x_offset in range(width):
            x = x_start + x_offset
            if not 0 <= x < DisplayConfig.MATRIX_COLS:
                continue
            at_edge = x_offset < 2 or x_offset >= width - 2
            if not at_edge and y > 0:
                self.manager.draw_pixel(x, y - 1, 235, 238, 245)
            body = (210, 216, 228) if at_edge else (255, 255, 255)
            self.manager.draw_pixel(x, y, *body)
            if y < DisplayConfig.MATRIX_ROWS - 1:
                shade = (200, 206, 220) if at_edge else (232, 235, 242)
                self.manager.draw_pixel(x, y + 1, *shade)

    def _drift_clouds(self) -> None:
        for cloud in self.clouds:
            cloud['x'] += cloud['speed']
            if cloud['x'] > DisplayConfig.MATRIX_COLS:
                cloud['x'] = -float(cloud['width'])
                cloud['y'] = random.randint(4, 14)

    def _draw_day_frame(
        self, fraction: float, sunrise: pendulum.DateTime,
        sunset: pendulum.DateTime, tick: float | None = None
    ) -> None:
        """Sun climbing its arc between today's sunrise and sunset"""
        if tick is None:
            tick = time.time()
        self.manager.clear_canvas()

        # Sky warms toward golden hour near sunrise and sunset
        low_sun = 1.0 - min(1.0, min(fraction, 1.0 - fraction) / 0.18)
        sky_top = self._blend(DAY_SKY_TOP, LOW_SUN_SKY_TOP, low_sun)
        sky_bottom = self._blend(DAY_SKY_BOTTOM, LOW_SUN_SKY_BOTTOM, low_sun)
        self._draw_gradient(sky_top, sky_bottom)

        # Grass below the horizon
        for y in range(40, DisplayConfig.MATRIX_ROWS):
            t = (y - 40) / (DisplayConfig.MATRIX_ROWS - 1 - 40)
            color = self._blend(GRASS_TOP, GRASS_BOTTOM, t)
            for x in range(DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, y, *color)
        for x in range(DisplayConfig.MATRIX_COLS):
            self.manager.draw_pixel(x, 39, 95, 150, 85)

        # Drifting clouds behind the sun
        for cloud in self.clouds:
            self._draw_cloud(cloud)
        self._drift_clouds()

        # Arc: golden trail already traveled, dotted path still ahead
        for i in range(0, 41):
            ax, ay = self._arc_point(i / 40)
            if i / 40 <= fraction:
                self.manager.draw_pixel(ax, ay, *SUN_TRAIL)
            elif i % 2 == 0:
                self.manager.draw_pixel(ax, ay, *ARC_GRAY)

        # The sun: soft glow halo, bright core, gently pulsing rays
        sx, sy = self._arc_point(fraction)
        halo = self._blend(sky_top, SUN_YELLOW, 0.45)
        for dx in range(-4, 5):
            for dy in range(-4, 5):
                d2 = dx * dx + dy * dy
                if 5 < d2 <= 16:
                    self.manager.draw_pixel(sx + dx, sy + dy, *halo)
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                if dx * dx + dy * dy <= 5:
                    self.manager.draw_pixel(sx + dx, sy + dy, *SUN_YELLOW)
        pulse = abs(math.sin(tick * 2.0))
        ray_len = 5 + (1 if pulse > 0.5 else 0)
        for angle in range(0, 360, 45):
            rad = math.radians(angle)
            rx = sx + int(ray_len * math.cos(rad))
            ry = sy + int(ray_len * math.sin(rad))
            if 0 <= rx < DisplayConfig.MATRIX_COLS and 0 <= ry < 48:
                self.manager.draw_pixel(rx, ry, 255, 235, 140)

        self.manager.draw_text(
            'micro', 2, 46, Colors.WHITE, sunrise.format('h:mmA'))
        sunset_str = sunset.format('h:mmA')
        self.manager.draw_text(
            'micro', 94 - len(sunset_str) * 4, 46, Colors.WHITE, sunset_str)
        title = 'SUN & SKY'
        self.manager.draw_text(
            'micro', (96 - len(title) * 4) // 2, 6, SUN_YELLOW, title)
        self.manager.swap_canvas()

    def _update_shooting_star(self) -> None:
        """Occasional shooting star streaking down the night sky"""
        if self.shooting_star is None:
            if random.random() < 0.006:
                self.shooting_star = {
                    'x': float(random.randint(10, 70)),
                    'y': float(random.randint(0, 6)),
                    'speed_x': random.uniform(1.2, 2.0),
                    'speed_y': random.uniform(0.5, 1.0),
                    'tail': random.randint(5, 8),
                }
            return
        star = self.shooting_star
        x, y = int(star['x']), int(star['y'])
        if 0 <= x < DisplayConfig.MATRIX_COLS and 0 <= y < 38:
            self.manager.draw_pixel(x, y, 255, 255, 255)
        for i in range(1, star['tail'] + 1):
            tx = int(star['x'] - star['speed_x'] * i)
            ty = int(star['y'] - star['speed_y'] * i)
            if 0 <= tx < DisplayConfig.MATRIX_COLS and 0 <= ty < 38:
                fade = 1.0 - i / (star['tail'] + 1)
                level = int(220 * fade)
                self.manager.draw_pixel(
                    tx, ty, level, level, min(255, int(level * 1.15)))
        star['x'] += star['speed_x']
        star['y'] += star['speed_y']
        if star['x'] >= DisplayConfig.MATRIX_COLS or star['y'] >= 38:
            self.shooting_star = None

    def _draw_night_frame(
        self, phase_fraction: float, phase_name: str,
        sunrise: pendulum.DateTime | None, tick: float | None = None
    ) -> None:
        """Tonight's moon over a starfield"""
        if tick is None:
            tick = time.time()
        self.manager.clear_canvas()
        self._draw_gradient(NIGHT_SKY_TOP, NIGHT_SKY_BOTTOM)

        # Deterministic starfield, each star twinkling at its own pace
        for i in range(34):
            x = (i * 37 + 11) % DisplayConfig.MATRIX_COLS
            y = (i * 17 + 5) % 38
            level = int(150 + 100 * math.sin(tick * (0.6 + i % 5 * 0.35) + i))
            level = max(60, min(255, level))
            self.manager.draw_pixel(x, y, level, level, min(255, level + 20))
            if level > 230:
                glow = int(level * 0.35)
                for gx, gy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nx, ny = x + gx, y + gy
                    if 0 <= nx < DisplayConfig.MATRIX_COLS and 0 <= ny < 38:
                        self.manager.draw_pixel(nx, ny, glow, glow, glow + 10)

        self._update_shooting_star()

        # Moon: lit disc with a same-size shadow disc slid across it.
        # Waxing: shadow retreats to the left; waning: returns from the
        # right. Offset 0 = new moon (covered), +/-2r = full (clear).
        cx, cy, radius = 48, 22, 9
        if phase_fraction < 0.5:
            shadow_center = -4 * radius * phase_fraction
        else:
            shadow_center = 4 * radius * (1 - phase_fraction)

        # Soft glow halo around the disc
        for dy in range(-radius - 2, radius + 3):
            for dx in range(-radius - 2, radius + 3):
                d2 = dx * dx + dy * dy
                if radius * radius < d2 <= (radius + 2) * (radius + 2):
                    glow = MOON_GLOW if d2 <= (radius + 1) * (radius + 1) \
                        else self._blend(NIGHT_SKY_TOP, MOON_GLOW, 0.45)
                    self.manager.draw_pixel(cx + dx, cy + dy, *glow)

        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx * dx + dy * dy > radius * radius:
                    continue
                sdx = dx - shadow_center
                in_shadow = sdx * sdx + dy * dy <= radius * radius
                if in_shadow:
                    color = MOON_DARK
                elif (dx, dy) in MOON_CRATERS:
                    color = MOON_CRATER
                else:
                    color = MOON_LIT
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
        if not self.clouds:
            self._init_clouds()
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
            time.sleep(0.12)

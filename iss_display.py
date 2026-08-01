"""ISS tracker - where the Space Station is relative to home"""

from __future__ import annotations

import math
import time
import requests
from PIL import Image
from typing import TYPE_CHECKING, Any

from scoreboard_config import Colors, DisplayConfig

if TYPE_CHECKING:
    from scoreboard_manager import ScoreboardManager

ISS_API_URL = 'http://api.open-notify.org/iss-now.json'
ISS_IMAGE_PATH = './iss.png'
LAND_MASK_PATHS = ('./land_mask.png', '/home/pi/land_mask.png')
ISS_SPEED_MPH = 17150
ISS_ALTITUDE_MI = 254
OVERHEAD_MILES = 500  # close enough to call it overhead

SPACE_TOP = (2, 2, 12)
SPACE_BOTTOM = (10, 14, 34)
TITLE_BLUE = (140, 160, 220)
OVERHEAD_GREEN = (60, 220, 90)

# Globe view: orthographic hemisphere centered on home
GLOBE_CX, GLOBE_CY, GLOBE_R = 23, 25, 21
OCEAN_BLUE = (8, 30, 72)
LAND_GREEN = (38, 128, 58)
ARC_TAIL = (180, 140, 0)
ARC_HEAD = (255, 223, 0)
HORIZON_DIM = (90, 110, 170)


class ISSDisplay:
    """Shows the Space Station's live position and distance from home"""

    def __init__(
        self, scoreboard_manager: ScoreboardManager,
        latitude: float | None, longitude: float | None
    ) -> None:
        self.manager = scoreboard_manager
        self.latitude = latitude
        self.longitude = longitude
        try:
            self.sprite: Image.Image | None = Image.open(
                ISS_IMAGE_PATH).convert('RGBA')
        except Exception as e:
            print(f"ISS artwork unavailable: {e}")
            self.sprite = None
        self.land_mask: Image.Image | None = self._load_land_mask()
        self._globe_bg: Image.Image | None = None  # built lazily, cached
        self._arc_cache: tuple[tuple[float, float], list] | None = None

    @staticmethod
    def _load_land_mask() -> Image.Image | None:
        for path in LAND_MASK_PATHS:
            try:
                return Image.open(path).convert('1')
            except Exception:
                continue
        print("land_mask.png not found; globe view disabled")
        return None

    @staticmethod
    def _parse_position(payload: dict[str, Any]) -> tuple[float, float] | None:
        """(lat, lon) from an open-notify response, or None"""
        try:
            if payload.get('message') != 'success':
                return None
            pos = payload['iss_position']
            return (float(pos['latitude']), float(pos['longitude']))
        except (KeyError, TypeError, ValueError):
            return None

    def _fetch_position(self) -> tuple[float, float] | None:
        try:
            response = requests.get(ISS_API_URL, timeout=5)
            return self._parse_position(response.json())
        except Exception as e:
            print(f"ISS position unavailable: {e}")
            return None

    @staticmethod
    def _distance_mi(
        lat1: float, lon1: float, lat2: float, lon2: float
    ) -> float:
        """Great-circle ground distance in miles"""
        rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2) ** 2
             + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2)
        return 3959 * 2 * math.asin(math.sqrt(a))

    @staticmethod
    def _bearing(
        lat1: float, lon1: float, lat2: float, lon2: float
    ) -> float:
        """Initial bearing in degrees from point 1 toward point 2"""
        rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
        dlon = math.radians(lon2 - lon1)
        x = math.sin(dlon) * math.cos(rlat2)
        y = (math.cos(rlat1) * math.sin(rlat2)
             - math.sin(rlat1) * math.cos(rlat2) * math.cos(dlon))
        return math.degrees(math.atan2(x, y)) % 360

    @staticmethod
    def _cardinal(degrees: float) -> str:
        directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
        return directions[int((degrees + 22.5) // 45) % 8]

    def _project(self, lat: float, lon: float) -> tuple[int, int, float]:
        """Orthographic projection centered on home: pixel (x, y) plus
        cos of the angular distance - negative means the far side"""
        lat0, lon0 = math.radians(self.latitude), math.radians(self.longitude)
        rlat, dlon = math.radians(lat), math.radians(lon - self.longitude)
        x = math.cos(rlat) * math.sin(dlon)
        y = (math.cos(lat0) * math.sin(rlat)
             - math.sin(lat0) * math.cos(rlat) * math.cos(dlon))
        cos_c = (math.sin(lat0) * math.sin(rlat)
                 + math.cos(lat0) * math.cos(rlat) * math.cos(dlon))
        return (GLOBE_CX + round(x * GLOBE_R),
                GLOBE_CY - round(y * GLOBE_R), cos_c)

    def _build_globe_bg(self) -> Image.Image:
        """Space gradient with the home-centered hemisphere, built once"""
        img = Image.new(
            'RGB', (DisplayConfig.MATRIX_COLS, DisplayConfig.MATRIX_ROWS))
        pixels = img.load()
        for y in range(DisplayConfig.MATRIX_ROWS):
            t = y / (DisplayConfig.MATRIX_ROWS - 1)
            color = tuple(int(a + (b - a) * t)
                          for a, b in zip(SPACE_TOP, SPACE_BOTTOM))
            for x in range(DisplayConfig.MATRIX_COLS):
                pixels[x, y] = color

        lat0 = math.radians(self.latitude)
        lon0 = math.radians(self.longitude)
        mask = self.land_mask
        for py in range(GLOBE_CY - GLOBE_R, GLOBE_CY + GLOBE_R + 1):
            for px in range(GLOBE_CX - GLOBE_R, GLOBE_CX + GLOBE_R + 1):
                dx = (px - GLOBE_CX) / GLOBE_R
                dy = (GLOBE_CY - py) / GLOBE_R
                rho2 = dx * dx + dy * dy
                if rho2 > 1:
                    continue
                # Inverse orthographic back to lat/lon
                rho = math.sqrt(rho2)
                if rho < 1e-9:
                    lat, lon = self.latitude, self.longitude
                else:
                    c = math.asin(min(1.0, rho))
                    sin_c, cos_c = math.sin(c), math.cos(c)
                    lat = math.degrees(math.asin(
                        cos_c * math.sin(lat0)
                        + dy * sin_c * math.cos(lat0) / rho))
                    lon = self.longitude + math.degrees(math.atan2(
                        dx * sin_c,
                        rho * math.cos(lat0) * cos_c
                        - dy * math.sin(lat0) * sin_c))
                land = False
                if mask is not None:
                    # Mask is equirectangular with lon -180 at x=0
                    mx = int(((lon + 180) % 360) / 360 * mask.width)
                    my = min(mask.height - 1,
                             int((90 - lat) / 180 * mask.height))
                    land = bool(mask.getpixel((mx % mask.width, my)))
                base = LAND_GREEN if land else OCEAN_BLUE
                # Limb darkening sells the sphere
                shade = 0.45 + 0.55 * math.sqrt(max(0.0, 1.0 - rho2))
                pixels[px, py] = tuple(int(c * shade) for c in base)
        return img

    def _arc_points(
        self, position: tuple[float, float]
    ) -> list[tuple[int, int, bool]]:
        """Great-circle pixels from home toward the station, clipped at
        the horizon; the last element carries visible=False if the
        station is on the far side of the globe"""
        if self._arc_cache is not None and self._arc_cache[0] == position:
            return self._arc_cache[1]

        def vec(lat: float, lon: float) -> tuple[float, float, float]:
            rlat, rlon = math.radians(lat), math.radians(lon)
            return (math.cos(rlat) * math.cos(rlon),
                    math.cos(rlat) * math.sin(rlon), math.sin(rlat))

        v1 = vec(self.latitude, self.longitude)
        v2 = vec(*position)
        dot = max(-1.0, min(1.0, sum(a * b for a, b in zip(v1, v2))))
        omega = math.acos(dot)
        points: list[tuple[int, int, bool]] = []
        if omega < 1e-6:
            self._arc_cache = (position, points)
            return points
        sin_omega = math.sin(omega)
        last = None
        for i in range(1, 49):
            t = i / 48
            f1 = math.sin((1 - t) * omega) / sin_omega
            f2 = math.sin(t * omega) / sin_omega
            p = tuple(f1 * a + f2 * b for a, b in zip(v1, v2))
            lat = math.degrees(math.asin(max(-1.0, min(1.0, p[2]))))
            lon = math.degrees(math.atan2(p[1], p[0]))
            x, y, cos_c = self._project(lat, lon)
            if cos_c < 0:  # dipped below the horizon - stop the line there
                if points:
                    points[-1] = (points[-1][0], points[-1][1], False)
                break
            if (x, y) != last:
                points.append((x, y, True))
                last = (x, y)
        self._arc_cache = (position, points)
        return points

    def _draw_globe_frame(
        self, position: tuple[float, float], distance: float,
        direction: str, progress: float, tick: float | None = None
    ) -> None:
        """Hemisphere centered on home with a line reaching to the ISS"""
        if tick is None:
            tick = time.time()
        if self._globe_bg is None:
            self._globe_bg = self._build_globe_bg()
        self.manager.clear_canvas()
        img = self._globe_bg.copy()
        pixels = img.load()

        # Twinkling stars, kept off the globe
        for i in range(26):
            x = (i * 41 + 7) % DisplayConfig.MATRIX_COLS
            y = (i * 19 + 3) % DisplayConfig.MATRIX_ROWS
            if ((x - GLOBE_CX) ** 2 + (y - GLOBE_CY) ** 2
                    <= (GLOBE_R + 1) ** 2):
                continue
            level = 80 if (i + int(tick)) % 4 else 200
            pixels[x, y] = (level, level, level)

        # The line grows from home toward the station
        arc = self._arc_points(position)
        count = max(1, round(len(arc) * progress)) if arc else 0
        for i, (ax, ay, _) in enumerate(arc[:count]):
            pixels[ax, ay] = ARC_HEAD if i >= count - 2 else ARC_TAIL

        # Station marker once the line arrives (or pulsing home if overhead)
        blink_on = int(tick * 2) % 2 == 0
        if arc and progress >= 1.0 and blink_on:
            ex, ey, visible = arc[-1]
            color = OVERHEAD_GREEN if visible else HORIZON_DIM
            for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                if (0 <= ex + dx < DisplayConfig.MATRIX_COLS
                        and 0 <= ey + dy < DisplayConfig.MATRIX_ROWS):
                    pixels[ex + dx, ey + dy] = color

        # Home is always dead center
        pixels[GLOBE_CX, GLOBE_CY] = (
            (255, 255, 255) if blink_on else Colors.YELLOW)
        self.manager.set_image(img, 0, 0)

        # Vitals column to the right of the globe
        col_center = 70
        title = 'ISS TRACKER'
        self.manager.draw_text(
            'micro', col_center - (len(title) * 4) // 2, 10,
            TITLE_BLUE, title)
        if distance <= OVERHEAD_MILES:
            info, info_color = 'OVERHEAD!', OVERHEAD_GREEN
        else:
            info, info_color = f'{distance:,.0f} MI', Colors.YELLOW
        self.manager.draw_text(
            'micro', col_center - (len(info) * 4) // 2, 25,
            info_color, info)
        heading = f'TO THE {direction}'
        self.manager.draw_text(
            'micro', col_center - (len(heading) * 4) // 2, 36,
            Colors.WHITE, heading)
        self.manager.swap_canvas()

    def _draw_iss_frame(
        self, distance: float, direction: str, tick: float | None = None
    ) -> None:
        """The station artwork over a starfield with its vitals alongside"""
        if tick is None:
            tick = time.time()
        self.manager.clear_canvas()

        img = Image.new(
            'RGB', (DisplayConfig.MATRIX_COLS, DisplayConfig.MATRIX_ROWS))
        pixels = img.load()
        for y in range(DisplayConfig.MATRIX_ROWS):
            t = y / (DisplayConfig.MATRIX_ROWS - 1)
            color = tuple(int(a + (b - a) * t)
                          for a, b in zip(SPACE_TOP, SPACE_BOTTOM))
            for x in range(DisplayConfig.MATRIX_COLS):
                pixels[x, y] = color

        # Twinkling starfield behind everything
        for i in range(26):
            x = (i * 41 + 7) % DisplayConfig.MATRIX_COLS
            y = (i * 19 + 3) % DisplayConfig.MATRIX_ROWS
            level = 80 if (i + int(tick)) % 4 else 200
            pixels[x, y] = (level, level, level)

        # The station drifts gently on the left
        if self.sprite is not None:
            bob = int(tick) % 2
            img.paste(self.sprite, (1, 7 + bob), self.sprite)
        self.manager.set_image(img, 0, 0)

        title = 'SPACE STATION'
        self.manager.draw_text(
            'micro', (96 - len(title) * 4) // 2, 6, TITLE_BLUE, title)

        # Vitals column to the right of the artwork
        col_center = 68
        if distance <= OVERHEAD_MILES:
            info, info_color = 'OVERHEAD!', OVERHEAD_GREEN
        else:
            info, info_color = f'{distance:,.0f} MI {direction}', Colors.YELLOW
        self.manager.draw_text(
            'micro', col_center - (len(info) * 4) // 2, 21,
            info_color, info)

        stats = f'{ISS_SPEED_MPH:,} MPH'
        self.manager.draw_text(
            'micro', col_center - (len(stats) * 4) // 2, 32,
            Colors.WHITE, stats)
        alt = f'{ISS_ALTITUDE_MI} MILES UP'
        self.manager.draw_text(
            'micro', col_center - (len(alt) * 4) // 2, 43, TITLE_BLUE, alt)
        self.manager.swap_canvas()

    def display_iss(self, duration: int = 60) -> bool:
        """Track the station; False if location or API is unavailable"""
        if self.latitude is None or self.longitude is None:
            return False
        position = self._fetch_position()
        if position is None:
            return False

        print("Displaying ISS tracker...")
        start = time.time()
        last_fetch = time.time()
        # First half: the station card; second half: the globe view with
        # the line animating out from home (skipped without a land mask)
        globe_at = duration / 2 if self.land_mask is not None else duration
        while time.time() - start < duration:
            elapsed = time.time() - start
            distance = self._distance_mi(
                self.latitude, self.longitude, *position)
            direction = self._cardinal(self._bearing(
                self.latitude, self.longitude, *position))
            if elapsed < globe_at:
                self._draw_iss_frame(distance, direction)
                time.sleep(1)
            else:
                progress = min(1.0, (elapsed - globe_at) / 2.5)
                self._draw_globe_frame(
                    position, distance, direction, progress)
                time.sleep(0.12)
            if time.time() - last_fetch >= 10:  # it moves ~5 miles a second
                fresh = self._fetch_position()
                if fresh is not None:
                    position = fresh
                last_fetch = time.time()
        return True

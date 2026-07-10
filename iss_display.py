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
ISS_SPEED_MPH = 17150
ISS_ALTITUDE_MI = 254
OVERHEAD_MILES = 500  # close enough to call it overhead

SPACE_TOP = (2, 2, 12)
SPACE_BOTTOM = (10, 14, 34)
TITLE_BLUE = (140, 160, 220)
OVERHEAD_GREEN = (60, 220, 90)


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
        while time.time() - start < duration:
            distance = self._distance_mi(
                self.latitude, self.longitude, *position)
            direction = self._cardinal(self._bearing(
                self.latitude, self.longitude, *position))
            self._draw_iss_frame(distance, direction)
            time.sleep(1)
            if time.time() - last_fetch >= 10:  # it moves ~5 miles a second
                fresh = self._fetch_position()
                if fresh is not None:
                    position = fresh
                last_fetch = time.time()
        return True

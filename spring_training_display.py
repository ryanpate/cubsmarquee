"""Spring Training Countdown display for Cubs LED Scoreboard"""

from __future__ import annotations

import time
import pendulum
import statsapi
from PIL import Image
import os
from typing import TYPE_CHECKING

from scoreboard_config import Colors, GameConfig, DisplayConfig, RGBColor, TeamConfig, get_scroll_delay, load_user_config
from retry import retry_api_call

if TYPE_CHECKING:
    from scoreboard_manager import ScoreboardManager


class SpringTrainingDisplay:
    """Handles Spring Training countdown display with scrolling text"""

    def __init__(self, scoreboard_manager: ScoreboardManager) -> None:
        """Initialize Spring Training display"""
        self.manager = scoreboard_manager
        self.scroll_position: int = DisplayConfig.MATRIX_COLS

        # Color scheme - Cubs colors
        self.CUBS_BLUE: RGBColor = Colors.CUBS_BLUE
        self.CUBS_YELLOW: RGBColor = Colors.YELLOW
        self.WHITE: RGBColor = Colors.WHITE

        # Load and cache Spring Training header image
        self._header_image: Image.Image | None = self._load_header_image()

        # Daily cache for the Opening Day lookup
        self._opening_day_cache: pendulum.DateTime | None = None
        self._opening_day_cached_on: str | None = None

    def _load_header_image(self) -> Image.Image | None:
        """Load Spring Training header image"""
        image_paths = [
            './spring_training.png',
            '/home/pi/spring_training.png'
        ]
        for path in image_paths:
            if os.path.exists(path):
                try:
                    image = Image.open(path).convert('RGBA')
                    print(f"Loaded Spring Training header from {path}")
                    return image
                except Exception as e:
                    print(f"Error loading Spring Training image: {e}")
        print("Spring Training image not found")
        return None

    def _load_scroll_config(self) -> dict:
        """Load scroll speed settings from config file"""
        return load_user_config()

    def is_spring_training_active(self) -> bool:
        """Check if Spring Training is currently underway (Feb 21 - Mar 31)."""
        now = pendulum.now('America/Chicago')
        start = pendulum.datetime(now.year, 2, 21, tz='America/Chicago')
        end = pendulum.datetime(now.year, 3, 31, tz='America/Chicago')
        return start <= now <= end

    def _get_spring_training_date(self) -> pendulum.DateTime:
        """
        Get the Spring Training start date for the current/upcoming year.
        Spring Training typically starts around February 21-22.
        """
        now = pendulum.now('America/Chicago')
        year = now.year

        # Spring Training start date (approximate - first game around Feb 21)
        spring_training = pendulum.datetime(year, 2, 21, tz='America/Chicago')

        # Once Spring Training is over (same Mar 31 cutoff as
        # is_spring_training_active), count down to next year
        end = pendulum.datetime(year, 3, 31, tz='America/Chicago')
        if now > end:
            spring_training = pendulum.datetime(year + 1, 2, 21, tz='America/Chicago')

        return spring_training

    def _get_opening_day(self) -> pendulum.DateTime | None:
        """First regular-season game of the current year (cached daily)"""
        today = pendulum.now('America/Chicago').format('YYYY-MM-DD')
        if self._opening_day_cached_on == today:
            return self._opening_day_cache

        year = pendulum.now('America/Chicago').year
        try:
            games = retry_api_call(
                statsapi.schedule,
                start_date=f'03/01/{year}', end_date=f'04/15/{year}',
                team=TeamConfig.CUBS_TEAM_ID,
            )
            for game in games:
                if game.get('game_type') == 'R':
                    self._opening_day_cache = pendulum.parse(
                        game['game_datetime']).in_timezone('America/Chicago')
                    self._opening_day_cached_on = today
                    return self._opening_day_cache
        except Exception as e:
            print(f"Could not fetch Opening Day: {e}")
        return None

    def _get_countdown_target(self) -> tuple[str, pendulum.DateTime]:
        """The next milestone to count down to: Spring Training, then
        Opening Day, then next year's Spring Training."""
        now = pendulum.now('America/Chicago')
        spring_training = pendulum.datetime(
            now.year, 2, 21, tz='America/Chicago')
        if now < spring_training:
            return ('Spring Training', spring_training)

        opening_day = self._get_opening_day()
        if opening_day and now < opening_day:
            return ('Opening Day', opening_day)
        if opening_day is None and now.month <= 3:
            # Schedule not published: opening day is typically late March
            return ('Opening Day',
                    pendulum.datetime(now.year, 3, 26, tz='America/Chicago'))

        return ('Spring Training',
                pendulum.datetime(now.year + 1, 2, 21, tz='America/Chicago'))

    def _calculate_countdown(self) -> dict[str, int]:
        """
        Calculate the countdown to the next milestone.
        Returns dict with days, hours, minutes, and the milestone label.
        """
        now = pendulum.now('America/Chicago')
        label, target = self._get_countdown_target()

        diff = target - now

        # Calculate components
        total_seconds = max(0, int(diff.total_seconds()))
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60

        return {
            'days': days,
            'hours': hours,
            'minutes': minutes,
            'year': target.year,
            'label': label
        }

    def _get_countdown_message(self, countdown: dict[str, int]) -> str:
        """Generate the scrolling countdown message"""
        days = countdown['days']
        hours = countdown['hours']
        minutes = countdown['minutes']
        label = countdown.get('label', 'Spring Training')

        if days > 0:
            day_word = "Day" if days == 1 else "Days"
            return f"{days} {day_word} till {label}"
        elif hours > 0:
            hour_word = "Hour" if hours == 1 else "Hours"
            return f"{hours} {hour_word} till {label}"
        elif minutes > 0:
            minute_word = "Minute" if minutes == 1 else "Minutes"
            return f"{minutes} {minute_word} till {label}"
        else:
            return f"{label} is HERE!"

    def _draw_header(self) -> None:
        """Draw the Spring Training header image at the top, centered with Cubs blue background"""
        # Create a full-screen image with Cubs blue background
        background = Image.new("RGB", (96, 48), self.CUBS_BLUE)

        if self._header_image:
            # Center the header image horizontally
            image_width = self._header_image.width
            x_offset = (96 - image_width) // 2
            x_offset = max(0, x_offset)

            # Paste the header image onto the blue background with transparency
            background.paste(self._header_image, (x_offset, 0), self._header_image)

        # Display the composite image
        self.manager.set_image(background, 0, 0)

    def display_spring_training_countdown(self, duration: int = 180) -> None:
        """Display Spring Training countdown with scrolling message"""
        start_time = time.time()
        self.scroll_position = 96
        last_countdown_update = 0
        cached_countdown: dict[str, int] | None = None
        current_message: str = ""

        print("Displaying Spring Training countdown...")

        while time.time() - start_time < duration:
            try:
                self.manager.clear_canvas()

                # Update countdown every 60 seconds
                current_time = time.time()
                if cached_countdown is None or (current_time - last_countdown_update) >= 60:
                    cached_countdown = self._calculate_countdown()
                    current_message = self._get_countdown_message(cached_countdown)
                    last_countdown_update = current_time
                    print(f"Spring Training countdown: {current_message}")

                # Draw the header image at the top
                self._draw_header()

                # Scroll the countdown message at the bottom
                scroll_increment = getattr(GameConfig, 'SCROLL_PIXELS', 1)
                self.scroll_position -= scroll_increment
                text_length = len(current_message) * 9  # medium_bold font width

                # Reset scroll position when text fully exits left side
                if self.scroll_position + text_length < 0:
                    self.scroll_position = 96

                # Draw scrolling countdown text at the bottom with black outline
                text_x = int(self.scroll_position)
                text_y = 44
                # Draw black outline (offset in all directions)
                for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)]:
                    self.manager.draw_text(
                        'medium_bold', text_x + dx, text_y + dy,
                        (0, 0, 0), current_message
                    )
                # Draw main text on top
                self.manager.draw_text(
                    'medium_bold', text_x, text_y,
                    self.CUBS_YELLOW, current_message
                )

                self.manager.swap_canvas()
                # Use configurable scroll speed (Spring Training is intentionally slower)
                config = self._load_scroll_config()
                scroll_delay = get_scroll_delay(config.get('scroll_speed_spring_training', 5))
                time.sleep(scroll_delay)

            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"Error in Spring Training countdown display: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(1)

    def display(self, duration: int = 180) -> None:
        """Main display method for compatibility with DisplayHandler pattern"""
        self.display_spring_training_countdown(duration)

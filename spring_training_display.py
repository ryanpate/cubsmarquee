"""Spring Training Countdown display for Cubs LED Scoreboard"""

from __future__ import annotations

import time
import pendulum
from PIL import Image
import os
from typing import TYPE_CHECKING

from scoreboard_config import Colors, GameConfig, DisplayConfig, RGBColor

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

    def _get_spring_training_date(self) -> pendulum.DateTime:
        """
        Get the Spring Training start date for the current/upcoming year.
        Spring Training typically starts around February 21-22.
        """
        now = pendulum.now('America/Chicago')
        year = now.year

        # Spring Training start date (approximate - first game around Feb 21)
        spring_training = pendulum.datetime(year, 2, 21, tz='America/Chicago')

        # If Spring Training has passed (we're in April or later), use next year
        if now > spring_training.add(months=2):
            spring_training = pendulum.datetime(year + 1, 2, 21, tz='America/Chicago')

        return spring_training

    def _calculate_countdown(self) -> dict[str, int]:
        """
        Calculate the countdown to Spring Training.
        Returns dict with days, hours, minutes.
        """
        now = pendulum.now('America/Chicago')
        spring_training = self._get_spring_training_date()

        diff = spring_training - now

        # Calculate components
        total_seconds = max(0, int(diff.total_seconds()))
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60

        return {
            'days': days,
            'hours': hours,
            'minutes': minutes,
            'year': spring_training.year
        }

    def _get_countdown_message(self, countdown: dict[str, int]) -> str:
        """Generate the scrolling countdown message"""
        days = countdown['days']
        hours = countdown['hours']
        minutes = countdown['minutes']

        if days > 0:
            day_word = "Day" if days == 1 else "Days"
            return f"{days} {day_word} till Spring Training"
        elif hours > 0:
            hour_word = "Hour" if hours == 1 else "Hours"
            return f"{hours} {hour_word} till Spring Training"
        elif minutes > 0:
            minute_word = "Minute" if minutes == 1 else "Minutes"
            return f"{minutes} {minute_word} till Spring Training"
        else:
            return "Spring Training is HERE!"

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
        self.manager.canvas.SetImage(background, 0, 0)

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
                time.sleep(GameConfig.SCROLL_SPEED * 6)  # Slower scroll for countdown

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

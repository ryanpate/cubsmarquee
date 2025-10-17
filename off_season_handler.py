"""Handler for off-season content display"""

import time
import json
import os
import pendulum
from PIL import Image
from scoreboard_config import Colors, GameConfig
from weather_display import WeatherDisplay


class OffSeasonHandler:
    """Manages off-season content rotation"""

    def __init__(self, scoreboard_manager):
        """Initialize with reference to main scoreboard manager"""
        self.manager = scoreboard_manager
        self.weather_display = WeatherDisplay(scoreboard_manager)
        self.scroll_position = 96

        # Load configuration
        self.config = self._load_config()

        # Content rotation schedule (in minutes)
        self.rotation_schedule = {
            'weather': 5,      # Show weather for 5 minutes
            'cubs_trivia': 2,  # Cubs trivia for 2 minutes
            'message': 3       # Custom message for 3 minutes
        }

    def _load_config(self):
        """Load configuration from JSON file"""
        config_path = '/home/pi/config.json'

        default_config = {
            'zip_code': '',
            'weather_api_key': '',
            'custom_message': 'GO CUBS GO! SEE YOU NEXT SEASON!',
            'display_mode': 'auto'  # auto, weather_only, message_only
        }

        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    loaded_config = json.load(f)
                    # Merge with defaults
                    default_config.update(loaded_config)
        except Exception as e:
            print(f"Error loading config: {e}")

        return default_config

    def display_off_season_content(self):
        """Main loop for off-season content rotation"""
        print("Entering off-season display mode...")

        # Check if weather is configured
        weather_enabled = (
            self.config.get('zip_code') and
            self.config.get('weather_api_key')
        )

        if not weather_enabled:
            print("Weather not configured - showing default message only")
            self._display_message_loop()
            return

        # Main rotation loop
        while True:
            try:
                # Reload config periodically (every loop)
                self.config = self._load_config()

                # Check if season has started
                if self._check_season_started():
                    print("New season detected! Exiting off-season mode...")
                    return

                # Display mode handling
                display_mode = self.config.get('display_mode', 'auto')

                if display_mode == 'weather_only' and weather_enabled:
                    self._display_weather_cycle()
                elif display_mode == 'message_only':
                    self._display_message_cycle()
                else:  # auto mode
                    self._display_rotation_cycle()

            except Exception as e:
                print(f"Error in off-season display: {e}")
                time.sleep(10)

    def _check_season_started(self):
        """Check if a new season has started"""
        try:
            from scoreboard_manager import ScoreboardManager
            temp_manager = ScoreboardManager()
            game_data = temp_manager.get_schedule()
            return bool(game_data)  # If games found, season started
        except:
            return False

    def _display_rotation_cycle(self):
        """Rotate between different content types"""
        # Display weather
        print("Displaying weather...")
        self.weather_display.display_weather_screen(
            duration=self.rotation_schedule['weather'] * 60
        )

        # Display Cubs trivia/history
        print("Displaying Cubs content...")
        self._display_cubs_content(
            duration=self.rotation_schedule['cubs_trivia'] * 60
        )

        # Display custom message
        print("Displaying custom message...")
        self._display_custom_message(
            duration=self.rotation_schedule['message'] * 60
        )

    def _display_weather_cycle(self):
        """Display weather for extended period"""
        self.weather_display.display_weather_screen(duration=300)  # 5 minutes

    def _display_message_cycle(self):
        """Display message for extended period"""
        self._display_custom_message(duration=300)  # 5 minutes

    def _display_cubs_content(self, duration=120):
        """Display Cubs-related content"""
        cubs_facts = [
            "CUBS WON THE 2016 WORLD SERIES!",
            "WRIGLEY FIELD - HOME OF THE CUBS SINCE 1916",
            "FLY THE W! GO CUBS GO!",
            "108 YEARS - WORTH THE WAIT!",
            "THE FRIENDLY CONFINES",
            "CUBS HAVE 3 WORLD SERIES TITLES (1907, 1908, 2016)",
            "ERNIE BANKS - MR. CUB - 512 HOME RUNS",
            "RYNE SANDBERG - HALL OF FAME 2B",
            "FERGUSON JENKINS - CUBS ACE - HOF",
            "BILLY WILLIAMS - 426 HOME RUNS AS A CUB"
        ]

        start_time = time.time()
        fact_index = 0

        while time.time() - start_time < duration:
            self.manager.clear_canvas()

            # Create Cubs blue background
            self.manager.fill_canvas(*Colors.CUBS_BLUE)

            # Draw Cubs logo if available
            try:
                cubs_logo = Image.open('./logos/cubs28x28.png')#.resize((32, 32))
                output_image = Image.new("RGB", (96, 48), (0, 51, 102))
                output_image.paste(cubs_logo, (32, 2))
                self.manager.canvas.SetImage(output_image.convert("RGB"), 0, 0)
            except:
                pass

            # Draw title
            self.manager.draw_text('small_bold', 12, 10,
                                   Colors.WHITE, 'CUBS HISTORY')

            # Scroll the fact
            current_fact = cubs_facts[fact_index]

            self.scroll_position -= 1
            text_length = len(current_fact) * 7

            if self.scroll_position + text_length < 0:
                self.scroll_position = 96
                fact_index = (fact_index + 1) % len(cubs_facts)

            self.manager.draw_text(
                'lineup', self.scroll_position, 45, Colors.YELLOW, current_fact
            )

            self.manager.swap_canvas()
            time.sleep(GameConfig.SCROLL_SPEED)

    def _display_custom_message(self, duration=180):
        """Display custom scrolling message"""
        message = self.config.get('custom_message', 'GO CUBS GO!')

        start_time = time.time()
        self.scroll_position = 96

        while time.time() - start_time < duration:
            self.manager.clear_canvas()

            # Create gradient background
            for y in range(48):
                # Gradient from Cubs blue to slightly lighter blue
                blue_intensity = int(102 + (y * 0.5))
                for x in range(96):
                    self.manager.draw_pixel(x, y, 0, 51, blue_intensity)

            # Display marquee image if available
            try:
                marquee = Image.open('./marquee.png')
                output_image = Image.new("RGB", (96, 48))
                output_image.paste(marquee, (0, 0))
                self.manager.canvas.SetImage(output_image.convert("RGB"), 0, 0)
            except:
                pass

            # Scroll the message
            self.scroll_position -= .2
            text_length = len(message) * 9

            if self.scroll_position + text_length < 0:
                self.scroll_position = 96

            self.manager.draw_text(
                'medium_bold', self.scroll_position, 48, Colors.YELLOW, message
            )

            self.manager.swap_canvas()
            time.sleep(GameConfig.SCROLL_SPEED)

    def _display_message_loop(self):
        """Continuously display message when weather isn't configured"""
        while True:
            # Check if season started
            if self._check_season_started():
                return

            self._display_custom_message(duration=300)

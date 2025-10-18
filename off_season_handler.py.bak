"""Handler for off-season content display"""

import time
import json
import os
import random
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

        # Load Cubs facts
        self.cubs_facts = self._load_cubs_facts()

        # Content rotation schedule (in minutes)
        self.rotation_schedule = {
            'weather': 2,      # Show weather for 2 minutes
            'message': 4       # Custom message + Cubs facts for 4 minutes
        }

        # Track when we last checked for new season
        self.last_season_check = None
        self.season_check_interval = 86400  # 24 hours in seconds

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

    def _load_cubs_facts(self):
        """Load Cubs facts from JSON file"""
        facts_path = '/home/pi/cubs_facts.json'

        # Default facts in case file doesn't exist
        default_facts = [
            "CUBS WON THE 2016 WORLD SERIES!",
            "WRIGLEY FIELD - HOME OF THE CUBS SINCE 1916",
            "FLY THE W! GO CUBS GO!",
            "108 YEARS - WORTH THE WAIT!",
            "THE FRIENDLY CONFINES"
        ]

        try:
            if os.path.exists(facts_path):
                with open(facts_path, 'r') as f:
                    data = json.load(f)
                    facts = data.get('facts', default_facts)
                    print(f"Loaded {len(facts)} Cubs facts from file")
                    return facts
            else:
                print(
                    f"Cubs facts file not found at {facts_path}, using defaults")
                return default_facts
        except Exception as e:
            print(f"Error loading Cubs facts: {e}")
            return default_facts

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
        loop_count = 0
        while True:
            loop_count += 1
            print(
                f"\n>>> Off-season loop iteration #{loop_count} at {pendulum.now().to_time_string()} <<<")

            try:
                # Reload config periodically (every loop)
                self.config = self._load_config()

                # Display mode handling
                display_mode = self.config.get('display_mode', 'auto')
                print(f"Display mode: {display_mode}")

                if display_mode == 'weather_only' and weather_enabled:
                    self._display_weather_cycle()
                elif display_mode == 'message_only':
                    self._display_message_cycle()
                else:  # auto mode
                    self._display_rotation_cycle()

                # Only check if season has started once per day
                if self._should_check_season():
                    print("Checking for new season (24hr check)...")

                    if self._check_season_started():
                        print("New season detected! Exiting off-season mode...")
                        return

                    print(f"No new season detected. Next check in 24 hours.")
                else:
                    # Calculate time until next check
                    if self.last_season_check:
                        time_since_check = time.time() - self.last_season_check
                        hours_until_next = (
                            self.season_check_interval - time_since_check) / 3600
                        print(
                            f"Skipping season check. Next check in {hours_until_next:.1f} hours.")

            except KeyboardInterrupt:
                print("Keyboard interrupt received in off-season handler")
                raise
            except Exception as e:
                print(f"Error in off-season display: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(10)

    def _should_check_season(self):
        """Determine if we should check for season start (once per day)"""
        if self.last_season_check is None:
            # First check - do it now
            return True

        time_since_check = time.time() - self.last_season_check
        return time_since_check >= self.season_check_interval

    def _check_season_started(self):
        """Check if a new season has started using the existing manager"""
        try:
            print("Checking if season has started...")

            # Use the EXISTING manager instead of creating a new one
            game_data = self.manager.get_schedule()
            has_games = bool(game_data)

            # Update last check time
            self.last_season_check = time.time()

            print(
                f"Season check complete: {'Games found' if has_games else 'No games'}")
            return has_games
        except Exception as e:
            print(f"Error checking season status: {e}")
            import traceback
            traceback.print_exc()
            # Update check time even on error to prevent hammering the API
            self.last_season_check = time.time()
            return False

    def _display_rotation_cycle(self):
        """Rotate between different content types"""
        print("=== Starting rotation cycle ===")

        # Display weather
        print("Displaying weather...")
        try:
            self.weather_display.display_weather_screen(
                duration=self.rotation_schedule['weather'] * 60
            )
            print("Weather display finished")
        except Exception as e:
            print(f"Error in weather display: {e}")
            import traceback
            traceback.print_exc()

        # Display custom message with Cubs facts
        print("Displaying custom message and Cubs facts...")
        try:
            self._display_custom_message(
                duration=self.rotation_schedule['message'] * 60
            )
            print("Custom message finished")
        except Exception as e:
            print(f"Error in custom message: {e}")
            import traceback
            traceback.print_exc()

        print("=== Rotation cycle complete ===")

    def _display_weather_cycle(self):
        """Display weather for extended period"""
        self.weather_display.display_weather_screen(duration=300)  # 5 minutes

    def _display_message_cycle(self):
        """Display message for extended period"""
        self._display_custom_message(duration=300)  # 5 minutes

    def _display_custom_message(self, duration=180):
        """Display custom scrolling message combined with random Cubs facts"""
        # Get custom message from config
        custom_message = self.config.get('custom_message', 'GO CUBS GO!')

        # Create a shuffled list of Cubs facts
        shuffled_facts = self.cubs_facts.copy()
        random.shuffle(shuffled_facts)

        # Combine custom message with shuffled Cubs facts
        all_messages = [custom_message] + shuffled_facts

        start_time = time.time()
        message_index = 0
        self.scroll_position = 96

        while time.time() - start_time < duration:
            try:
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
                    self.manager.canvas.SetImage(
                        output_image.convert("RGB"), 0, 0)
                except Exception as e:
                    # Continue without marquee image
                    pass

                # Get current message
                current_message = all_messages[message_index]

                # Scroll the message (move multiple pixels for smoother motion)
                scroll_increment = getattr(GameConfig, 'SCROLL_PIXELS', 2)
                self.scroll_position -= scroll_increment
                text_length = len(current_message) * 9

                if self.scroll_position + text_length < 0:
                    self.scroll_position = 96
                    # Move to next message
                    message_index = (message_index + 1) % len(all_messages)

                    # Re-shuffle facts when we've gone through all of them
                    if message_index == 0:
                        print("Re-shuffling Cubs facts for variety")
                        shuffled_facts = self.cubs_facts.copy()
                        random.shuffle(shuffled_facts)
                        all_messages = [custom_message] + shuffled_facts

                self.manager.draw_text(
                    'medium_bold', int(
                        self.scroll_position), 48, Colors.YELLOW, current_message
                )

                self.manager.swap_canvas()
                time.sleep(GameConfig.SCROLL_SPEED)

            except Exception as e:
                print(f"Error in custom message display: {e}")
                import traceback
                traceback.print_exc()
                break

    def _display_message_loop(self):
        """Continuously display message when weather isn't configured"""
        while True:
            # Only check if season started once per day
            if self._should_check_season():
                if self._check_season_started():
                    return

            self._display_custom_message(duration=300)

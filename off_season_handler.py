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

        # Content rotation schedule (in minutes)
        self.rotation_schedule = {
            'weather': 2,      # Show weather for 5 minutes
            'cubs_trivia': 2,  # Cubs trivia for 2 minutes
            'message': 2       # Custom message for 3 minutes
        }

        # Generate comprehensive Cubs facts
        self.cubs_facts = self._generate_cubs_facts()

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

    def _generate_cubs_facts(self):
        """Generate comprehensive list of Cubs facts and trivia"""
        facts = []

        # World Series and Championships
        championships = [
            "CUBS WON THE 2016 WORLD SERIES!",
            "108 YEARS - WORTH THE WAIT!",
            "CUBS WORLD SERIES TITLES: 1907, 1908, 2016",
            "2016 CHAMPIONS - BREAKING THE CURSE!",
            "BACK-TO-BACK WORLD SERIES 1907-1908",
            "FLY THE W! WORLD SERIES CHAMPS!",
        ]
        facts.extend(championships)

        # Wrigley Field
        wrigley_facts = [
            "WRIGLEY FIELD - HOME SINCE 1916",
            "THE FRIENDLY CONFINES",
            "WRIGLEY FIELD - 2ND OLDEST MLB PARK",
            "ICONIC IVY WALLS AT WRIGLEY",
            "WRIGLEY FIELD OPENED APRIL 23, 1914",
            "HISTORIC WRIGLEY FIELD - OVER 100 YEARS OLD",
            "CLARK & ADDISON - WRIGLEY FIELD ADDRESS",
        ]
        facts.extend(wrigley_facts)

        # Hall of Famers - Position Players
        hof_players = [
            "ERNIE BANKS - MR. CUB - 512 HOME RUNS",
            "RYNE SANDBERG - HALL OF FAME 2B",
            "BILLY WILLIAMS - 426 HOME RUNS AS A CUB",
            "RON SANTO - 337 HOME RUNS - CUBS LEGEND",
            "HACK WILSON - 191 RBIs IN 1930!",
            "FERGUSON JENKINS - CUBS ACE - HOF",
            "ANDRE DAWSON - 1987 NL MVP AS A CUB",
            "GREG MADDUX - 4X CY YOUNG WINNER",
            "KRIS BRYANT - 2016 NL MVP",
            "ANTHONY RIZZO - CUBS CAPTAIN",
        ]
        facts.extend(hof_players)

        # Team Records
        records = [
            "CUBS RECORD: 116 WINS IN 1906",
            "SAMMY SOSA - 609 HOME RUNS",
            "SAMMY SOSA - 66 HRS IN 1998",
            "KERRY WOOD - 20 STRIKEOUTS IN ONE GAME",
            "NO-HITTERS: MULTIPLE CUBS PITCHERS",
            "CUBS HAVE RETIRED 10 NUMBERS",
        ]
        facts.extend(records)

        # Traditions and Culture
        traditions = [
            "FLY THE W! GO CUBS GO!",
            "TAKE ME OUT TO THE BALL GAME - 7TH INNING",
            "HARRY CARAY - LEGENDARY CUBS ANNOUNCER",
            "CUBS FANS - MOST LOYAL IN BASEBALL",
            "BLEACHER BUMS - WRIGLEY TRADITION",
            "ROOFTOP SEATS - ONLY AT WRIGLEY!",
            "DAY GAMES AT WRIGLEY - A TRADITION",
        ]
        facts.extend(traditions)

        # Recent Era
        recent = [
            "THEO EPSTEIN - CUBS PRESIDENT 2011-2020",
            "JOE MADDON - 2016 WORLD SERIES MANAGER",
            "DAVID ROSS - CUBS MANAGER",
            "JAVY BAEZ - EL MAGO - THE MAGICIAN",
            "KYLE SCHWARBER - 2016 PLAYOFFS HERO",
            "CUBS CORE FOUR - BRYANT, RIZZO, BAEZ, CONTRERAS",
        ]
        facts.extend(recent)

        # Division Titles
        divisions = [
            "CUBS: 6 NL CENTRAL DIVISION TITLES",
            "NL CENTRAL CHAMPS 2016, 2017, 2020",
            "CUBS: 16+ NATIONAL LEAGUE PENNANTS",
        ]
        facts.extend(divisions)

        # Fun Facts
        fun_facts = [
            "CUBS PLAY IN THE NL CENTRAL DIVISION",
            "CUBS COLORS: CUBS BLUE AND RED",
            "CHICAGO CUBS EST. 1876",
            "CUBS - ONE OF MLB'S ORIGINAL TEAMS",
            "WRIGLEYVILLE - CUBS NEIGHBORHOOD",
            "GO CUBS GO - WRITTEN BY STEVE GOODMAN",
        ]
        facts.extend(fun_facts)

        return facts

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
        """Display Cubs-related content with randomized facts"""
        start_time = time.time()

        # Create a shuffled copy of facts for this display cycle
        shuffled_facts = self.cubs_facts.copy()
        random.shuffle(shuffled_facts)
        fact_index = 0

        while time.time() - start_time < duration:
            self.manager.clear_canvas()

            # Create Cubs blue background
            self.manager.fill_canvas(*Colors.CUBS_BLUE)

            # Draw Cubs logo at 28x28 centered (96 - 28 = 68, 68/2 = 34)
            try:
                cubs_logo = Image.open('./cubs28x28.png')
                output_image = Image.new("RGB", (96, 48), (0, 51, 102))
                output_image.paste(cubs_logo, (34, 2))
                self.manager.canvas.SetImage(output_image.convert("RGB"), 0, 0)
            except:
                pass

            # Draw title below logo
            self.manager.draw_text('small_bold', 12, 33,
                                   Colors.WHITE, 'CUBS HISTORY')

            # Scroll the fact at bottom
            current_fact = shuffled_facts[fact_index]

            self.scroll_position -= 1
            text_length = len(current_fact) * 7

            if self.scroll_position + text_length < 0:
                self.scroll_position = 96
                fact_index = (fact_index + 1) % len(shuffled_facts)

                # Reshuffle when we've shown all facts
                if fact_index == 0:
                    random.shuffle(shuffled_facts)

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
            self.scroll_position -= 1
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

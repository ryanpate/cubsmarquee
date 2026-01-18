"""Handler for off-season content display"""

from __future__ import annotations

import time
import json
import os
import random
import pendulum
import feedparser
from PIL import Image
from typing import TYPE_CHECKING, Any

from scoreboard_config import Colors, GameConfig, DisplayConfig, RGBColor
from weather_display import WeatherDisplay
from bears_display import BearsDisplay
from pga_display import PGADisplay
from bible_display import BibleDisplay
from newsmax_display import NewsmaxDisplay
from stock_display import StockDisplay
from spring_training_display import SpringTrainingDisplay
from flight_display import FlightDisplay

if TYPE_CHECKING:
    from scoreboard_manager import ScoreboardManager


class OffSeasonHandler:
    """Manages off-season content rotation"""

    def __init__(self, scoreboard_manager: ScoreboardManager) -> None:
        """Initialize with reference to main scoreboard manager"""
        self.manager = scoreboard_manager
        self.weather_display: WeatherDisplay = WeatherDisplay(scoreboard_manager)
        self.bears_display: BearsDisplay = BearsDisplay(scoreboard_manager)
        self.pga_display: PGADisplay = PGADisplay(scoreboard_manager)
        self.bible_display: BibleDisplay = BibleDisplay(scoreboard_manager)
        self.newsmax_display: NewsmaxDisplay = NewsmaxDisplay(scoreboard_manager)
        self.stock_display: StockDisplay = StockDisplay(scoreboard_manager)
        self.spring_training_display: SpringTrainingDisplay = SpringTrainingDisplay(scoreboard_manager)
        self.flight_display: FlightDisplay = FlightDisplay(scoreboard_manager)
        self.scroll_position: int = DisplayConfig.MATRIX_COLS

        # Load configuration
        self.config: dict[str, Any] = self._load_config()

        # Load Cubs facts
        self.cubs_facts: list[str] = self._load_cubs_facts()

        # Initialize shuffled facts list and index for persistent rotation
        self.shuffled_cubs_facts: list[str] = self.cubs_facts.copy()
        random.shuffle(self.shuffled_cubs_facts)
        self.cubs_facts_index: int = 0  # Track position in shuffled list

        # RSS news caching for Cubs
        self.cubs_news: list[str] | None = None
        self.last_cubs_news_update: float | None = None
        self.cubs_news_update_interval: int = GameConfig.NEWS_UPDATE_INTERVAL

        # RSS news caching for Bears
        self.bears_news: list[str] | None = None
        self.last_bears_news_update: float | None = None
        self.bears_news_update_interval: int = GameConfig.NEWS_UPDATE_INTERVAL

        # Classic Bears colors for news display (using centralized config)
        self.BEARS_NAVY: RGBColor = Colors.BEARS_NAVY
        self.BEARS_ORANGE: RGBColor = Colors.BEARS_ORANGE
        self.BEARS_WHITE: RGBColor = Colors.WHITE

        # Content rotation schedule (in minutes) - using centralized config
        self.rotation_schedule: dict[str, int] = {
            'weather': GameConfig.WEATHER_DISPLAY_DURATION,
            'bears': GameConfig.BEARS_DISPLAY_DURATION,
            'bears_news': GameConfig.BEARS_NEWS_DURATION,
            'pga': GameConfig.PGA_DISPLAY_DURATION,
            'pga_news': GameConfig.PGA_NEWS_DURATION if hasattr(GameConfig, 'PGA_NEWS_DURATION') else 2,
            'pga_facts': GameConfig.PGA_FACTS_DURATION,
            'cubs_news': GameConfig.CUBS_NEWS_DURATION,
            'message': GameConfig.MESSAGE_DISPLAY_DURATION,
            'bible': GameConfig.BIBLE_DISPLAY_DURATION if hasattr(GameConfig, 'BIBLE_DISPLAY_DURATION') else 3,
            'newsmax': GameConfig.NEWSMAX_DISPLAY_DURATION if hasattr(GameConfig, 'NEWSMAX_DISPLAY_DURATION') else 2,
            'stocks': GameConfig.STOCKS_DISPLAY_DURATION if hasattr(GameConfig, 'STOCKS_DISPLAY_DURATION') else 2,
            'spring_training': GameConfig.SPRING_TRAINING_DISPLAY_DURATION if hasattr(GameConfig, 'SPRING_TRAINING_DISPLAY_DURATION') else 2,
            'flights': GameConfig.FLIGHT_DISPLAY_DURATION if hasattr(GameConfig, 'FLIGHT_DISPLAY_DURATION') else 2
        }

        # Track when we last checked for new season
        self.last_season_check: float | None = None
        self.season_check_interval: int = GameConfig.SEASON_CHECK_INTERVAL

        # Cache marquee image to avoid loading every frame
        self._marquee_image: Image.Image | None = self._load_marquee_image()

    def _load_marquee_image(self) -> Image.Image | None:
        """Load and cache the marquee image"""
        try:
            marquee = Image.open('./marquee.png')
            print("Marquee image loaded and cached")
            return marquee
        except FileNotFoundError:
            print("Warning: marquee.png not found")
            return None
        except Exception as e:
            print(f"Error loading marquee image: {e}")
            return None

    def _load_config(self) -> dict[str, Any]:
        """Load configuration from JSON file"""
        config_path: str = '/home/pi/config.json'

        default_config: dict[str, Any] = {
            'zip_code': '',
            'weather_api_key': '',
            'custom_message': 'GO CUBS GO! SEE YOU NEXT SEASON!',
            'display_mode': 'auto',  # auto, weather_only, message_only
            'enable_weather': True,  # Enable/disable Weather display
            'enable_bears': True,    # Enable/disable Bears display
            'enable_bears_news': True,  # Enable/disable Bears breaking news
            'enable_pga': True,      # Enable/disable PGA Tour leaderboard
            'enable_pga_news': True,  # Enable/disable PGA Tour news
            'enable_pga_facts': True,  # Enable/disable PGA Tour facts
            'enable_cubs_facts': True,  # Enable/disable Cubs facts & message
            'enable_cubs_news': True,  # Enable/disable Cubs breaking news
            'enable_bible': True,  # Enable/disable Bible Verse of the Day
            'enable_newsmax': True,  # Enable/disable Newsmax news
            'enable_stocks': True,  # Enable/disable Stock Exchange ticker
            'enable_spring_training': True,  # Enable/disable Spring Training countdown
            'enable_flights': True,  # Enable/disable Flight Tracking display
            'flight_tracking_latitude': None,  # Latitude for flight tracking center
            'flight_tracking_longitude': None,  # Longitude for flight tracking center
            'flight_tracking_address': '',  # Address for flight tracking location
            'airlabs_api_key': ''  # AirLabs API key for flight destinations
        }

        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    loaded_config: dict[str, Any] = json.load(f)
                    # Merge with defaults
                    default_config.update(loaded_config)
        except Exception as e:
            print(f"Error loading config: {e}")

        return default_config

    def _load_cubs_facts(self) -> list[str]:
        """Load Cubs facts from JSON file"""
        facts_path: str = '/home/pi/cubs_facts.json'

        # Default facts in case file doesn't exist
        default_facts: list[str] = [
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

    def _fetch_cubs_news_rss(self):
        """
        Fetch latest Cubs/MLB news from RSS feeds
        Uses multiple sources for comprehensive coverage
        """
        news_headlines = []

        # List of RSS feed URLs for Cubs/MLB news
        rss_feeds = [
            'https://www.espn.com/espn/rss/mlb/news',
            'https://www.mlb.com/cubs/feeds/news/rss.xml',
            'https://www.cbssports.com/rss/headlines/mlb/'
        ]

        for feed_url in rss_feeds:
            try:
                print(f"Fetching Cubs news from {feed_url}")
                feed = feedparser.parse(feed_url)

                # Check if feed has entries even if bozo flag is set
                # Some feeds work fine despite bozo being True
                if not feed.entries:
                    print(f"No entries found in feed: {feed_url}")
                    if feed.bozo:
                        print(f"Feed error: {feed.get('bozo_exception', 'Unknown error')}")
                    continue

                print(f"Found {len(feed.entries)} entries in {feed_url}")

                # Extract headlines from entries
                for entry in feed.entries[:20]:  # Check top 20 from each feed for more coverage
                    try:
                        # Get title and format it
                        headline = entry.title.strip().upper()

                        # Comprehensive Cubs keyword filtering
                        # Current players (2025-2026 season) and retired Cubs legends only
                        cubs_keywords = [
                            # Team names and variations
                            'CUBS', 'CHICAGO CUBS', 'CHI CUBS', 'CUBBIES',
                            'NORTH SIDERS',

                            # Current players (2025-2026 season)
                            'CODY BELLINGER', 'BELLINGER',
                            'DANSBY SWANSON', 'SWANSON',
                            'IAN HAPP', 'HAPP',
                            'NICO HOERNER', 'HOERNER',
                            'SEIYA SUZUKI', 'SUZUKI',
                            'JUSTIN STEELE', 'STEELE',
                            'SHOTA IMANAGA', 'IMANAGA',
                            'MICHAEL BUSCH', 'BUSCH',
                            'PETE CROW-ARMSTRONG', 'PCA',
                            'MIGUEL AMAYA', 'AMAYA',
                            'ISAAC PAREDES', 'PAREDES',
                            'PATRICK WISDOM', 'WISDOM',
                            'JAMESON TAILLON', 'TAILLON',
                            'KYLE HENDRICKS', 'HENDRICKS',
                            'JAVIER ASSAD', 'ASSAD',
                            'HAYDEN WESNESKI', 'WESNESKI',
                            'PORTER HODGE', 'HODGE',

                            # Retired Cubs legends (who retired as Cubs only)
                            'ERNIE BANKS', 'BANKS', 'MR. CUB',
                            'RYNE SANDBERG', 'SANDBERG', 'RYNO',
                            'BILLY WILLIAMS', 'WILLIAMS',
                            'RON SANTO', 'SANTO',
                            'KERRY WOOD', 'WOOD',
                            'MORDECAI BROWN', 'THREE FINGER BROWN',
                            'HACK WILSON', 'WILSON',
                            'GABBY HARTNETT', 'HARTNETT',
                            'PHIL CAVARRETTA', 'CAVARRETTA',

                            # Current coaches and front office
                            'CRAIG COUNSELL', 'COUNSELL',
                            'JED HOYER', 'HOYER',

                            # Stadium and facilities
                            'WRIGLEY FIELD', 'WRIGLEY',
                            'FRIENDLY CONFINES',
                            'CLARK AND ADDISON',
                            'WAVELAND',
                            'SHEFFIELD',

                            # Division
                            'NL CENTRAL', 'NATIONAL LEAGUE'
                        ]

                        # Check if headline mentions Cubs
                        is_cubs_related = any(keyword in headline for keyword in cubs_keywords)

                        if is_cubs_related or 'cubs' in feed_url.lower():
                            # Add "CUBS NEWS:" prefix
                            formatted_headline = f"CUBS NEWS: {headline}"

                            # Avoid duplicates
                            if formatted_headline not in news_headlines:
                                news_headlines.append(formatted_headline)
                                print(f"Added Cubs headline: {headline[:50]}...")

                    except AttributeError as e:
                        print(f"Error parsing entry: {e}")
                        continue

            except Exception as e:
                print(f"Error fetching from {feed_url}: {e}")
                continue

        if not news_headlines:
            print("No Cubs news found, using fallback message")
        else:
            print(f"Total Cubs headlines collected: {len(news_headlines)}")

        # Return up to 12 news items (increased from 8 for more variety)
        return news_headlines[:12]

    def _should_update_cubs_news(self):
        """Check if Cubs news needs updating"""
        if not self.cubs_news or not self.last_cubs_news_update:
            return True
        return (time.time() - self.last_cubs_news_update) > self.cubs_news_update_interval

    def _get_live_cubs_news(self):
        """
        Get cached or fetch fresh Cubs news headlines
        Returns list of formatted news headlines
        """
        # Update news if needed
        if self._should_update_cubs_news():
            print("Fetching fresh Cubs news from RSS feeds...")

            # Display loading message while fetching
            self._display_cubs_loading("FETCHING NEWS...")
            time.sleep(0.5)  # Show loading message briefly

            self.cubs_news = self._fetch_cubs_news_rss()
            self.last_cubs_news_update = time.time()

        return self.cubs_news if self.cubs_news else []

    def _fetch_bears_news_rss(self):
        """
        Fetch latest Bears news from official Chicago Bears RSS feed
        Falls back to ESPN/CBS if official feed fails
        """
        news_headlines = []

        # Primary source: Official Chicago Bears RSS feed
        official_feed = 'https://www.chicagobears.com/rss/news'

        try:
            print(f"Fetching Bears news from official source: {official_feed}")
            feed = feedparser.parse(official_feed)

            if feed.entries:
                print(f"Found {len(feed.entries)} entries from chicagobears.com")

                for entry in feed.entries[:15]:
                    try:
                        headline = entry.title.strip().upper()
                        formatted_headline = f"BEARS NEWS - {headline}"

                        if formatted_headline not in news_headlines:
                            news_headlines.append(formatted_headline)
                            print(f"Added Bears headline: {headline[:50]}...")

                    except AttributeError as e:
                        print(f"Error parsing entry: {e}")
                        continue
            else:
                print(f"No entries from official feed")
                if feed.bozo:
                    print(f"Feed error: {feed.get('bozo_exception', 'Unknown error')}")

        except Exception as e:
            print(f"Error fetching from official Bears feed: {e}")

        # Fallback to other sources if official feed didn't provide enough news
        if len(news_headlines) < 5:
            print("Supplementing with ESPN/CBS feeds...")
            fallback_feeds = [
                'https://www.espn.com/espn/rss/nfl/news',
                'https://www.cbssports.com/rss/headlines/nfl/'
            ]

            # Keywords for filtering NFL feeds for Bears content
            bears_keywords = [
                'BEARS', 'CHICAGO BEARS', 'CHI BEARS', 'DA BEARS',
                'CALEB WILLIAMS', 'DJ MOORE', 'D.J. MOORE',
                'KEENAN ALLEN', 'ROME ODUNZE', 'COLE KMET',
                'MONTEZ SWEAT', 'TREMAINE EDMUNDS', 'JAYLON JOHNSON',
                'D\'ANDRE SWIFT', 'KYLER GORDON', 'JAQUAN BRISKER',
                'BEN JOHNSON', 'RYAN POLES',
                'SOLDIER FIELD', 'HALAS HALL'
            ]

            for feed_url in fallback_feeds:
                try:
                    print(f"Fetching Bears news from {feed_url}")
                    feed = feedparser.parse(feed_url)

                    if not feed.entries:
                        continue

                    for entry in feed.entries[:20]:
                        try:
                            headline = entry.title.strip().upper()
                            is_bears_related = any(keyword in headline for keyword in bears_keywords)

                            if is_bears_related:
                                formatted_headline = f"BEARS NEWS - {headline}"
                                if formatted_headline not in news_headlines:
                                    news_headlines.append(formatted_headline)
                                    print(f"Added Bears headline: {headline[:50]}...")

                        except AttributeError:
                            continue

                except Exception as e:
                    print(f"Error fetching from {feed_url}: {e}")
                    continue

        if not news_headlines:
            print("No Bears news found, using fallback message")
        else:
            print(f"Total Bears headlines collected: {len(news_headlines)}")

        # Return up to 12 news items
        return news_headlines[:12]

    def _should_update_bears_news(self):
        """Check if Bears news needs updating"""
        if not self.bears_news or not self.last_bears_news_update:
            return True
        return (time.time() - self.last_bears_news_update) > self.bears_news_update_interval

    def _get_live_bears_news(self):
        """
        Get cached or fetch fresh Bears news headlines
        Returns list of formatted news headlines
        """
        # Update news if needed
        if self._should_update_bears_news():
            print("Fetching fresh Bears news from RSS feeds...")

            # Display loading message while fetching
            self._display_bears_loading("FETCHING NEWS...")
            time.sleep(0.5)  # Show loading message briefly

            self.bears_news = self._fetch_bears_news_rss()
            self.last_bears_news_update = time.time()

        return self.bears_news if self.bears_news else []

    def _is_football_season(self):
        """
        Determine if it's currently football season
        Bears season typically runs September through early February
        """
        month = pendulum.now().month
        return month >= 9 or month <= 2  # Sept through Feb

    def _is_golf_season(self):
        """
        Determine if it's currently golf season
        PGA Tour season typically runs January through September
        (FedEx Cup Playoffs end in late August/early September)
        """
        month = pendulum.now().month
        return 1 <= month <= 9  # Jan through Sept

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

        # Display Bears info if it's football season and enabled
        bears_enabled = self.config.get('enable_bears', True)
        if self._is_football_season() and bears_enabled:
            print("Displaying Bears info (football season)...")
            try:
                self.bears_display.display_bears_info(
                    duration=self.rotation_schedule['bears'] * 60
                )
                print("Bears display finished")
            except Exception as e:
                print(f"Error in Bears display: {e}")
                import traceback
                traceback.print_exc()
        else:
            if not self._is_football_season():
                print("Skipping Bears display (not football season)")
            else:
                print("Skipping Bears display (disabled in config)")

        # Display weather (between Bears schedule and Bears news)
        weather_enabled = self.config.get('enable_weather', True)
        if weather_enabled:
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
        else:
            print("Skipping weather display (disabled in config)")

        # Display Bears breaking news if enabled
        bears_news_enabled = self.config.get('enable_bears_news', True)
        if bears_news_enabled:
            print("Displaying Bears breaking news...")
            try:
                self.display_bears_news(
                    duration=self.rotation_schedule['bears_news'] * 60
                )
                print("Bears news display finished")
            except Exception as e:
                print(f"Error in Bears news display: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("Skipping Bears news (disabled in config)")

        # Display PGA Tour info if it's golf season and enabled
        pga_enabled = self.config.get('enable_pga', True)
        if self._is_golf_season() and pga_enabled:
            print("Displaying PGA Tour info (golf season)...")
            try:
                self.pga_display.display_pga_info(
                    duration=self.rotation_schedule['pga'] * 60
                )
                print("PGA display finished")
            except Exception as e:
                print(f"Error in PGA display: {e}")
                import traceback
                traceback.print_exc()
        else:
            if not self._is_golf_season():
                print("Skipping PGA display (not golf season)")
            else:
                print("Skipping PGA display (disabled in config)")

        # Display PGA Tour news if it's golf season and enabled
        pga_news_enabled = self.config.get('enable_pga_news', True)
        if self._is_golf_season() and pga_news_enabled:
            print("Displaying PGA Tour news (golf season)...")
            try:
                self.pga_display.display_pga_news(
                    duration=self.rotation_schedule['pga_news'] * 60
                )
                print("PGA news display finished")
            except Exception as e:
                print(f"Error in PGA news display: {e}")
                import traceback
                traceback.print_exc()
        else:
            if not self._is_golf_season():
                print("Skipping PGA news (not golf season)")
            else:
                print("Skipping PGA news (disabled in config)")

        # Display PGA Tour facts if it's golf season and enabled
        pga_facts_enabled = self.config.get('enable_pga_facts', True)
        if self._is_golf_season() and pga_facts_enabled:
            print("Displaying PGA Tour facts (golf season)...")
            try:
                self.pga_display.display_pga_facts(
                    duration=self.rotation_schedule['pga_facts'] * 60
                )
                print("PGA facts display finished")
            except Exception as e:
                print(f"Error in PGA facts display: {e}")
                import traceback
                traceback.print_exc()
        else:
            if not self._is_golf_season():
                print("Skipping PGA facts (not golf season)")
            else:
                print("Skipping PGA facts (disabled in config)")

        # Display custom message with Cubs facts
        cubs_facts_enabled = self.config.get('enable_cubs_facts', True)
        if cubs_facts_enabled:
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
        else:
            print("Skipping Cubs facts/custom message (disabled in config)")

        # Display Spring Training countdown if enabled
        spring_training_enabled = self.config.get('enable_spring_training', True)
        if spring_training_enabled:
            print("Displaying Spring Training countdown...")
            try:
                self.spring_training_display.display_spring_training_countdown(
                    duration=self.rotation_schedule['spring_training'] * 60
                )
                print("Spring Training countdown finished")
            except Exception as e:
                print(f"Error in Spring Training countdown: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("Skipping Spring Training countdown (disabled in config)")

        # Display weather (between Cubs facts and Cubs news)
        if weather_enabled:
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
        else:
            print("Skipping weather display (disabled in config)")

        # Display Cubs breaking news if enabled
        cubs_news_enabled = self.config.get('enable_cubs_news', True)
        if cubs_news_enabled:
            print("Displaying Cubs breaking news...")
            try:
                self.display_cubs_news(
                    duration=self.rotation_schedule['cubs_news'] * 60
                )
                print("Cubs news display finished")
            except Exception as e:
                print(f"Error in Cubs news display: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("Skipping Cubs news (disabled in config)")

        # Display Bible Verse of the Day if enabled
        bible_enabled = self.config.get('enable_bible', True)
        if bible_enabled:
            print("Displaying Bible Verse of the Day...")
            try:
                self.bible_display.display_bible_verse(
                    duration=self.rotation_schedule['bible'] * 60
                )
                print("Bible verse display finished")
            except Exception as e:
                print(f"Error in Bible verse display: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("Skipping Bible verse (disabled in config)")

        # Display Newsmax news if enabled
        newsmax_enabled = self.config.get('enable_newsmax', True)
        if newsmax_enabled:
            print("Displaying Newsmax news...")
            try:
                self.newsmax_display.display_newsmax_news(
                    duration=self.rotation_schedule['newsmax'] * 60
                )
                print("Newsmax news display finished")
            except Exception as e:
                print(f"Error in Newsmax news display: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("Skipping Newsmax news (disabled in config)")

        # Display Stock Exchange ticker if enabled
        stocks_enabled = self.config.get('enable_stocks', True)
        if stocks_enabled:
            print("Displaying Stock Exchange ticker...")
            try:
                self.stock_display.display_stock_ticker(
                    duration=self.rotation_schedule['stocks'] * 60
                )
                print("Stock ticker display finished")
            except Exception as e:
                print(f"Error in Stock ticker display: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("Skipping Stock ticker (disabled in config)")

        # Display Flight Tracking if enabled
        flights_enabled = self.config.get('enable_flights', True)
        if flights_enabled:
            print("Displaying Flight Tracking...")
            try:
                self.flight_display.display_flight_info(
                    duration=self.rotation_schedule['flights'] * 60
                )
                print("Flight tracking display finished")
            except Exception as e:
                print(f"Error in Flight tracking display: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("Skipping Flight tracking (disabled in config)")

        print("=== Rotation cycle complete ===")

    def _display_weather_cycle(self):
        """Display weather for extended period"""
        self.weather_display.display_weather_screen(duration=300)  # 5 minutes

    def _display_message_cycle(self):
        """Display message for extended period"""
        self._display_custom_message(duration=300)  # 5 minutes

    def _display_bears_loading(self, message="FETCHING NEWS..."):
        """Display loading message with Bears sweater header"""
        self.manager.clear_canvas()

        # Draw the classic Bears sweater header
        # Fill entire background with Bears navy
        for y in range(48):
            for x in range(96):
                self.manager.draw_pixel(x, y, *self.BEARS_NAVY)

        # Top orange stripe (3 pixels tall)
        for y in range(4, 7):
            for x in range(96):
                self.manager.draw_pixel(x, y, *self.BEARS_ORANGE)

        # Bottom orange stripe (3 pixels tall)
        for y in range(22, 25):
            for x in range(96):
                self.manager.draw_pixel(x, y, *self.BEARS_ORANGE)

        # Draw "CHICAGO BEARS" text in white, centered between stripes
        self.manager.draw_text('small_bold', 9, 19,
                               self.BEARS_WHITE, 'CHICAGO BEARS')

        # Display loading message centered
        message_width = len(message) * 5
        x_pos = max(0, (96 - message_width) // 2)
        self.manager.draw_text('small_bold', x_pos, 42,
                               self.BEARS_WHITE, message)

        self.manager.swap_canvas()

    def _display_cubs_loading(self, message="FETCHING NEWS..."):
        """Display loading message with Cubs logo"""
        self.manager.clear_canvas()

        # Create gradient background (same as Cubs facts display)
        for y in range(48):
            # Gradient from Cubs blue to slightly lighter blue
            blue_intensity = int(102 + (y * 0.5))
            for x in range(96):
                self.manager.draw_pixel(x, y, 0, 51, blue_intensity)

        # Display cached marquee image (Cubs logo) at the top
        if self._marquee_image is not None:
            output_image = Image.new("RGB", (96, 48))
            output_image.paste(self._marquee_image, (0, 0))
            self.manager.canvas.SetImage(
                output_image.convert("RGB"), 0, 0)

        # Display loading message centered at bottom
        message_width = len(message) * 5
        x_pos = max(0, (96 - message_width) // 2)
        self.manager.draw_text('small_bold', x_pos, 48,
                               Colors.YELLOW, message)

        self.manager.swap_canvas()

    def _draw_sweater_header(self):
        """Draw the classic Bears sweater header with orange stripes"""
        # Fill entire background with Bears navy
        for y in range(48):
            for x in range(96):
                self.manager.draw_pixel(x, y, *self.BEARS_NAVY)

        # Top orange stripe (3 pixels tall)
        for y in range(4, 7):
            for x in range(96):
                self.manager.draw_pixel(x, y, *self.BEARS_ORANGE)

        # Bottom orange stripe (3 pixels tall)
        for y in range(22, 25):
            for x in range(96):
                self.manager.draw_pixel(x, y, *self.BEARS_ORANGE)

        # Draw "CHICAGO BEARS" text in white, centered between stripes
        self.manager.draw_text('small_bold', 9, 19,
                               self.BEARS_WHITE, 'CHICAGO BEARS')

    def display_bears_news(self, duration=180):
        """Display scrolling Bears breaking news with sweater header"""
        # Fetch live Bears news headlines
        live_news = self._get_live_bears_news()

        # If no news available, show message
        if not live_news:
            live_news = ["BREAKING NEWS - STAY TUNED FOR THE LATEST BEARS UPDATES!"]

        start_time = time.time()
        message_index = 0
        self.scroll_position = 96

        while time.time() - start_time < duration:
            try:
                self.manager.clear_canvas()

                # Draw the classic Bears sweater header
                self._draw_sweater_header()

                # Get current news headline
                current_headline = live_news[message_index]

                # Scroll the message
                scroll_increment = getattr(GameConfig, 'SCROLL_PIXELS', 2)
                self.scroll_position -= scroll_increment
                text_length = len(current_headline) * 9

                if self.scroll_position + text_length < 0:
                    self.scroll_position = 96
                    # Move to next headline
                    message_index = (message_index + 1) % len(live_news)

                    # Refresh news when we've gone through all headlines
                    if message_index == 0:
                        print("Refreshing Bears news")
                        # Fetch fresh news (checks cache internally)
                        fresh_news = self._get_live_bears_news()
                        if fresh_news:
                            live_news = fresh_news

                # Draw scrolling Bears news below the sweater header in white
                self.manager.draw_text(
                    'medium_bold', int(self.scroll_position), 44,
                    self.BEARS_WHITE, current_headline
                )

                self.manager.swap_canvas()

                # Use GameConfig SCROLL_SPEED for consistent timing
                time.sleep(GameConfig.SCROLL_SPEED)

            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"Error in Bears news display: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(1)

    def display_cubs_news(self, duration=180):
        """Display scrolling Cubs breaking news with Cubs logo"""
        # Fetch live Cubs news headlines
        live_news = self._get_live_cubs_news()

        # If no news available, show message
        if not live_news:
            live_news = ["CUBS NEWS: STAY TUNED FOR THE LATEST CUBS UPDATES!"]

        start_time = time.time()
        message_index = 0
        self.scroll_position = 96

        while time.time() - start_time < duration:
            try:
                self.manager.clear_canvas()

                # Create gradient background (same as Cubs facts display)
                for y in range(48):
                    # Gradient from Cubs blue to slightly lighter blue
                    blue_intensity = int(102 + (y * 0.5))
                    for x in range(96):
                        self.manager.draw_pixel(x, y, 0, 51, blue_intensity)

                # Display cached marquee image (Cubs logo) at the top
                if self._marquee_image is not None:
                    output_image = Image.new("RGB", (96, 48))
                    output_image.paste(self._marquee_image, (0, 0))
                    self.manager.canvas.SetImage(
                        output_image.convert("RGB"), 0, 0)

                # Get current news headline
                current_headline = live_news[message_index]

                # Scroll the message
                scroll_increment = getattr(GameConfig, 'SCROLL_PIXELS', 2)
                self.scroll_position -= scroll_increment
                text_length = len(current_headline) * 9

                if self.scroll_position + text_length < 0:
                    self.scroll_position = 96
                    # Move to next headline
                    message_index = (message_index + 1) % len(live_news)

                    # Refresh news when we've gone through all headlines
                    if message_index == 0:
                        print("Refreshing Cubs news")
                        # Fetch fresh news (checks cache internally)
                        fresh_news = self._get_live_cubs_news()
                        if fresh_news:
                            live_news = fresh_news

                # Draw scrolling Cubs news at the bottom (same as Cubs facts)
                self.manager.draw_text(
                    'medium_bold', int(self.scroll_position), 48,
                    Colors.YELLOW, current_headline
                )

                self.manager.swap_canvas()

                # Use GameConfig SCROLL_SPEED for consistent timing
                time.sleep(GameConfig.SCROLL_SPEED)

            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"Error in Cubs news display: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(1)

    def _display_custom_message(self, duration=180):
        """Display custom scrolling message combined with random Cubs facts"""
        # Get custom message from config
        custom_message = self.config.get('custom_message', 'GO CUBS GO!')

        start_time = time.time()
        self.scroll_position = 96

        # Show custom message only once at the beginning of this display cycle
        showing_custom = True
        custom_shown = False

        while time.time() - start_time < duration:
            try:
                self.manager.clear_canvas()

                # Create gradient background
                for y in range(48):
                    # Gradient from Cubs blue to slightly lighter blue
                    blue_intensity = int(102 + (y * 0.5))
                    for x in range(96):
                        self.manager.draw_pixel(x, y, 0, 51, blue_intensity)

                # Display cached marquee image if available
                if self._marquee_image is not None:
                    output_image = Image.new("RGB", (96, 48))
                    output_image.paste(self._marquee_image, (0, 0))
                    self.manager.canvas.SetImage(
                        output_image.convert("RGB"), 0, 0)

                # Get current message - custom message once, then facts continuously
                if showing_custom and not custom_shown:
                    current_message = custom_message
                else:
                    current_message = self.shuffled_cubs_facts[self.cubs_facts_index]
                    showing_custom = False

                # Scroll the message (move multiple pixels for smoother motion)
                scroll_increment = getattr(GameConfig, 'SCROLL_PIXELS', 2)
                self.scroll_position -= scroll_increment
                text_length = len(current_message) * 9

                if self.scroll_position + text_length < 0:
                    self.scroll_position = 96

                    # If we just finished showing the custom message
                    if showing_custom and not custom_shown:
                        custom_shown = True
                        showing_custom = False
                    else:
                        # Move to next fact
                        self.cubs_facts_index += 1

                        # Check if we've shown all facts
                        if self.cubs_facts_index >= len(self.shuffled_cubs_facts):
                            print(f"Completed full cycle of {len(self.shuffled_cubs_facts)} Cubs facts - re-shuffling")
                            # Re-shuffle for next cycle
                            self.shuffled_cubs_facts = self.cubs_facts.copy()
                            random.shuffle(self.shuffled_cubs_facts)
                            self.cubs_facts_index = 0

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

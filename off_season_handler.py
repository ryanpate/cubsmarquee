"""Handler for off-season content display"""

from __future__ import annotations

import time
import json
import random
import pendulum
from PIL import Image
from typing import TYPE_CHECKING, Any

from scoreboard_config import Colors, GameConfig, DisplayConfig, RGBColor, get_scroll_delay, load_user_config, create_team_gradient_background
from teams import get_active_team, get_active_nfl_team, apply_team_defaults, data_path_candidates
from rss_fetch import fetch_feed, is_probably_english
from weather_display import WeatherDisplay
from bears_display import BearsDisplay
from pga_display import PGADisplay
from bible_display import BibleDisplay
from newsmax_display import NewsmaxDisplay
from stock_display import StockDisplay
from spring_training_display import SpringTrainingDisplay
from allstar_display import AllStarDisplay
from flight_display import FlightDisplay
from clock_display import WrigleyClockDisplay
from cubs_history_display import TeamHistoryDisplay
from sky_display import SkyDisplay
from iss_display import ISSDisplay
from celebration_display import CelebrationDisplay

if TYPE_CHECKING:
    from scoreboard_manager import ScoreboardManager


class OffSeasonHandler:
    """Manages off-season content rotation"""

    def __init__(self, scoreboard_manager: ScoreboardManager) -> None:
        """Initialize with reference to main scoreboard manager"""
        self.manager = scoreboard_manager
        self.team = get_active_team()
        self.weather_display: WeatherDisplay = WeatherDisplay(scoreboard_manager)
        self.bears_display: BearsDisplay = BearsDisplay(scoreboard_manager)
        self.pga_display: PGADisplay = PGADisplay(scoreboard_manager)
        self.bible_display: BibleDisplay = BibleDisplay(scoreboard_manager)
        self.newsmax_display: NewsmaxDisplay = NewsmaxDisplay(scoreboard_manager)
        self.stock_display: StockDisplay = StockDisplay(scoreboard_manager)
        self.spring_training_display: SpringTrainingDisplay = SpringTrainingDisplay(scoreboard_manager)
        self.allstar_display: AllStarDisplay = AllStarDisplay(scoreboard_manager)
        self.flight_display: FlightDisplay = FlightDisplay(scoreboard_manager)
        self.clock_display: WrigleyClockDisplay = WrigleyClockDisplay(
            scoreboard_manager, self.weather_display)
        self.cubs_history_display: TeamHistoryDisplay = TeamHistoryDisplay(scoreboard_manager)
        self.sky_display: SkyDisplay = SkyDisplay(scoreboard_manager, self.weather_display)
        self.iss_display: ISSDisplay = ISSDisplay(
            scoreboard_manager, self.flight_display.latitude,
            self.flight_display.longitude)
        self.celebration_display: CelebrationDisplay = CelebrationDisplay(scoreboard_manager)
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

        # RSS news caching for the NFL team
        self.bears_news: list[str] | None = None
        self.last_bears_news_update: float | None = None
        self.bears_news_update_interval: int = GameConfig.NEWS_UPDATE_INTERVAL

        # NFL pack drives the football news theming (colors, feed, prefix)
        self.nfl_team = get_active_nfl_team()
        self.NFL_PRIMARY: RGBColor = self.nfl_team.primary_color
        self.NFL_ACCENT: RGBColor = self.nfl_team.accent_color

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
            'bible_facts': GameConfig.BIBLE_FACTS_DURATION if hasattr(GameConfig, 'BIBLE_FACTS_DURATION') else 2,
            'newsmax': GameConfig.NEWSMAX_DISPLAY_DURATION if hasattr(GameConfig, 'NEWSMAX_DISPLAY_DURATION') else 2,
            'stocks': GameConfig.STOCKS_DISPLAY_DURATION if hasattr(GameConfig, 'STOCKS_DISPLAY_DURATION') else 2,
            'spring_training': GameConfig.SPRING_TRAINING_DISPLAY_DURATION if hasattr(GameConfig, 'SPRING_TRAINING_DISPLAY_DURATION') else 2,
            'allstar': 2,  # All-Star break: Derby promo / ASG countdown

            'flights': GameConfig.FLIGHT_DISPLAY_DURATION if hasattr(GameConfig, 'FLIGHT_DISPLAY_DURATION') else 2,
            'clock': GameConfig.CLOCK_DISPLAY_DURATION,
            'cubs_history': GameConfig.CUBS_HISTORY_DURATION,
            'sky': GameConfig.SKY_DISPLAY_DURATION,
            'iss': GameConfig.ISS_DISPLAY_DURATION,
            'celebration': GameConfig.CELEBRATION_DURATION
        }

        # Track when we last checked for new season
        self.last_season_check: float | None = None
        self.season_check_interval: int = GameConfig.SEASON_CHECK_INTERVAL

        # Cache marquee image to avoid loading every frame
        self._marquee_image: Image.Image | None = self._load_marquee_image()

        # Pre-generate cached background images for performance
        self._cubs_gradient_bg: Image.Image = self._create_cubs_gradient_background()
        self._bears_sweater_bg: Image.Image = self._create_bears_sweater_background()

    def _load_marquee_image(self) -> Image.Image | None:
        """Load and cache the marquee image"""
        try:
            marquee = Image.open(self.team.marquee_path)
            print("Marquee image loaded and cached")
            return marquee
        except FileNotFoundError:
            print(f"Warning: {self.team.marquee_path} not found")
            return None
        except Exception as e:
            print(f"Error loading marquee image: {e}")
            return None

    def _create_cubs_gradient_background(self) -> Image.Image:
        """Pre-generate team gradient background image for performance"""
        img = create_team_gradient_background(self.team.primary_color)
        print("Team gradient background cached (with black scroll area)")
        return img

    def _create_bears_sweater_background(self) -> Image.Image:
        """Pre-generate compact Bears sweater header background for performance"""
        img = Image.new("RGB", (96, 48), self.NFL_PRIMARY)
        pixels = img.load()
        for y in (0, 1, 10, 11):
            for x in range(96):
                pixels[x, y] = self.NFL_ACCENT
        print("NFL sweater background cached")
        return img

    def _load_config(self) -> dict[str, Any]:
        """Load configuration from JSON file"""
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
            'enable_bible_facts': True,  # Enable/disable Bible Facts
            'enable_newsmax': True,  # Enable/disable Newsmax news
            'enable_stocks': True,  # Enable/disable Stock Exchange ticker
            'enable_spring_training': True,  # Enable/disable Spring Training countdown
            'enable_allstar': True,  # All-Star break screens (Derby promo, ASG countdown)
            'enable_playoff_race': True,  # Enable/disable playoff race display
            'enable_flights': True,  # Enable/disable Flight Tracking display
            'enable_flight_radar': True,  # Enable/disable radar scope view
            'enable_clock': True,  # Enable/disable Wrigley scoreboard clock
            'enable_cubs_history': True,  # Enable/disable Today in Cubs History
            'enable_sky': True,  # Enable/disable Sun & Sky display
            'enable_iss': True,  # Enable/disable ISS tracker display
            'enable_celebrations': True,  # Enable/disable celebration days
            'flights_between_displays': False,  # Show flight interstitial between every rotation segment
            'flight_tracking_latitude': None,  # Latitude for flight tracking center
            'flight_tracking_longitude': None,  # Longitude for flight tracking center
            'flight_tracking_address': '',  # Address for flight tracking location
            'airlabs_api_key': '',  # AirLabs API key for flight destinations (optional)
            'adsb_receiver_url': GameConfig.ADSB_RECEIVER_URL,  # Local ADS-B receiver URL
            'flight_max_range_nm': GameConfig.FLIGHT_MAX_RANGE_NM  # Max range in nautical miles
        }

        # Merge with defaults (cached loader; only re-parses on file change)
        user_config = load_user_config()
        default_config = apply_team_defaults(default_config, user_config)
        default_config.update(user_config)
        return default_config

    def _load_cubs_facts(self) -> list[str]:
        """Load team facts from the active team pack's JSON file"""
        default_facts: list[str] = [
            f"GO {self.team.short_name.upper()}!",
            f"{self.team.name.upper()} BASEBALL",
        ]
        for facts_path in data_path_candidates(self.team.facts_basename):
            try:
                with open(facts_path, 'r') as f:
                    facts = json.load(f).get('facts', [])
                if facts:
                    print(f"Loaded {len(facts)} {self.team.short_name} "
                          f"facts from {facts_path}")
                    return facts
            except (OSError, json.JSONDecodeError) as e:
                continue
        print(f"{self.team.facts_basename} not found, using defaults")
        return default_facts

    def _fetch_cubs_news_rss(self):
        """
        Fetch latest Cubs/MLB news from RSS feeds
        Uses multiple sources for comprehensive coverage
        """
        news_headlines = []

        # List of RSS feed URLs for team/MLB news
        rss_feeds = [
            'https://www.espn.com/espn/rss/mlb/news',
            self.team.news_rss_url,
            'https://www.cbssports.com/rss/headlines/mlb/'
        ]

        for feed_url in rss_feeds:
            try:
                print(f"Fetching {self.team.short_name} news from {feed_url}")
                feed = fetch_feed(feed_url)

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

                        # Team keyword filtering (current players, retired
                        # legends, stadium, etc.) from the active team pack
                        is_cubs_related = any(
                            keyword in headline
                            for keyword in self.team.news_keywords)

                        if ((is_cubs_related or self.team.slug in feed_url.lower())
                                and is_probably_english(headline)):
                            # Add team news prefix
                            formatted_headline = f"{self.team.short_name.upper()} NEWS: {headline}"

                            # Avoid duplicates
                            if formatted_headline not in news_headlines:
                                news_headlines.append(formatted_headline)
                                print(f"Added {self.team.short_name} headline: {headline[:50]}...")

                    except AttributeError as e:
                        print(f"Error parsing entry: {e}")
                        continue

            except Exception as e:
                print(f"Error fetching from {feed_url}: {e}")
                continue

        if not news_headlines:
            print(f"No {self.team.short_name} news found, using fallback message")
        else:
            print(f"Total {self.team.short_name} headlines collected: {len(news_headlines)}")

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
        Fetch latest news for the active NFL team from its official RSS feed
        Falls back to ESPN/CBS if official feed fails
        """
        news_headlines = []

        # Primary source: Official NFL team RSS feed
        official_feed = self.nfl_team.news_rss_url
        news_prefix = f"{self.nfl_team.short_name.upper()} NEWS - "

        try:
            print(f"Fetching {self.nfl_team.short_name} news from official source: {official_feed}")
            feed = fetch_feed(official_feed)

            if feed.entries:
                print(f"Found {len(feed.entries)} entries from {self.nfl_team.short_name}")

                for entry in feed.entries[:15]:
                    try:
                        headline = entry.title.strip().upper()
                        if not is_probably_english(headline):
                            continue
                        formatted_headline = f"{news_prefix}{headline}"

                        if formatted_headline not in news_headlines:
                            news_headlines.append(formatted_headline)
                            print(f"Added {self.nfl_team.short_name} headline: {headline[:50]}...")

                    except AttributeError as e:
                        print(f"Error parsing entry: {e}")
                        continue
            else:
                print(f"No entries from official feed")
                if feed.bozo:
                    print(f"Feed error: {feed.get('bozo_exception', 'Unknown error')}")

        except Exception as e:
            print(f"Error fetching from official {self.nfl_team.short_name} feed: {e}")

        # Fallback to other sources if official feed didn't provide enough news
        if len(news_headlines) < 5:
            print("Supplementing with ESPN/CBS feeds...")
            fallback_feeds = [
                'https://www.espn.com/espn/rss/nfl/news',
                'https://www.cbssports.com/rss/headlines/nfl/'
            ]

            for feed_url in fallback_feeds:
                try:
                    print(f"Fetching {self.nfl_team.short_name} news from {feed_url}")
                    feed = fetch_feed(feed_url)

                    if not feed.entries:
                        continue

                    for entry in feed.entries[:20]:
                        try:
                            headline = entry.title.strip().upper()
                            is_team_related = any(keyword in headline for keyword in self.nfl_team.news_keywords)

                            if is_team_related and is_probably_english(headline):
                                formatted_headline = f"{news_prefix}{headline}"
                                if formatted_headline not in news_headlines:
                                    news_headlines.append(formatted_headline)
                                    print(f"Added {self.nfl_team.short_name} headline: {headline[:50]}...")

                        except AttributeError:
                            continue

                except Exception as e:
                    print(f"Error fetching from {feed_url}: {e}")
                    continue

        if not news_headlines:
            print(f"No {self.nfl_team.short_name} news found, using fallback message")
        else:
            print(f"Total {self.nfl_team.short_name} headlines collected: {len(news_headlines)}")

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
            if not self._display_message_loop():
                return  # season started
            # Weather was configured via the admin panel - fall through
            # into the full rotation loop
            self.config = self._load_config()

        # Main rotation loop
        loop_count = 0
        while True:
            loop_count += 1
            print(
                f"\n>>> Off-season loop iteration #{loop_count} at {pendulum.now().to_time_string()} <<<")

            try:
                # Reload config periodically (every loop)
                self.config = self._load_config()
                weather_enabled = (
                    self.config.get('zip_code') and
                    self.config.get('weather_api_key')
                )

                # Display mode handling
                display_mode = self.config.get('display_mode', 'auto')
                print(f"Display mode: {display_mode}")

                if display_mode == 'weather_only' and weather_enabled:
                    self._display_weather_cycle()
                elif display_mode == 'message_only':
                    self._display_message_cycle()
                else:  # auto mode
                    self._display_rotation_cycle()

                # Skip season check when user has forced no-games mode
                if display_mode == 'no_games':
                    print("Display mode 'no_games' - skipping season check")
                # Only check if season has started once per day
                elif self._should_check_season():
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

    def _display_rotation_cycle(self, between_callback=None):
        """Rotate between different content types.

        If between_callback is provided, it's called after each segment
        that actually displayed something (skipped/no-op segments don't
        trigger the interlude, so the game-over screen can't chain).
        When it returns True, the rotation exits early.
        """
        print("=== Starting rotation cycle ===")

        # If the user enabled "flights between every screen", show a brief
        # flight interstitial between each rotation segment (in addition to
        # the normal flight slot at the end of the cycle).
        flights_between = self.config.get('flights_between_displays', False)
        flights_enabled = self.config.get('enable_flights', True)
        flight_interstitial_sec = 45

        def _tick():
            """Run the between-segment interstitial (if enabled) and
            optionally invoke the external between_callback. Returns True
            to abort the rotation."""
            if flights_between and flights_enabled:
                try:
                    self.flight_display.display_flight_info(
                        duration=flight_interstitial_sec
                    )
                except Exception as e:
                    print(f"Flight interstitial error: {e}")
            if between_callback is not None:
                return bool(between_callback())
            return False

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
            if _tick():
                return
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
            if _tick():
                return
        else:
            print("Skipping weather display (disabled in config)")

        # Display the Wrigley clock if enabled
        if self.config.get('enable_clock', True):
            print("Displaying Wrigley clock...")
            try:
                self.clock_display.display_clock(
                    duration=self.rotation_schedule['clock'] * 60
                )
                print("Clock display finished")
            except Exception as e:
                print(f"Error in clock display: {e}")
                import traceback
                traceback.print_exc()
            if _tick():
                return
        else:
            print("Skipping clock (disabled in config)")

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
            if _tick():
                return
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
            if _tick():
                return
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
            if _tick():
                return
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
            if _tick():
                return
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
            if _tick():
                return
        else:
            print("Skipping Cubs facts/custom message (disabled in config)")

        # Celebration days (birthdays etc. from config; skips quietly
        # when today isn't one)
        if self.config.get('enable_celebrations', True):
            try:
                if self.celebration_display.display_celebrations(
                        duration=self.rotation_schedule['celebration'] * 60):
                    print("Celebration display finished")
                    if _tick():
                        return
            except Exception as e:
                print(f"Error in celebration display: {e}")
                import traceback
                traceback.print_exc()

        # Display milestone countdown (Spring Training, then Opening Day
        # once Spring Training is underway) if enabled
        spring_training_enabled = self.config.get('enable_spring_training', True)
        if spring_training_enabled:
            print("Displaying season countdown...")
            try:
                self.spring_training_display.display_spring_training_countdown(
                    duration=self.rotation_schedule['spring_training'] * 60
                )
                print("Season countdown finished")
            except Exception as e:
                print(f"Error in season countdown: {e}")
                import traceback
                traceback.print_exc()
            if _tick():
                return
        else:
            print("Skipping season countdown (disabled in config)")

        # All-Star break: Derby promo / ASG pregame countdown. display_promo
        # is a no-op outside the two-day window, so this segment costs
        # nothing the rest of the year - and never triggers the
        # between-segment interlude (it cannot report whether it drew).
        if self.config.get('enable_allstar', True):
            try:
                self.allstar_display.display_promo(
                    duration=self.rotation_schedule['allstar'] * 60)
            except Exception as e:
                print(f"Error in All-Star display: {e}")
                import traceback
                traceback.print_exc()

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
            if _tick():
                return
        else:
            print("Skipping weather display (disabled in config)")

        # Display sun/moon sky screen if enabled
        if self.config.get('enable_sky', True):
            print("Displaying sun & sky...")
            try:
                self.sky_display.display_sky(
                    duration=self.rotation_schedule['sky'] * 60
                )
                print("Sky display finished")
            except Exception as e:
                print(f"Error in sky display: {e}")
                import traceback
                traceback.print_exc()
            if _tick():
                return
        else:
            print("Skipping sky display (disabled in config)")

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
            if _tick():
                return
        else:
            print("Skipping Cubs news (disabled in config)")

        # Display today in Cubs history if enabled (skips quietly on
        # dates with no entry)
        if self.config.get('enable_cubs_history', True):
            try:
                if self.cubs_history_display.display_history(
                        duration=self.rotation_schedule['cubs_history'] * 60):
                    print("Cubs history display finished")
                    if _tick():
                        return
            except Exception as e:
                print(f"Error in Cubs history display: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("Skipping Cubs history (disabled in config)")

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
            if _tick():
                return
        else:
            print("Skipping Bible verse (disabled in config)")

        # Display Bible Facts if enabled
        bible_facts_enabled = self.config.get('enable_bible_facts', True)
        if bible_facts_enabled:
            print("Displaying Bible Facts...")
            try:
                self.bible_display.display_bible_facts(
                    duration=self.rotation_schedule['bible_facts'] * 60
                )
                print("Bible facts display finished")
            except Exception as e:
                print(f"Error in Bible facts display: {e}")
                import traceback
                traceback.print_exc()
            if _tick():
                return
        else:
            print("Skipping Bible facts (disabled in config)")

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
            if _tick():
                return
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
            if _tick():
                return
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
            if _tick():
                return
        else:
            print("Skipping Flight tracking (disabled in config)")

        # Display the ISS tracker if enabled (skips when the API or a
        # home location is unavailable)
        if self.config.get('enable_iss', True):
            try:
                if self.iss_display.display_iss(
                        duration=self.rotation_schedule['iss'] * 60):
                    print("ISS display finished")
                    if _tick():
                        return
            except Exception as e:
                print(f"Error in ISS display: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("Skipping ISS tracker (disabled in config)")

        print("=== Rotation cycle complete ===")

    def _display_weather_cycle(self):
        """Display weather for extended period"""
        self.weather_display.display_weather_screen(duration=300)  # 5 minutes

    def _display_message_cycle(self):
        """Display message for extended period"""
        self._display_custom_message(duration=300)  # 5 minutes

    def _display_bears_loading(self, message="FETCHING NEWS..."):
        """Display loading message with Bears sweater header using cached image"""
        self.manager.clear_canvas()

        self._draw_sweater_header()

        # Display loading message centered in the content area
        message_width = len(message) * 5
        x_pos = max(0, (96 - message_width) // 2)
        self.manager.draw_text('small_bold', x_pos, 32,
                               Colors.WHITE, message)

        self.manager.swap_canvas()

    def _display_cubs_loading(self, message="FETCHING NEWS..."):
        """Display loading message with Cubs logo using cached background"""
        self.manager.clear_canvas()

        # Use pre-generated cached gradient for performance
        output_image = self._cubs_gradient_bg.copy()

        # Paste cached marquee image (Cubs logo) at the top if available
        if self._marquee_image is not None:
            output_image.paste(self._marquee_image, (0, 0))

        self.manager.set_image(output_image.convert("RGB"), 0, 0)

        # Display loading message centered at bottom
        message_width = len(message) * 5
        x_pos = max(0, (96 - message_width) // 2)
        self.manager.draw_text('small_bold', x_pos, 48,
                               Colors.YELLOW, message)

        self.manager.swap_canvas()

    def _draw_sweater_header(self):
        """Draw the compact sweater header using the cached image"""
        self.manager.set_image(self._bears_sweater_bg, 0, 0)
        header = self.nfl_team.header_name
        x = max(0, (96 - len(header) * 5) // 2)
        self.manager.draw_text('tiny_bold', x, 9, Colors.WHITE, header)

    def display_bears_news(self, duration=180):
        """Display scrolling Bears breaking news with sweater header"""
        # Fetch live Bears news headlines
        live_news = self._get_live_bears_news()

        # If no news available, show message
        if not live_news:
            live_news = [f"BREAKING NEWS - STAY TUNED FOR THE LATEST {self.nfl_team.short_name.upper()} UPDATES!"]

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

                # Scroll smoothly 1 pixel at a time (like Spring Training)
                self.scroll_position -= 1
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

                # Draw scrolling text
                self.manager.draw_text(
                    'medium_bold', int(self.scroll_position), 32,
                    Colors.WHITE, current_headline
                )

                self.manager.swap_canvas()
                # Load config after drawing (like Spring Training)
                fresh_config = self._load_config()
                scroll_delay = get_scroll_delay(fresh_config.get('scroll_speed_bears_news', 5))
                time.sleep(scroll_delay)

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
            team_name = self.team.short_name.upper()
            live_news = [f"{team_name} NEWS: STAY TUNED FOR THE LATEST {team_name} UPDATES!"]

        start_time = time.time()
        message_index = 0
        self.scroll_position = 96

        while time.time() - start_time < duration:
            try:
                self.manager.clear_canvas()

                # Use pre-generated cached gradient for performance
                output_image = self._cubs_gradient_bg.copy()

                # Paste cached marquee image (Cubs logo) at the top if available
                if self._marquee_image is not None:
                    output_image.paste(self._marquee_image, (0, 0))

                self.manager.set_image(output_image.convert("RGB"), 0, 0)

                # Get current news headline
                current_headline = live_news[message_index]

                # Scroll smoothly 1 pixel at a time (like Spring Training)
                self.scroll_position -= 1
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

                # Draw scrolling text
                self.manager.draw_text(
                    'medium_bold', int(self.scroll_position), 48,
                    Colors.YELLOW, current_headline
                )

                self.manager.swap_canvas()
                # Load config after drawing (like Spring Training)
                fresh_config = self._load_config()
                scroll_delay = get_scroll_delay(fresh_config.get('scroll_speed_cubs_news', 5))
                time.sleep(scroll_delay)

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
        custom_message = self.config.get(
            'custom_message', f'GO {self.team.short_name.upper()} GO!')

        start_time = time.time()
        self.scroll_position = 96

        # Show custom message only once at the beginning of this display cycle
        showing_custom = True
        custom_shown = False

        while time.time() - start_time < duration:
            try:
                self.manager.clear_canvas()

                # Use pre-generated cached gradient for performance
                output_image = self._cubs_gradient_bg.copy()

                # Paste cached marquee image at the top if available
                if self._marquee_image is not None:
                    output_image.paste(self._marquee_image, (0, 0))

                self.manager.set_image(output_image.convert("RGB"), 0, 0)

                # Get current message - custom message once, then facts continuously
                if showing_custom and not custom_shown:
                    current_message = custom_message
                else:
                    current_message = self.shuffled_cubs_facts[self.cubs_facts_index]
                    showing_custom = False

                # Scroll smoothly 1 pixel at a time (like Spring Training)
                self.scroll_position -= 1
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

                # Draw scrolling text
                self.manager.draw_text(
                    'medium_bold', int(self.scroll_position), 48,
                    Colors.YELLOW, current_message
                )

                self.manager.swap_canvas()
                # Load config after drawing (like Spring Training)
                fresh_config = self._load_config()
                scroll_delay = get_scroll_delay(fresh_config.get('scroll_speed_cubs_facts', 5))
                time.sleep(scroll_delay)

            except Exception as e:
                print(f"Error in custom message display: {e}")
                import traceback
                traceback.print_exc()
                break

    def _display_message_loop(self):
        """Continuously display message when weather isn't configured.

        Returns True if weather config was added (via the admin panel),
        False if a new season started.
        """
        while True:
            # Only check if season started once per day
            if self._should_check_season():
                if self._check_season_started():
                    return False

            # Pick up weather config added via the admin panel without
            # requiring a process restart
            config = self._load_config()
            if config.get('zip_code') and config.get('weather_api_key'):
                print("Weather configuration detected - switching to full rotation")
                return True

            self._display_custom_message(duration=300)

"""USA Today news display - Top Stories RSS, white background, navy text"""

from __future__ import annotations

import re
import time
import os
from PIL import Image
from typing import TYPE_CHECKING, Any

from scoreboard_config import Colors, GameConfig, DisplayConfig, RGBColor, get_scroll_delay, load_user_config
from rss_fetch import fetch_feed

if TYPE_CHECKING:
    from scoreboard_manager import ScoreboardManager


class UsaTodayDisplay:
    """Handles USA Today headlines display with RSS feed"""

    RSS_URL = (
        'https://news.google.com/rss/search?q=site:usatoday.com+when:1d'
        '&hl=en-US&gl=US&ceid=US:en'
    )

    def __init__(self, scoreboard_manager: ScoreboardManager) -> None:
        """Initialize USA Today display"""
        self.manager = scoreboard_manager
        self.scroll_position: int = DisplayConfig.MATRIX_COLS

        # USA Today colors - white background, brand blue, navy text
        self.USATODAY_WHITE: RGBColor = Colors.WHITE
        self.USATODAY_BLUE: RGBColor = (0, 155, 255)   # brand circle blue
        self.USATODAY_NAVY: RGBColor = (20, 40, 80)    # headline text

        # Load USA Today logo
        self.usatoday_logo: Image.Image | None = self._load_usatoday_logo()

        # RSS news caching
        self.usatoday_news: list[str] | None = None
        self.last_news_update: float | None = None
        self.news_update_interval: int = GameConfig.NEWS_UPDATE_INTERVAL

        # Pre-generate cached background image for performance
        self._usatoday_bg: Image.Image = self._create_usatoday_background()

    def _create_usatoday_background(self) -> Image.Image:
        """Pre-composite the full header (white bg + logo + blue rule) once.

        The logo must NOT be redrawn per frame: pixel-by-pixel draw_pixel
        loops cost more than the scroll delay on the Pi, which made the
        ticker slower and choppier than the other scrolling screens.
        """
        img = Image.new("RGB", (DisplayConfig.MATRIX_COLS, DisplayConfig.MATRIX_ROWS), self.USATODAY_WHITE)

        if self.usatoday_logo:
            logo_x = (DisplayConfig.MATRIX_COLS - self.usatoday_logo.width) // 2
            logo_y = 4
            img.paste(self.usatoday_logo, (logo_x, logo_y), self.usatoday_logo)

            separator_y = logo_y + self.usatoday_logo.height + 2
            rule = Image.new("RGB", (DisplayConfig.MATRIX_COLS, 2), self.USATODAY_BLUE)
            img.paste(rule, (0, separator_y))

        print("USA Today header cached")
        return img

    def _load_usatoday_logo(self) -> Image.Image | None:
        """Load the USA Today logo"""
        logo_paths = [
            './usatoday.png',
            '/home/pi/usatoday.png',
            './logos/usatoday.png',
            '/home/pi/logos/usatoday.png'
        ]
        for path in logo_paths:
            if os.path.exists(path):
                try:
                    logo = Image.open(path).convert('RGBA')
                    print(f"Loaded USA Today logo from {path}")
                    return logo
                except Exception as e:
                    print(f"Error loading USA Today logo: {e}")
        print("USA Today logo not found")
        return None

    def _fetch_usatoday_rss(self) -> list[str]:
        """Fetch latest headlines from the USA Today Top Stories feed"""
        news_items: list[str] = []

        try:
            print(f"Fetching USA Today news from {self.RSS_URL}")
            feed = fetch_feed(self.RSS_URL)

            if feed.bozo and not feed.entries:
                print(f"Warning: Feed parsing issue for {self.RSS_URL}")
                return news_items

            print(f"Found {len(feed.entries)} entries from USA Today")

            for entry in feed.entries[:15]:
                try:
                    title = entry.title.strip() if hasattr(entry, 'title') else ''
                    if not title:
                        continue

                    # Google News titles are suffixed with the source name;
                    # summaries are related-link HTML blobs, not article
                    # text, so this feed is title-only.
                    title = re.sub(r'\s+-\s+USA Today.*$', '', title, flags=re.IGNORECASE)

                    formatted_news = title.upper()

                    is_duplicate = False
                    for existing in news_items:
                        if existing[:50] == formatted_news[:50]:
                            is_duplicate = True
                            break
                    if not is_duplicate:
                        news_items.append(formatted_news)

                except AttributeError as e:
                    print(f"Error parsing entry: {e}")
                    continue

            print(f"Got {len(news_items)} USA Today news items")

        except Exception as e:
            print(f"Error fetching from USA Today RSS: {e}")

        return news_items[:12]

    def _should_update_news(self) -> bool:
        """Check if news needs updating"""
        if not self.usatoday_news or not self.last_news_update:
            return True
        return (time.time() - self.last_news_update) > self.news_update_interval

    def _get_live_usatoday_news(self) -> list[str]:
        """Get cached or fetch fresh USA Today headlines"""
        if self._should_update_news():
            print("Fetching fresh USA Today news from RSS feed...")
            self.usatoday_news = self._fetch_usatoday_rss()
            self.last_news_update = time.time()

        return self.usatoday_news if self.usatoday_news else []

    def _draw_usatoday_header(self):
        """Draw USA Today header from the pre-composited cached image"""
        self.manager.set_image(self._usatoday_bg, 0, 0)

        if not self.usatoday_logo:
            self.manager.draw_text('small_bold', 18, 16, self.USATODAY_NAVY, 'USA TODAY')
            for x in range(DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, 20, *self.USATODAY_BLUE)

    def _load_scroll_config(self) -> dict:
        """Load scroll speed settings from config file"""
        return load_user_config()

    def display_usatoday_news(self, duration: int = 180) -> None:
        """Display scrolling USA Today headlines with header"""
        live_news = self._get_live_usatoday_news()

        if not live_news:
            live_news = ["CHECK BACK FOR THE LATEST NEWS UPDATES!"]

        start_time = time.time()
        self.scroll_position = DisplayConfig.MATRIX_COLS

        # One continuous ticker: headlines chained with a wire-style
        # separator so there is no empty-screen pause between them
        separator = '   +++   '
        ticker = separator.join(live_news) + separator
        char_width = 10  # large_bold font width
        text_length = len(ticker) * char_width

        while time.time() - start_time < duration:
            try:
                self.manager.clear_canvas()

                self._draw_usatoday_header()

                self.scroll_position -= 1  # 1px/frame, same as Cubs facts scroll

                if self.scroll_position + text_length < 0:
                    self.scroll_position = DisplayConfig.MATRIX_COLS
                    print("Refreshing USA Today news")
                    fresh_news = self._get_live_usatoday_news()
                    if fresh_news:
                        live_news = fresh_news
                        ticker = separator.join(live_news) + separator
                        text_length = len(ticker) * char_width

                # Draw only the on-screen slice of the (long) ticker so
                # per-frame cost stays constant regardless of headline count
                first_char = max(0, int(-self.scroll_position) // char_width)
                visible = ticker[first_char:first_char + 12]
                self.manager.draw_text(
                    'large_bold',
                    int(self.scroll_position) + first_char * char_width, 44,
                    self.USATODAY_NAVY, visible, smooth=False
                )

                self.manager.swap_canvas()
                config = self._load_scroll_config()
                scroll_delay = get_scroll_delay(config.get('scroll_speed_usatoday', 5))
                time.sleep(scroll_delay)

            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"Error in USA Today news display: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(1)

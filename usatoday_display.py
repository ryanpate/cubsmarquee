"""USA Today news display - Top Stories RSS, white background, navy text"""

from __future__ import annotations

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

    RSS_URL = 'http://rssfeeds.usatoday.com/usatoday-NewsTopStories'

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
        """Pre-generate white background image for performance"""
        img = Image.new("RGB", (DisplayConfig.MATRIX_COLS, DisplayConfig.MATRIX_ROWS), self.USATODAY_WHITE)
        print("USA Today background cached")
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

    def _clean_html(self, text: str) -> str:
        """Remove HTML tags and clean up text"""
        import re
        clean = re.sub(r'<[^>]+>', '', text)
        clean = clean.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        clean = clean.replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean

    def _get_first_sentence(self, text: str, max_length: int = 150) -> str:
        """Extract first sentence or truncate to max length"""
        for ending in ['. ', '! ', '? ']:
            idx = text.find(ending)
            if idx > 0 and idx < max_length:
                return text[:idx + 1].strip()

        if len(text) > max_length:
            truncated = text[:max_length]
            last_space = truncated.rfind(' ')
            if last_space > max_length - 30:
                return truncated[:last_space] + '...'
            return truncated + '...'
        return text

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

                    summary = None
                    if hasattr(entry, 'summary') and entry.summary:
                        summary = self._clean_html(entry.summary)
                    elif hasattr(entry, 'description') and entry.description:
                        summary = self._clean_html(entry.description)

                    if summary and len(summary) > 30:
                        summary_short = self._get_first_sentence(summary, max_length=180)

                        title_words = set(title.lower().split())
                        summary_words = set(summary_short.lower().split())
                        new_words = summary_words - title_words

                        if len(new_words) > 5 and summary_short.lower() != title.lower():
                            title_short = title[:60] + '...' if len(title) > 60 else title
                            news_text = f"{title_short} - {summary_short}"
                        else:
                            news_text = summary_short
                    else:
                        news_text = title

                    formatted_news = f"USA TODAY: {news_text.upper()}"

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
        """Draw USA Today header: white background, logo, blue rule"""
        self.manager.set_image(self._usatoday_bg, 0, 0)

        if self.usatoday_logo:
            logo_width = self.usatoday_logo.width
            logo_height = self.usatoday_logo.height
            logo_x = (DisplayConfig.MATRIX_COLS - logo_width) // 2
            logo_y = 4

            self._draw_logo(logo_x, logo_y, self.usatoday_logo)

            separator_y = logo_y + logo_height + 2
            for x in range(DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, separator_y, *self.USATODAY_BLUE)
                self.manager.draw_pixel(x, separator_y + 1, *self.USATODAY_BLUE)
        else:
            self.manager.draw_text('small_bold', 18, 16, self.USATODAY_NAVY, 'USA TODAY')
            for x in range(DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, 20, *self.USATODAY_BLUE)

    def _draw_logo(self, x: int, y: int, logo: Image.Image) -> None:
        """Draw the logo at the specified position"""
        try:
            for py in range(logo.height):
                for px in range(logo.width):
                    pixel = logo.getpixel((px, py))
                    if len(pixel) == 4:
                        r, g, b, a = pixel
                        if a > 128:
                            self.manager.draw_pixel(x + px, y + py, r, g, b)
                    else:
                        r, g, b = pixel[:3]
                        self.manager.draw_pixel(x + px, y + py, r, g, b)
        except Exception as e:
            print(f"Error drawing USA Today logo: {e}")

    def _load_scroll_config(self) -> dict:
        """Load scroll speed settings from config file"""
        return load_user_config()

    def display_usatoday_news(self, duration: int = 180) -> None:
        """Display scrolling USA Today headlines with header"""
        live_news = self._get_live_usatoday_news()

        if not live_news:
            live_news = ["USA TODAY: CHECK BACK FOR THE LATEST NEWS UPDATES!"]

        start_time = time.time()
        message_index = 0
        self.scroll_position = DisplayConfig.MATRIX_COLS

        while time.time() - start_time < duration:
            try:
                self.manager.clear_canvas()

                self._draw_usatoday_header()

                current_message = live_news[message_index]

                self.scroll_position -= 1
                text_length = len(current_message) * 10  # large_bold font width

                if self.scroll_position + text_length < 0:
                    self.scroll_position = DisplayConfig.MATRIX_COLS
                    message_index = (message_index + 1) % len(live_news)

                    if message_index == 0:
                        print("Refreshing USA Today news")
                        fresh_news = self._get_live_usatoday_news()
                        if fresh_news:
                            live_news = fresh_news

                self.manager.draw_text(
                    'large_bold', int(self.scroll_position), 44,
                    self.USATODAY_NAVY, current_message
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

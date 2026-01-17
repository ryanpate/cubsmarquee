"""Newsmax news display - RSS feed with white background and blue text"""

from __future__ import annotations

import time
import os
import feedparser
from PIL import Image
from typing import TYPE_CHECKING, Any

from scoreboard_config import Colors, GameConfig, DisplayConfig, RGBColor

if TYPE_CHECKING:
    from scoreboard_manager import ScoreboardManager


class NewsmaxDisplay:
    """Handles Newsmax news display with RSS feed"""

    def __init__(self, scoreboard_manager: ScoreboardManager) -> None:
        """Initialize Newsmax display"""
        self.manager = scoreboard_manager
        self.scroll_position: int = DisplayConfig.MATRIX_COLS

        # Newsmax colors - white background with blue text
        self.NEWSMAX_WHITE: RGBColor = Colors.WHITE
        self.NEWSMAX_BLUE: RGBColor = (0, 51, 153)  # Newsmax brand blue
        self.NEWSMAX_RED: RGBColor = (204, 0, 0)  # Newsmax accent red

        # Load Newsmax logo
        self.newsmax_logo: Image.Image | None = self._load_newsmax_logo()

        # RSS news caching
        self.newsmax_news: list[str] | None = None
        self.last_news_update: float | None = None
        self.news_update_interval: int = GameConfig.NEWS_UPDATE_INTERVAL

    def _load_newsmax_logo(self) -> Image.Image | None:
        """Load the Newsmax logo"""
        logo_paths = [
            './newsmax.png',
            '/home/pi/newsmax.png',
            './logos/newsmax.png',
            '/home/pi/logos/newsmax.png'
        ]
        for path in logo_paths:
            if os.path.exists(path):
                try:
                    logo = Image.open(path).convert('RGBA')
                    print(f"Loaded Newsmax logo from {path}")
                    return logo
                except Exception as e:
                    print(f"Error loading Newsmax logo: {e}")
        print("Newsmax logo not found")
        return None

    def _clean_html(self, text: str) -> str:
        """Remove HTML tags and clean up text"""
        import re
        # Remove HTML tags
        clean = re.sub(r'<[^>]+>', '', text)
        # Decode HTML entities
        clean = clean.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        clean = clean.replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')
        # Clean up whitespace
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean

    def _get_first_sentence(self, text: str, max_length: int = 150) -> str:
        """Extract first sentence or truncate to max length"""
        # Try to find first sentence ending
        for ending in ['. ', '! ', '? ']:
            idx = text.find(ending)
            if idx > 0 and idx < max_length:
                return text[:idx + 1].strip()

        # No sentence ending found, truncate at max_length
        if len(text) > max_length:
            # Try to break at a word boundary
            truncated = text[:max_length]
            last_space = truncated.rfind(' ')
            if last_space > max_length - 30:
                return truncated[:last_space] + '...'
            return truncated + '...'
        return text

    def _fetch_newsmax_rss(self) -> list[str]:
        """
        Fetch latest news from Newsmax RSS feed
        """
        news_items = []

        rss_url = 'https://www.newsmax.com/rss/Newsfront/16'

        try:
            print(f"Fetching Newsmax news from {rss_url}")
            feed = feedparser.parse(rss_url)

            # Check if feed was successfully parsed
            if feed.bozo and not feed.entries:
                print(f"Warning: Feed parsing issue for {rss_url}")
                return news_items

            print(f"Found {len(feed.entries)} entries from Newsmax")

            # Extract news with summaries from entries
            for entry in feed.entries[:15]:  # Get top 15 stories
                try:
                    title = entry.title.strip() if hasattr(entry, 'title') else ''
                    if not title:
                        continue

                    # Get summary/description for story context
                    summary = None
                    if hasattr(entry, 'summary') and entry.summary:
                        summary = self._clean_html(entry.summary)
                    elif hasattr(entry, 'description') and entry.description:
                        summary = self._clean_html(entry.description)

                    # Build news item combining title and summary
                    if summary and len(summary) > 30:
                        summary_short = self._get_first_sentence(summary, max_length=180)

                        # Check if summary adds info beyond the title
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

                    # Format with uppercase
                    formatted_news = f"NEWSMAX: {news_text.upper()}"

                    # Avoid duplicates
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

            print(f"Got {len(news_items)} Newsmax news items")

        except Exception as e:
            print(f"Error fetching from Newsmax RSS: {e}")

        if news_items:
            print(f"Successfully fetched {len(news_items)} Newsmax news items")
        else:
            print("No Newsmax news items found")

        return news_items[:12]  # Return max 12 news items

    def _should_update_news(self) -> bool:
        """Check if news needs updating"""
        if not self.newsmax_news or not self.last_news_update:
            return True
        return (time.time() - self.last_news_update) > self.news_update_interval

    def _get_live_newsmax_news(self) -> list[str]:
        """
        Get cached or fetch fresh Newsmax news headlines
        Returns list of formatted news headlines
        """
        # Update news if needed
        if self._should_update_news():
            print("Fetching fresh Newsmax news from RSS feed...")
            self.newsmax_news = self._fetch_newsmax_rss()
            self.last_news_update = time.time()

        return self.newsmax_news if self.newsmax_news else []

    def _draw_newsmax_header(self):
        """Draw Newsmax header with white background and logo"""
        # Fill entire background with white
        for y in range(DisplayConfig.MATRIX_ROWS):
            for x in range(DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, y, *self.NEWSMAX_WHITE)

        # Draw Newsmax logo at top if available
        if self.newsmax_logo:
            # Center the logo horizontally at the top
            logo_width = self.newsmax_logo.width
            logo_height = self.newsmax_logo.height
            logo_x = (DisplayConfig.MATRIX_COLS - logo_width) // 2
            logo_y = 4  # Moved up 2 pixels

            self._draw_logo(logo_x, logo_y, self.newsmax_logo)

            # Draw blue separator line below the logo (2 pixels wide)
            separator_y = logo_y + logo_height + 2
            for x in range(DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, separator_y, *self.NEWSMAX_BLUE)
                self.manager.draw_pixel(x, separator_y + 1, *self.NEWSMAX_BLUE)
        else:
            # No logo - draw text header instead
            self.manager.draw_text('small_bold', 20, 16, self.NEWSMAX_BLUE, 'NEWSMAX')

            # Draw a thin blue separator line
            for x in range(DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, 20, *self.NEWSMAX_BLUE)

    def _draw_logo(self, x: int, y: int, logo: Image.Image) -> None:
        """Draw the logo at the specified position"""
        try:
            for py in range(logo.height):
                for px in range(logo.width):
                    pixel = logo.getpixel((px, py))
                    # Handle RGBA images - skip transparent pixels
                    if len(pixel) == 4:
                        r, g, b, a = pixel
                        if a > 128:  # Only draw if not too transparent
                            self.manager.draw_pixel(x + px, y + py, r, g, b)
                    else:
                        r, g, b = pixel[:3]
                        # Don't skip any colors on white background
                        self.manager.draw_pixel(x + px, y + py, r, g, b)
        except Exception as e:
            print(f"Error drawing Newsmax logo: {e}")

    def display_newsmax_news(self, duration: int = 180) -> None:
        """Display scrolling Newsmax news with header"""
        # Fetch live news headlines
        live_news = self._get_live_newsmax_news()

        # If no news available, show fallback message
        if not live_news:
            live_news = ["NEWSMAX: CHECK BACK FOR THE LATEST NEWS UPDATES!"]

        start_time = time.time()
        message_index = 0
        self.scroll_position = DisplayConfig.MATRIX_COLS

        while time.time() - start_time < duration:
            try:
                self.manager.clear_canvas()

                # Draw the Newsmax header with white background
                self._draw_newsmax_header()

                # Get current news headline
                current_message = live_news[message_index]

                # Scroll the message (smoother with 1px steps)
                scroll_increment = 1
                self.scroll_position -= scroll_increment
                text_length = len(current_message) * 9

                if self.scroll_position + text_length < 0:
                    self.scroll_position = DisplayConfig.MATRIX_COLS
                    # Move to next message
                    message_index = (message_index + 1) % len(live_news)

                    # Refresh news when we've gone through all headlines
                    if message_index == 0:
                        print("Refreshing Newsmax news")
                        fresh_news = self._get_live_newsmax_news()
                        if fresh_news:
                            live_news = fresh_news

                # Draw scrolling Newsmax news in blue on white background
                # Position at bottom of display area
                self.manager.draw_text(
                    'large_bold', int(self.scroll_position), 44,
                    self.NEWSMAX_BLUE, current_message
                )

                self.manager.swap_canvas()
                time.sleep(0.00067)  # 1.5x faster, still smooth with 1px steps

            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"Error in Newsmax news display: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(1)

"""PGA Tour display - Tournament leaderboard and scores"""

from __future__ import annotations

import time
import requests
import pendulum
import json
import os
import random
import feedparser
from PIL import Image
from typing import TYPE_CHECKING, Any

from scoreboard_config import Colors, GameConfig, DisplayConfig, Positions, RGBColor
from retry import retry_http_request

if TYPE_CHECKING:
    from scoreboard_manager import ScoreboardManager


class PGADisplay:
    """Handles PGA Tour tournament information display"""

    def __init__(self, scoreboard_manager: ScoreboardManager) -> None:
        """Initialize PGA display"""
        self.manager = scoreboard_manager
        self.pga_data: dict[str, Any] | None = None
        self.pga_calendar: list[dict[str, Any]] | None = None
        self.last_update: float | None = None
        self.update_interval: int = GameConfig.SCHEDULE_UPDATE_INTERVAL
        self.live_update_interval: int = 300  # Update live scores every 5 minutes
        self.scroll_position: int = DisplayConfig.MATRIX_COLS  # For scrolling text

        # Load PGA facts
        self.pga_facts: list[str] = self._load_pga_facts()

        # Initialize shuffled facts list and index for persistent rotation
        self.shuffled_pga_facts: list[str] = self.pga_facts.copy()
        random.shuffle(self.shuffled_pga_facts)
        self.pga_facts_index: int = 0

        # Load PGA logos
        self.pga_logo: Image.Image | None = self._load_pga_logo()
        self.pga_main_logo: Image.Image | None = self._load_image('pga.png')
        self.golfball_logo: Image.Image | None = self._load_image('golfball.png')
        self.masters_logo: Image.Image | None = self._load_image('masters.png')

        # RSS news caching
        self.pga_news: list[str] | None = None
        self.last_news_update: float | None = None
        self.news_update_interval: int = GameConfig.NEWS_UPDATE_INTERVAL

        # PGA Tour colors (using centralized config)
        self.PGA_BLUE: RGBColor = Colors.PGA_BLUE
        self.PGA_NAVY: RGBColor = Colors.PGA_NAVY
        self.PGA_GOLD: RGBColor = Colors.PGA_GOLD
        self.PGA_WHITE: RGBColor = Colors.WHITE
        self.PGA_GREEN: RGBColor = Colors.PGA_GREEN

    def _load_pga_logo(self) -> Image.Image | None:
        """Load the PGA golf flag logo"""
        logo_paths = [
            './logos/pga_flag.png',
            '/home/pi/logos/pga_flag.png'
        ]
        for path in logo_paths:
            if os.path.exists(path):
                try:
                    logo = Image.open(path).convert('RGBA')
                    print(f"Loaded PGA logo from {path}")
                    return logo
                except Exception as e:
                    print(f"Error loading PGA logo: {e}")
        print("PGA logo not found")
        return None

    def _load_image(self, filename: str) -> Image.Image | None:
        """Load an image from standard paths"""
        paths = [
            f'./{filename}',
            f'/home/pi/{filename}',
            f'./logos/{filename}',
            f'/home/pi/logos/{filename}'
        ]
        for path in paths:
            if os.path.exists(path):
                try:
                    img = Image.open(path).convert('RGBA')
                    print(f"Loaded {filename} from {path}")
                    return img
                except Exception as e:
                    print(f"Error loading {filename}: {e}")
        print(f"{filename} not found")
        return None

    def _fetch_pga_data(self):
        """
        Fetch PGA Tour data from ESPN API
        Uses multiple endpoints for comprehensive data
        """
        try:
            # Try the leaderboard endpoint first for active tournaments
            leaderboard_url = "https://site.api.espn.com/apis/site/v2/sports/golf/leaderboard"

            response = retry_http_request(
                leaderboard_url,
                timeout=10,
                headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'}
            )
            data = response.json()
            self.pga_data = data
            print("PGA Tour leaderboard data updated")

        except Exception as e:
            print(f"Error fetching PGA leaderboard: {e}")
            self.pga_data = None

        # Always fetch calendar/upcoming events from scoreboard endpoint
        try:
            scoreboard_url = "https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard"

            response = retry_http_request(
                scoreboard_url,
                timeout=10,
                headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'}
            )
            scoreboard_data = response.json()

            # Extract calendar from leagues data
            leagues = scoreboard_data.get('leagues', [])
            if leagues:
                self.pga_calendar = leagues[0].get('calendar', [])
                print(f"PGA Tour calendar updated: {len(self.pga_calendar)} events")

        except Exception as e:
            print(f"Error fetching PGA calendar: {e}")

        self.last_update = time.time()
        return self.pga_data is not None or self.pga_calendar is not None

    def _should_update_data(self):
        """Check if data needs updating"""
        if (not self.pga_data and not self.pga_calendar) or not self.last_update:
            return True
        return (time.time() - self.last_update) > self.update_interval

    def _load_pga_facts(self):
        """Load PGA facts from JSON file"""
        facts_path = '/home/pi/pga_facts.json'
        alt_facts_path = './pga_facts.json'

        # Default facts in case file doesn't exist
        default_facts = [
            "TIGER WOODS HAS WON 82 PGA TOUR EVENTS!",
            "THE MASTERS AT AUGUSTA NATIONAL - GOLF'S GREATEST TOURNAMENT!",
            "JACK NICKLAUS - 18 MAJOR CHAMPIONSHIPS!",
            "RORY MCILROY - 4 MAJORS BEFORE AGE 26!",
            "THE PGA TOUR - WHERE LEGENDS ARE MADE!"
        ]

        try:
            # Try primary path first
            if os.path.exists(facts_path):
                with open(facts_path, 'r') as f:
                    data = json.load(f)
                    facts = data.get('facts', default_facts)
                    print(f"Loaded {len(facts)} PGA facts from {facts_path}")
                    return facts
            # Try alternate path
            elif os.path.exists(alt_facts_path):
                with open(alt_facts_path, 'r') as f:
                    data = json.load(f)
                    facts = data.get('facts', default_facts)
                    print(f"Loaded {len(facts)} PGA facts from {alt_facts_path}")
                    return facts
            else:
                print(f"PGA facts file not found, using defaults")
                return default_facts
        except Exception as e:
            print(f"Error loading PGA facts: {e}")
            return default_facts

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

    def _fetch_pga_news_rss(self):
        """
        Fetch latest PGA news from RSS feeds
        Uses ESPN and CBS Sports for better summaries with story context
        """
        news_items = []

        # List of RSS feed URLs - ESPN and CBS Sports have the best summaries
        rss_feeds = [
            ('https://www.espn.com/espn/rss/golf/news', 'ESPN'),
            ('https://www.cbssports.com/rss/headlines/golf/', 'CBS'),
            ('https://golf.com/feed/', 'Golf.com'),
        ]

        for feed_url, source in rss_feeds:
            try:
                print(f"Fetching PGA news from {source}: {feed_url}")
                feed = feedparser.parse(feed_url)

                # Check if feed was successfully parsed
                if feed.bozo and not feed.entries:
                    print(f"Warning: Feed parsing issue for {feed_url}")
                    continue

                # Extract news with summaries from entries
                for entry in feed.entries[:6]:  # Get top 6 from each feed
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
                        elif hasattr(entry, 'content') and entry.content:
                            summary = self._clean_html(entry.content[0].get('value', ''))

                        # Build informative news item combining title and summary
                        if summary and len(summary) > 30:
                            # Extract key info from summary (first 1-2 sentences)
                            summary_short = self._get_first_sentence(summary, max_length=180)

                            # If summary adds info beyond the title, include both
                            title_words = set(title.lower().split())
                            summary_words = set(summary_short.lower().split())
                            # Check if summary has significant new info
                            new_words = summary_words - title_words
                            if len(new_words) > 5 and summary_short.lower() != title.lower():
                                # Combine: shortened title + summary detail
                                title_short = title[:60] + '...' if len(title) > 60 else title
                                news_text = f"{title_short} - {summary_short}"
                            else:
                                # Summary is just the title repeated, use summary as it's usually more complete
                                news_text = summary_short
                        else:
                            # No good summary, just use title
                            news_text = title

                        # Format with source tag and uppercase
                        formatted_news = f"GOLF: {news_text.upper()}"

                        # Avoid duplicates (check first 50 chars to catch similar headlines)
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

                print(f"Got {len(news_items)} news items from {source}")

                # Continue to next source to get variety (don't break early)
                if len(news_items) >= 10:
                    break

            except Exception as e:
                print(f"Error fetching from {feed_url}: {e}")
                continue

        if news_items:
            print(f"Successfully fetched {len(news_items)} PGA news items with summaries")
        else:
            print("No PGA news items found from any source")

        return news_items[:10]  # Return max 10 news items

    def _should_update_news(self):
        """Check if news needs updating"""
        if not self.pga_news or not self.last_news_update:
            return True
        return (time.time() - self.last_news_update) > self.news_update_interval

    def _get_live_pga_news(self):
        """
        Get cached or fetch fresh PGA news headlines
        Returns list of formatted news headlines
        """
        # Update news if needed
        if self._should_update_news():
            print("Fetching fresh PGA news from RSS feeds...")
            self.pga_news = self._fetch_pga_news_rss()
            self.last_news_update = time.time()

        return self.pga_news if self.pga_news else []

    def _get_active_tournament(self):
        """Get currently active tournament if there is one"""
        if not self.pga_data:
            return None

        try:
            # Check if there's an active event
            events = self.pga_data.get('events', [])

            if not events:
                return None

            # Get the first event (current/upcoming tournament)
            event = events[0]

            # Check tournament status - only return if actually in progress or has leaderboard
            status = event.get('status', {}).get('type', {}).get('name', '')
            state = event.get('status', {}).get('type', {}).get('state', '')

            # Valid active states: in progress, or completed with results
            active_states = ['in', 'post']  # 'in' = in progress, 'post' = completed
            canceled_statuses = ['STATUS_CANCELED', 'STATUS_POSTPONED']

            if state in active_states and status not in canceled_statuses:
                # Check if there are actually competitors/leaders
                competitions = event.get('competitions', [])
                if competitions:
                    competitors = competitions[0].get('competitors', [])
                    if competitors:
                        return event

            return None

        except Exception as e:
            print(f"Error parsing PGA tournament: {e}")
            return None

    def _get_upcoming_tournament(self) -> dict[str, Any] | None:
        """Get the next upcoming tournament from leaderboard or calendar"""
        now = pendulum.now()

        # First, check the leaderboard data for upcoming/scheduled events
        if self.pga_data:
            try:
                events = self.pga_data.get('events', [])
                for event in events:
                    # Get event dates
                    start_date_str = event.get('date', '')
                    end_date_str = event.get('endDate', start_date_str)

                    if start_date_str:
                        start_date = pendulum.parse(start_date_str)
                        end_date = pendulum.parse(end_date_str) if end_date_str else start_date

                        # Show any event that hasn't started or is currently running
                        # (ignore API status quirks for future events)
                        if start_date > now or end_date >= now:
                            return {
                                'name': event.get('name', 'PGA Event'),
                                'start_date': start_date,
                                'end_date': end_date,
                                'id': event.get('id')
                            }
            except Exception as e:
                print(f"Error parsing leaderboard for upcoming: {e}")

        # Fall back to calendar data
        if self.pga_calendar:
            try:
                for event in self.pga_calendar:
                    start_date_str = event.get('startDate', '')
                    if start_date_str:
                        start_date = pendulum.parse(start_date_str)
                        end_date_str = event.get('endDate', start_date_str)
                        end_date = pendulum.parse(end_date_str)

                        if end_date >= now:
                            return {
                                'name': event.get('label', 'PGA Event'),
                                'start_date': start_date,
                                'end_date': end_date,
                                'id': event.get('id')
                            }
            except Exception as e:
                print(f"Error parsing calendar for upcoming: {e}")

        return None

    def _get_tournament_info(self, event):
        """
        Extract tournament information
        Returns dict with: name, status, leaders, course, etc.
        """
        try:
            tournament_name = event.get('name', 'PGA TOUR')
            status = event.get('status', {}).get('type', {}).get('name', '')
            status_detail = event.get('status', {}).get('type', {}).get('shortDetail', '')

            # Get competition data
            competitions = event.get('competitions', [])
            if not competitions:
                return None

            competition = competitions[0]

            # Get competitors (players)
            competitors = competition.get('competitors', [])

            # Get top 5 leaders
            leaders = []
            for i, player in enumerate(competitors[:5]):
                try:
                    athlete = player.get('athlete', {})
                    name = athlete.get('displayName', 'Unknown')

                    # Get score (relative to par)
                    score_obj = player.get('score')
                    if isinstance(score_obj, dict):
                        score = score_obj.get('displayValue', 'E')
                    else:
                        score = str(score_obj) if score_obj else 'E'

                    # Get position
                    position = player.get('status', {}).get('position', {}).get('displayValue', str(i+1))

                    leaders.append({
                        'name': name,
                        'score': score,
                        'position': position
                    })
                except Exception as e:
                    print(f"Error parsing player {i}: {e}")
                    continue

            return {
                'name': tournament_name,
                'status': status,
                'status_detail': status_detail,
                'leaders': leaders
            }

        except Exception as e:
            print(f"Error getting tournament info: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _draw_pga_header(self):
        """Draw unique PGA Tour header with golf course/leaderboard theme"""
        # Golf course gradient background - dark green at bottom, lighter toward top
        # This creates a fairway-to-sky effect unique to PGA display
        for y in range(DisplayConfig.MATRIX_ROWS):
            # Gradient: lighter green at top (sky), darker green at bottom (fairway)
            if y < 12:
                # Header area - dark navy (like a scoreboard)
                for x in range(DisplayConfig.MATRIX_COLS):
                    self.manager.draw_pixel(x, y, *self.PGA_NAVY)
            else:
                # Content area - golf green gradient
                green_val = max(60, 120 - y)  # Darker as we go down
                for x in range(DisplayConfig.MATRIX_COLS):
                    self.manager.draw_pixel(x, y, 20, green_val, 30)

        # Gold leaderboard-style header bar at top (y=0-2) - distinctive from Bears stripes
        for y in range(3):
            for x in range(DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, y, *self.PGA_GOLD)

        # Draw thin white separator line below header
        for x in range(DisplayConfig.MATRIX_COLS):
            self.manager.draw_pixel(x, 11, 100, 100, 100)

        # Draw PGA logo if available (positioned at left edge)
        if self.pga_logo:
            self._draw_logo(2, 3, self.pga_logo)
            # Center "PGA TOUR" in remaining space (after logo)
            # Logo takes x=2 to x=18, remaining is x=20 to x=96 (76 pixels)
            # "PGA TOUR" = 8 chars * 5 pixels = 40 pixels wide
            # Adjusted left 5 pixels for visual centering
            text_x = 20 + (76 - 40) // 2 - 5  # = 33
        else:
            # Center on full screen
            text_x = (DisplayConfig.MATRIX_COLS - 40) // 2  # = 28

        # "PGA TOUR" text in white on navy header (shifted left 2 pixels)
        self.manager.draw_text('tiny_bold', text_x - 2, 10, self.PGA_WHITE, 'PGA TOUR')

    def _draw_logo(self, x: int, y: int, logo: Image.Image) -> None:
        """Draw the PGA logo at the specified position"""
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
                        if (r, g, b) != (0, 0, 0):  # Skip black (assumed transparent)
                            self.manager.draw_pixel(x + px, y + py, r, g, b)
        except Exception as e:
            print(f"Error drawing PGA logo: {e}")

    def display_pga_info(self, duration=180):
        """Display PGA Tour tournament information"""
        # Fetch data if needed
        if self._should_update_data():
            self._fetch_pga_data()

        # Check if we have any data at all
        if not self.pga_data and not self.pga_calendar:
            self._display_no_data(duration)
            return

        # Check for active tournament
        tournament = self._get_active_tournament()

        if tournament:
            self._display_tournament(tournament, duration)
        else:
            # No active tournament - show upcoming events
            self._display_no_tournament(duration)

    def _display_tournament(self, event, duration):
        """Display active tournament with leaderboard"""
        start_time = time.time()
        last_update = 0
        scroll_position = DisplayConfig.MATRIX_COLS

        try:
            # Get initial tournament info
            tourney_info = self._get_tournament_info(event)
            if not tourney_info:
                return

            tournament_name = tourney_info['name']
            status = tourney_info['status']
            status_detail = tourney_info['status_detail']
            leaders = tourney_info['leaders']

            print(f"Tournament: {tournament_name}, Status: {status}")

            while time.time() - start_time < duration:
                # Update live scores periodically
                current_time = time.time()
                if current_time - last_update >= self.live_update_interval:
                    if self._fetch_pga_data():
                        tournament = self._get_active_tournament()
                        if tournament:
                            updated_info = self._get_tournament_info(tournament)
                            if updated_info:
                                leaders = updated_info['leaders']
                                status_detail = updated_info['status_detail']
                                print("PGA scores updated")
                    last_update = current_time

                self.manager.clear_canvas()

                # Draw header (includes gradient background)
                self._draw_pga_header()

                # Tournament name - positioned below header (y=20)
                name_upper = tournament_name.upper()
                name_width = len(name_upper) * 5  # tiny font width

                if name_width > 90:
                    # Scroll long names
                    scroll_increment = getattr(GameConfig, 'SCROLL_PIXELS', 1)
                    scroll_position -= scroll_increment
                    if scroll_position + name_width < 0:
                        scroll_position = DisplayConfig.MATRIX_COLS

                    self.manager.draw_text('tiny', int(scroll_position), 20,
                                           self.PGA_GOLD, name_upper)
                else:
                    # Center short names
                    name_x = max(2, (DisplayConfig.MATRIX_COLS - name_width) // 2)
                    self.manager.draw_text('tiny', name_x, 20,
                                           self.PGA_GOLD, name_upper)

                # Status indicator (Round 1, Round 2, Final, etc.) - y=25
                if status_detail:
                    status_short = status_detail[:15]
                    status_x = max(2, (DisplayConfig.MATRIX_COLS - len(status_short) * 4) // 2)
                    self.manager.draw_text('micro', status_x, 25,
                                           self.PGA_WHITE, status_short)

                # Leaderboard column headers (like actual PGA leaderboard)
                self.manager.draw_text('ultra_micro', 2, 30, (120, 120, 120), 'POS')
                self.manager.draw_text('ultra_micro', 18, 30, (120, 120, 120), 'PLAYER')
                self.manager.draw_text('ultra_micro', 72, 30, (120, 120, 120), 'SCORE')

                # Display leaderboard - top 4 players in tabular layout
                if leaders:
                    y_pos = 36
                    for i, leader in enumerate(leaders[:4]):
                        pos = leader['position']
                        name_parts = leader['name'].split()
                        last_name = name_parts[-1][:8].upper() if name_parts else "UNKNOWN"
                        score = leader['score']

                        # Leader highlighted in gold
                        if i == 0:
                            pos_color = self.PGA_GOLD
                            name_color = self.PGA_GOLD
                        else:
                            pos_color = self.PGA_WHITE
                            name_color = self.PGA_WHITE

                        # Draw position (column 1)
                        self.manager.draw_text('micro', 4, y_pos, pos_color, str(pos))

                        # Draw name (column 2)
                        self.manager.draw_text('micro', 18, y_pos, name_color, last_name)

                        # Draw score (column 3) with color coding
                        try:
                            score_clean = score.replace('+', '').replace('E', '0').replace('-', '')
                            if score.startswith('-'):
                                score_color = (100, 255, 100)  # Under par - bright green
                            elif score.startswith('+'):
                                score_color = (255, 120, 120)  # Over par - light red
                            else:
                                score_color = self.PGA_WHITE
                        except (ValueError, AttributeError):
                            score_color = self.PGA_WHITE

                        self.manager.draw_text('micro', 74, y_pos, score_color, score)
                        y_pos += 4

                self.manager.swap_canvas()
                time.sleep(0.1)

        except Exception as e:
            print(f"Error displaying PGA tournament: {e}")
            import traceback
            traceback.print_exc()

    def _display_no_tournament(self, duration):
        """Display upcoming tournament info when no active tournament"""
        start_time = time.time()

        # Try to get upcoming tournament info
        upcoming = self._get_upcoming_tournament()

        if upcoming:
            # Display upcoming tournament with static info
            self._display_upcoming_tournament(upcoming, duration)
        else:
            # Fallback to scrolling message
            scroll_position = 96
            message = "CHECK BACK FOR TOURNAMENT UPDATES"

            while time.time() - start_time < duration:
                self.manager.clear_canvas()
                self._draw_pga_header()

                scroll_increment = getattr(GameConfig, 'SCROLL_PIXELS', 2)
                scroll_position -= scroll_increment
                text_length = len(message) * 5

                if scroll_position + text_length < 0:
                    scroll_position = 96

                # Scrolling message in content area
                self.manager.draw_text('tiny_bold', int(scroll_position), 32,
                                       self.PGA_WHITE, message)

                self.manager.swap_canvas()
                time.sleep(GameConfig.SCROLL_SPEED)

    def _display_upcoming_tournament(self, upcoming: dict[str, Any], duration: int):
        """Display upcoming tournament information with unique golf layout"""
        start_time = time.time()
        scroll_position = DisplayConfig.MATRIX_COLS

        tournament_name = upcoming['name']
        start_date = upcoming['start_date']
        end_date = upcoming['end_date']

        # Format dates for display
        start_str = start_date.in_timezone('America/Chicago').format('MMM D')
        end_str = end_date.in_timezone('America/Chicago').format('D')
        date_range = f"{start_str}-{end_str}"

        # Calculate days until tournament
        now = pendulum.now()
        days_until = (start_date - now).days

        while time.time() - start_time < duration:
            self.manager.clear_canvas()
            self._draw_pga_header()

            # "UP NEXT" label in small text (shifted left 2 pixels)
            self.manager.draw_text('ultra_micro', 36, 18, (150, 150, 150), 'UP NEXT')

            # Tournament name - positioned below header
            name_upper = tournament_name.upper()
            name_width = len(name_upper) * 5
            if name_width > 90:
                # Scroll long names
                scroll_increment = getattr(GameConfig, 'SCROLL_PIXELS', 1)
                scroll_position -= scroll_increment
                if scroll_position + name_width < 0:
                    scroll_position = DisplayConfig.MATRIX_COLS

                self.manager.draw_text('tiny_bold', int(scroll_position), 26,
                                       self.PGA_GOLD, name_upper)
            else:
                # Center short names
                name_x = max(2, (DisplayConfig.MATRIX_COLS - name_width) // 2)
                self.manager.draw_text('tiny_bold', name_x, 26,
                                       self.PGA_GOLD, name_upper)

            # Date range - centered
            date_x = max(2, (DisplayConfig.MATRIX_COLS - len(date_range) * 5) // 2)
            self.manager.draw_text('tiny', date_x, 34, self.PGA_WHITE, date_range)

            # Countdown with visual emphasis
            if days_until <= 0:
                countdown = "STARTS TODAY!"
                countdown_color = (100, 255, 100)  # Bright green
            elif days_until == 1:
                countdown = "STARTS TOMORROW"
                countdown_color = self.PGA_GOLD
            else:
                countdown = f"{days_until} DAYS AWAY"
                countdown_color = self.PGA_WHITE

            countdown_x = max(2, (DisplayConfig.MATRIX_COLS - len(countdown) * 5) // 2)
            self.manager.draw_text('tiny', countdown_x, 44, countdown_color, countdown)

            self.manager.swap_canvas()
            time.sleep(0.05)

    def _display_no_data(self, duration):
        """Display message when data fetch fails"""
        start_time = time.time()

        while time.time() - start_time < duration:
            self.manager.clear_canvas()
            self._draw_pga_header()

            # Error message centered in content area
            self.manager.draw_text('tiny', 22, 30, self.PGA_WHITE, 'DATA')
            self.manager.draw_text('tiny', 10, 40, self.PGA_WHITE, 'UNAVAILABLE')

            self.manager.swap_canvas()
            time.sleep(1)

    def _draw_pga_content_header(self, subtitle: str):
        """Draw header for PGA news or facts page with logo"""
        # Fill background with golf green gradient
        for y in range(DisplayConfig.MATRIX_ROWS):
            # Darker green at bottom, lighter at top
            green_val = max(50, 100 - y)
            for x in range(DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, y, 15, green_val, 25)

        # Gold bar at top (y=0-2) - matches main PGA header
        for y in range(3):
            for x in range(DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, y, *self.PGA_GOLD)

        # Navy header area (y=3-25, extended 1 pixel)
        for y in range(3, 26):
            for x in range(DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, y, *self.PGA_NAVY)

        # Gold separator line at bottom of header
        for x in range(DisplayConfig.MATRIX_COLS):
            self.manager.draw_pixel(x, 25, *self.PGA_GOLD)

        # Draw golfball logo on left if available (moved 2 pixels left)
        logo_x = 2
        if self.golfball_logo:
            self._draw_logo(logo_x, 5, self.golfball_logo)
            text_start = logo_x + self.golfball_logo.width + 4
        else:
            text_start = 8

        # "PGA TOUR" title - adjusted left 12 pixels, down 1 pixel
        title = "PGA TOUR"
        title_width = len(title) * 5
        available_width = DisplayConfig.MATRIX_COLS - text_start
        title_x = text_start + (available_width - title_width) // 2 - 12
        self.manager.draw_text('tiny_bold', title_x, 12, self.PGA_WHITE, title)

        # Subtitle (NEWS or FACTS) - adjusted left 12 pixels, down 1 pixel
        subtitle_width = len(subtitle) * 4
        subtitle_x = text_start + (available_width - subtitle_width) // 2 - 12
        self.manager.draw_text('micro', subtitle_x, 21, self.PGA_GOLD, subtitle)

        # Draw PGA main logo on right side if available (moved 2 pixels right)
        if self.pga_main_logo:
            logo_right_x = DisplayConfig.MATRIX_COLS - self.pga_main_logo.width - 2
            self._draw_logo(logo_right_x, 4, self.pga_main_logo)

    def display_pga_news(self, duration=180):
        """Display scrolling PGA Tour news with header"""
        # Fetch live news headlines
        live_news = self._get_live_pga_news()

        # If no news available, show fallback message
        if not live_news:
            live_news = ["GOLF NEWS: CHECK BACK FOR THE LATEST PGA TOUR UPDATES!"]

        start_time = time.time()
        message_index = 0
        self.scroll_position = 96

        while time.time() - start_time < duration:
            try:
                self.manager.clear_canvas()

                # Draw the PGA news header
                self._draw_pga_content_header("BREAKING NEWS")

                # Get current news headline
                current_message = live_news[message_index]

                # Scroll the message
                scroll_increment = getattr(GameConfig, 'SCROLL_PIXELS', 2)
                self.scroll_position -= scroll_increment
                text_length = len(current_message) * 9

                if self.scroll_position + text_length < 0:
                    self.scroll_position = 96
                    # Move to next message
                    message_index = (message_index + 1) % len(live_news)

                    # Refresh news when we've gone through all headlines
                    if message_index == 0:
                        print("Refreshing PGA news")
                        fresh_news = self._get_live_pga_news()
                        if fresh_news:
                            live_news = fresh_news

                # Draw scrolling PGA news below header (y=44 like other news pages)
                self.manager.draw_text(
                    'medium_bold', int(self.scroll_position), 44,
                    self.PGA_WHITE, current_message
                )

                self.manager.swap_canvas()
                time.sleep(GameConfig.SCROLL_SPEED)

            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"Error in PGA news display: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(1)

    def display_pga_facts(self, duration=180):
        """Display scrolling PGA Tour facts with header using persistent shuffle"""
        start_time = time.time()
        self.scroll_position = 96

        while time.time() - start_time < duration:
            try:
                self.manager.clear_canvas()

                # Draw the PGA facts header
                self._draw_pga_content_header("GOLF FACTS")

                # Get current fact from persistent shuffled list
                current_message = self.shuffled_pga_facts[self.pga_facts_index]

                # Scroll the message
                scroll_increment = getattr(GameConfig, 'SCROLL_PIXELS', 2)
                self.scroll_position -= scroll_increment
                text_length = len(current_message) * 9

                if self.scroll_position + text_length < 0:
                    self.scroll_position = 96
                    # Move to next fact
                    self.pga_facts_index += 1

                    # Re-shuffle when we've gone through all facts
                    if self.pga_facts_index >= len(self.shuffled_pga_facts):
                        print(f"Completed full cycle of {len(self.shuffled_pga_facts)} PGA facts - re-shuffling")
                        self.shuffled_pga_facts = self.pga_facts.copy()
                        random.shuffle(self.shuffled_pga_facts)
                        self.pga_facts_index = 0

                # Draw scrolling PGA facts below header (y=44 like other news pages)
                self.manager.draw_text(
                    'medium_bold', int(self.scroll_position), 44,
                    self.PGA_WHITE, current_message
                )

                self.manager.swap_canvas()
                time.sleep(GameConfig.SCROLL_SPEED)

            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"Error in PGA facts display: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(1)

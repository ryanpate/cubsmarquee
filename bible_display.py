"""Bible Verse of the Day display - Inspirational scripture on LED matrix"""

from __future__ import annotations

import time
import json
import os
import random
from PIL import Image
from typing import TYPE_CHECKING, Any

from scoreboard_config import Colors, GameConfig, DisplayConfig, RGBColor

if TYPE_CHECKING:
    from scoreboard_manager import ScoreboardManager


class BibleDisplay:
    """Handles Bible Verse of the Day display"""

    def __init__(self, scoreboard_manager: ScoreboardManager) -> None:
        """Initialize Bible display"""
        self.manager = scoreboard_manager
        self.scroll_position: int = DisplayConfig.MATRIX_COLS

        # Load Bible verses
        self.bible_verses: list[dict[str, str]] = self._load_bible_verses()

        # Initialize shuffled verses list and index for non-repeating rotation
        self.shuffled_verses: list[dict[str, str]] = self.bible_verses.copy()
        random.shuffle(self.shuffled_verses)
        self.verses_index: int = 0

        # Color scheme - warm gold and white on deep purple/navy
        self.BIBLE_NAVY: RGBColor = (20, 20, 60)  # Deep navy/purple
        self.BIBLE_GOLD: RGBColor = (255, 215, 0)  # Gold for header
        self.BIBLE_WHITE: RGBColor = (255, 255, 255)  # White for verse text
        self.BIBLE_CREAM: RGBColor = (255, 248, 220)  # Cream for reference

        # Load Bible icon
        self.bible_icon: Image.Image | None = self._load_bible_icon()

    def _load_bible_icon(self) -> Image.Image | None:
        """Load Bible icon for display"""
        icon_paths = [
            './bible.png',
            '/home/pi/bible.png',
            './logos/bible.png',
            '/home/pi/logos/bible.png'
        ]
        for path in icon_paths:
            if os.path.exists(path):
                try:
                    icon = Image.open(path).convert('RGBA')
                    print(f"Loaded Bible icon from {path}")
                    return icon
                except Exception as e:
                    print(f"Error loading Bible icon: {e}")
        print("Bible icon not found (optional)")
        return None

    def _draw_icon(self, x: int, y: int, icon: Image.Image) -> None:
        """Draw an icon at the specified position"""
        try:
            for py in range(icon.height):
                for px in range(icon.width):
                    pixel = icon.getpixel((px, py))
                    if len(pixel) == 4:
                        r, g, b, a = pixel
                        if a > 128:
                            self.manager.draw_pixel(x + px, y + py, r, g, b)
                    else:
                        r, g, b = pixel[:3]
                        if (r, g, b) != (0, 0, 0):
                            self.manager.draw_pixel(x + px, y + py, r, g, b)
        except Exception as e:
            print(f"Error drawing icon: {e}")

    def _load_bible_verses(self) -> list[dict[str, str]]:
        """Load Bible verses from JSON file"""
        verses_path = '/home/pi/bible_verses.json'
        alt_verses_path = './bible_verses.json'

        # Default verses in case file doesn't exist
        default_verses = [
            {"verse": "For God so loved the world that he gave his one and only Son, that whoever believes in him shall not perish but have eternal life.", "reference": "John 3:16"},
            {"verse": "I can do all things through Christ who strengthens me.", "reference": "Philippians 4:13"},
            {"verse": "The Lord is my shepherd; I shall not want.", "reference": "Psalm 23:1"},
            {"verse": "Trust in the Lord with all your heart and lean not on your own understanding.", "reference": "Proverbs 3:5"},
            {"verse": "Be strong and courageous. Do not be afraid; do not be discouraged, for the Lord your God will be with you wherever you go.", "reference": "Joshua 1:9"}
        ]

        try:
            # Try primary path first
            if os.path.exists(verses_path):
                with open(verses_path, 'r') as f:
                    data = json.load(f)
                    verses = data.get('verses', default_verses)
                    print(f"Loaded {len(verses)} Bible verses from {verses_path}")
                    return verses
            # Try alternate path
            elif os.path.exists(alt_verses_path):
                with open(alt_verses_path, 'r') as f:
                    data = json.load(f)
                    verses = data.get('verses', default_verses)
                    print(f"Loaded {len(verses)} Bible verses from {alt_verses_path}")
                    return verses
            else:
                print(f"Bible verses file not found, using defaults")
                return default_verses
        except Exception as e:
            print(f"Error loading Bible verses: {e}")
            return default_verses

    def _draw_bible_header(self):
        """Draw elegant Bible verse header with icon and two-line title"""
        # Fill background with deep navy/purple
        for y in range(48):
            for x in range(96):
                self.manager.draw_pixel(x, y, *self.BIBLE_NAVY)

        # Draw Bible icon on the left if available (shifted right 8 pixels)
        icon_width = 0
        if self.bible_icon:
            self._draw_icon(10, 2, self.bible_icon)
            icon_width = self.bible_icon.width + 4

        # Calculate text positioning based on icon (shifted right 8 pixels)
        text_start_x = icon_width + 10

        # Draw "VERSE OF" on first line (shifted down 4, right 8)
        self.manager.draw_text('small_bold', text_start_x, 13, self.BIBLE_GOLD, 'VERSE OF')

        # Draw "THE DAY" on second line (shifted down 4, right 8)
        self.manager.draw_text('small_bold', text_start_x, 23, self.BIBLE_GOLD, 'THE DAY')

        # Draw subtle separator line below header area (shifted down 3)
        for x in range(96):
            self.manager.draw_pixel(x, 27, 60, 60, 100)  # Subtle blue-gray line

    def display_bible_verse(self, duration: int = 180) -> None:
        """Display scrolling Bible verses - random order, no repeats until all shown"""
        start_time = time.time()
        self.scroll_position = 96

        while time.time() - start_time < duration:
            try:
                self.manager.clear_canvas()

                # Draw the Bible header
                self._draw_bible_header()

                # Get current verse from shuffled list
                current_verse_data = self.shuffled_verses[self.verses_index]
                verse_text = current_verse_data.get('verse', '')
                reference = current_verse_data.get('reference', '')
                full_text = f'"{verse_text}" - {reference}'

                # Scroll the message
                scroll_increment = getattr(GameConfig, 'SCROLL_PIXELS', 2)
                self.scroll_position -= scroll_increment
                text_length = len(full_text) * 9

                # When text scrolls off, move to next verse
                if self.scroll_position + text_length < 0:
                    self.scroll_position = 96
                    self.verses_index += 1

                    # Re-shuffle when all verses have been shown
                    if self.verses_index >= len(self.shuffled_verses):
                        print(f"Completed full cycle of {len(self.shuffled_verses)} Bible verses - re-shuffling")
                        self.shuffled_verses = self.bible_verses.copy()
                        random.shuffle(self.shuffled_verses)
                        self.verses_index = 0

                # Draw scrolling verse text in cream below header (moved down 2 pixels)
                self.manager.draw_text(
                    'medium_bold', int(self.scroll_position), 44,
                    self.BIBLE_CREAM, full_text
                )

                self.manager.swap_canvas()
                time.sleep(GameConfig.SCROLL_SPEED)

            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"Error in Bible verse display: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(1)

    def display_bible_loading(self, message: str = "LOADING VERSES...") -> None:
        """Display loading message with Bible header"""
        self.manager.clear_canvas()

        # Draw header
        self._draw_bible_header()

        # Display loading message centered
        message_width = len(message) * 5
        x_pos = max(0, (96 - message_width) // 2)
        self.manager.draw_text('small_bold', x_pos, 38, self.BIBLE_CREAM, message)

        self.manager.swap_canvas()

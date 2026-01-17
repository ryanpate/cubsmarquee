"""Stock Exchange ticker display - Major US indices"""

from __future__ import annotations

import time
import os
import requests
from PIL import Image
from typing import TYPE_CHECKING, Any

from scoreboard_config import Colors, GameConfig, DisplayConfig, RGBColor

if TYPE_CHECKING:
    from scoreboard_manager import ScoreboardManager


class StockDisplay:
    """Handles stock market ticker display with major US indices"""

    def __init__(self, scoreboard_manager: ScoreboardManager) -> None:
        """Initialize Stock display"""
        self.manager = scoreboard_manager
        self.scroll_position: int = DisplayConfig.MATRIX_COLS

        # Stock display colors - dark background with colored text
        self.BG_COLOR: RGBColor = (0, 0, 0)  # Black background
        self.HEADER_BG: RGBColor = (20, 20, 40)  # Dark blue-gray header
        self.STOCK_GREEN: RGBColor = (0, 255, 0)  # Bright green for gains
        self.STOCK_RED: RGBColor = (255, 50, 50)  # Red for losses
        self.STOCK_YELLOW: RGBColor = (255, 200, 0)  # Yellow for neutral/labels
        self.STOCK_WHITE: RGBColor = (255, 255, 255)

        # Load stocks icon
        self.stocks_icon: Image.Image | None = self._load_stocks_icon()

        # Stock data caching
        self.stock_data: list[dict[str, Any]] | None = None
        self.last_update: float | None = None
        self.update_interval: int = 300  # Update every 5 minutes

        # Major US indices to track
        self.indices = [
            ('^DJI', 'DOW'),
            ('^GSPC', 'S&P'),
            ('^IXIC', 'NASDAQ'),
            ('^RUT', 'RUSS'),
        ]

    def _load_stocks_icon(self) -> Image.Image | None:
        """Load the stocks icon"""
        icon_paths = [
            './stocks.png',
            '/home/pi/stocks.png',
        ]
        for path in icon_paths:
            if os.path.exists(path):
                try:
                    icon = Image.open(path).convert('RGBA')
                    print(f"Loaded stocks icon from {path}")
                    return icon
                except Exception as e:
                    print(f"Error loading stocks icon: {e}")
        print("Stocks icon not found")
        return None

    def _draw_icon(self, x: int, y: int, icon: Image.Image) -> None:
        """Draw icon at specified position"""
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
                        self.manager.draw_pixel(x + px, y + py, r, g, b)
        except Exception as e:
            print(f"Error drawing stocks icon: {e}")

    def _fetch_stock_data(self) -> list[dict[str, Any]]:
        """
        Fetch stock data for major US indices using Yahoo Finance API
        """
        stock_items = []

        for symbol, display_name in self.indices:
            try:
                # Yahoo Finance API endpoint
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
                params = {
                    'interval': '1d',
                    'range': '1d'
                }
                headers = {
                    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
                }

                response = requests.get(url, params=params, headers=headers, timeout=10)
                data = response.json()

                if 'chart' in data and 'result' in data['chart'] and data['chart']['result']:
                    result = data['chart']['result'][0]
                    meta = result.get('meta', {})

                    current_price = meta.get('regularMarketPrice', 0)
                    # Use chartPreviousClose as fallback for previousClose
                    previous_close = meta.get('previousClose') or meta.get('chartPreviousClose', 0)

                    if previous_close and current_price:
                        change = current_price - previous_close
                        change_pct = (change / previous_close) * 100

                        stock_items.append({
                            'symbol': display_name,
                            'price': current_price,
                            'change': change,
                            'change_pct': change_pct
                        })
                        print(f"Fetched {display_name}: {current_price:.2f} ({change_pct:+.2f}%)")

            except Exception as e:
                print(f"Error fetching {symbol}: {e}")
                continue

        return stock_items

    def _should_update(self) -> bool:
        """Check if stock data needs updating"""
        if not self.stock_data or not self.last_update:
            return True
        return (time.time() - self.last_update) > self.update_interval

    def _get_stock_data(self) -> list[dict[str, Any]]:
        """
        Get cached or fetch fresh stock data
        """
        if self._should_update():
            print("Fetching fresh stock market data...")
            self.stock_data = self._fetch_stock_data()
            self.last_update = time.time()

        return self.stock_data if self.stock_data else []

    def _draw_header(self):
        """Draw clean stock ticker header"""
        # Fill background with black
        for y in range(DisplayConfig.MATRIX_ROWS):
            for x in range(DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, y, *self.BG_COLOR)

        # Draw header bar background (extended to include text)
        for y in range(18):
            for x in range(DisplayConfig.MATRIX_COLS):
                self.manager.draw_pixel(x, y, *self.HEADER_BG)

        # Calculate positions for icon and "Markets" text centered together
        text_width = 7 * 9  # "Markets" = 7 chars * 9 pixels
        icon_width = self.stocks_icon.width if self.stocks_icon else 0
        total_width = icon_width + 4 + text_width  # icon + spacing + text
        start_x = (DisplayConfig.MATRIX_COLS - total_width) // 2

        # Draw stocks icon to the left of text
        if self.stocks_icon:
            icon_y = (18 - self.stocks_icon.height) // 2  # Center vertically in header
            self._draw_icon(start_x, icon_y, self.stocks_icon)
            text_x = start_x + icon_width + 4
        else:
            text_x = (DisplayConfig.MATRIX_COLS - text_width) // 2

        # Draw "Markets" text
        self.manager.draw_text('medium_bold', text_x, 15, self.STOCK_YELLOW, 'Markets')

        # Draw thin separator line
        for x in range(DisplayConfig.MATRIX_COLS):
            self.manager.draw_pixel(x, 18, 60, 60, 80)

    def display_stock_ticker(self, duration: int = 180) -> None:
        """Display scrolling stock ticker"""
        # Fetch stock data
        stocks = self._get_stock_data()

        if not stocks:
            stocks = [{'symbol': 'DATA', 'price': 0, 'change': 0, 'change_pct': 0}]

        start_time = time.time()
        self.scroll_position = DisplayConfig.MATRIX_COLS

        while time.time() - start_time < duration:
            try:
                self.manager.clear_canvas()
                self._draw_header()

                # Build and draw ticker with individual colors per stock
                x_pos = int(self.scroll_position)

                for i, stock in enumerate(stocks):
                    symbol = stock['symbol']
                    price = stock['price']
                    change_pct = stock['change_pct']

                    # Format price
                    if price > 1000:
                        price_str = f"{price:,.0f}"
                    else:
                        price_str = f"{price:.2f}"

                    # Determine color based on change
                    if change_pct > 0:
                        color = self.STOCK_GREEN
                        arrow = "+"
                    elif change_pct < 0:
                        color = self.STOCK_RED
                        arrow = ""
                    else:
                        color = self.STOCK_YELLOW
                        arrow = ""

                    # Build text for this stock
                    stock_text = f"{symbol} {price_str} {arrow}{change_pct:.1f}%"

                    # Draw the stock info
                    self.manager.draw_text('medium_bold', x_pos, 42, self.STOCK_WHITE, symbol)
                    x_pos += len(symbol) * 9 + 4

                    self.manager.draw_text('medium_bold', x_pos, 42, self.STOCK_YELLOW, price_str)
                    x_pos += len(price_str) * 9 + 4

                    pct_text = f"{arrow}{change_pct:.1f}%"
                    self.manager.draw_text('medium_bold', x_pos, 42, color, pct_text)
                    x_pos += len(pct_text) * 9 + 20  # Extra spacing between stocks

                # Calculate total width and scroll
                total_width = x_pos - int(self.scroll_position)
                self.scroll_position -= 1

                if self.scroll_position + total_width < 0:
                    self.scroll_position = DisplayConfig.MATRIX_COLS
                    # Refresh data on loop
                    print("Refreshing stock data")
                    stocks = self._get_stock_data()
                    if not stocks:
                        stocks = [{'symbol': 'DATA', 'price': 0, 'change': 0, 'change_pct': 0}]

                self.manager.swap_canvas()
                time.sleep(0.00067)

            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"Error in stock ticker display: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(1)

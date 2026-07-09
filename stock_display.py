"""Stock Exchange display - major US indices dashboard with sparklines"""

from __future__ import annotations

import time
import math
import pendulum
import requests
from PIL import Image
from typing import TYPE_CHECKING, Any

from scoreboard_config import DisplayConfig, RGBColor

if TYPE_CHECKING:
    from scoreboard_manager import ScoreboardManager


class StockDisplay:
    """Handles stock market display with major US indices"""

    DASH_SECONDS = 15   # dashboard view time per cycle
    SPARK_SECONDS = 8   # sparkline view time per index

    def __init__(self, scoreboard_manager: ScoreboardManager) -> None:
        """Initialize Stock display"""
        self.manager = scoreboard_manager

        # Stock display colors
        self.STOCK_GREEN: RGBColor = (60, 220, 90)   # gains
        self.STOCK_RED: RGBColor = (255, 80, 80)     # losses
        self.STOCK_YELLOW: RGBColor = (255, 200, 0)  # prices
        self.STOCK_WHITE: RGBColor = (255, 255, 255)
        self.BODY_BG: RGBColor = (4, 12, 8)          # near-black green

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

        # Pre-generate cached background image for performance
        self._stock_header_bg: Image.Image = self._create_stock_header_background()

    def _create_stock_header_background(self) -> Image.Image:
        """Emerald gradient header over a near-black green body"""
        img = Image.new(
            "RGB", (DisplayConfig.MATRIX_COLS, DisplayConfig.MATRIX_ROWS),
            self.BODY_BG)
        pixels = img.load()
        for y in range(13):
            t = y / 12
            color = (int(18 - 13 * t), int(90 - 68 * t), int(50 - 37 * t))
            for x in range(DisplayConfig.MATRIX_COLS):
                pixels[x, y] = color
        print("Stock header background cached")
        return img

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
                    'interval': '15m',  # intraday points for the sparkline
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
                            'change_pct': change_pct,
                            'sparkline': self._parse_chart_points(data),
                        })
                        print(f"Fetched {display_name}: {current_price:.2f} ({change_pct:+.2f}%)")

            except Exception as e:
                print(f"Error fetching {symbol}: {e}")
                continue

        return stock_items

    @staticmethod
    def _parse_chart_points(data: dict[str, Any]) -> list[float]:
        """Intraday close prices from a Yahoo chart response (gaps removed)"""
        try:
            result = data['chart']['result'][0]
            closes = result['indicators']['quote'][0]['close']
            return [c for c in closes if c is not None]
        except (KeyError, IndexError, TypeError):
            return []

    @staticmethod
    def _scale_points(
        points: list[float], x0: int, y0: int, w: int, h: int
    ) -> list[tuple[int, int]]:
        """Scale a price series into pixel coords inside a w x h box"""
        lo, hi = min(points), max(points)
        n = len(points)
        scaled = []
        for i, p in enumerate(points):
            x = x0 + (round(i * (w - 1) / (n - 1)) if n > 1 else 0)
            if hi == lo:
                y = y0 + h // 2
            else:
                y = y0 + h - 1 - round((p - lo) / (hi - lo) * (h - 1))
            scaled.append((x, y))
        return scaled

    @staticmethod
    def _is_market_open(when: pendulum.DateTime | None = None) -> bool:
        """NYSE core trading hours: weekdays 9:30-16:00 Eastern"""
        if when is None:
            when = pendulum.now('America/New_York')
        if when.weekday() > 4:  # Saturday / Sunday
            return False
        minutes = when.hour * 60 + when.minute
        return 9 * 60 + 30 <= minutes < 16 * 60

    @classmethod
    def _view_for_tick(
        cls, elapsed: float, index_count: int
    ) -> tuple[str, int | None]:
        """Which view to show: dashboard first, then a sparkline per index"""
        if index_count <= 0:
            return ('dashboard', None)
        cycle = cls.DASH_SECONDS + cls.SPARK_SECONDS * index_count
        t = elapsed % cycle
        if t < cls.DASH_SECONDS:
            return ('dashboard', None)
        return ('sparkline', int((t - cls.DASH_SECONDS) // cls.SPARK_SECONDS))

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

    @staticmethod
    def _format_price(price: float) -> str:
        return f"{price:,.0f}" if price > 1000 else f"{price:.2f}"

    def _change_color(self, change_pct: float) -> RGBColor:
        if change_pct > 0:
            return self.STOCK_GREEN
        if change_pct < 0:
            return self.STOCK_RED
        return self.STOCK_YELLOW

    def _draw_change_triangle(
        self, x: int, y: int, change_pct: float, color: RGBColor
    ) -> None:
        """Small up/down triangle for the day's direction (flat: dash)"""
        if change_pct == 0:
            for dx in range(3):
                self.manager.draw_pixel(x + 1 + dx, y + 1, *color)
            return
        rows = (0, 1, 2) if change_pct > 0 else (2, 1, 0)
        for i, width in enumerate((0, 1, 2)):
            for dx in range(-width, width + 1):
                self.manager.draw_pixel(x + 2 + dx, y + rows[i], *color)

    def _draw_header(self, tick: float | None = None) -> None:
        """Gradient header: trend glyph, MARKETS title, market status dot"""
        if tick is None:
            tick = time.time()
        self.manager.set_image(self._stock_header_bg, 0, 0)

        # Thin separator line below header
        for x in range(DisplayConfig.MATRIX_COLS):
            self.manager.draw_pixel(x, 13, 50, 95, 65)

        # Rising trend line glyph, drawn left of the title
        trend = [(2, 10), (4, 8), (6, 9), (8, 6), (10, 7), (12, 4), (14, 2)]
        for (x1, y1), (x2, y2) in zip(trend, trend[1:]):
            steps = max(abs(x2 - x1), abs(y2 - y1))
            for s in range(steps + 1):
                px = x1 + round((x2 - x1) * s / steps)
                py = y1 + round((y2 - y1) * s / steps)
                self.manager.draw_pixel(px, py, 120, 255, 150)
        # Blinking tip on the latest point
        if int(tick * 2) % 2:
            tx, ty = trend[-1]
            self.manager.draw_pixel(tx + 1, ty, 255, 255, 255)

        # Title, centered between the top edge and the separator
        self.manager.draw_text(
            'tiny_bold', 27, 9, self.STOCK_WHITE, 'MARKETS')

        # Market status: green blinking dot when open, dim red when closed
        if self._is_market_open():
            if int(tick * 2) % 2:
                for dx in range(2):
                    for dy in range(2):
                        self.manager.draw_pixel(
                            88 + dx, 5 + dy, *self.STOCK_GREEN)
        else:
            for dx in range(2):
                for dy in range(2):
                    self.manager.draw_pixel(88 + dx, 5 + dy, 150, 45, 45)

    def _draw_dashboard_frame(
        self, stocks: list[dict[str, Any]], tick: float | None = None
    ) -> None:
        """All indices at a glance: symbol, price, day change"""
        self.manager.clear_canvas()
        self._draw_header(tick)

        for stock, baseline in zip(stocks[:4], (21, 29, 37, 45)):
            price_str = self._format_price(stock['price'])
            change_pct = stock['change_pct']
            color = self._change_color(change_pct)
            pct_str = f"{abs(change_pct):.1f}%"

            self.manager.draw_text(
                'micro', 2, baseline, self.STOCK_WHITE, stock['symbol'])
            self.manager.draw_text(
                'tiny_bold', 64 - len(price_str) * 6, baseline,
                self.STOCK_YELLOW, price_str)
            pct_x = 94 - len(pct_str) * 4
            self._draw_change_triangle(pct_x - 7, baseline - 4, change_pct, color)
            self.manager.draw_text('micro', pct_x, baseline, color, pct_str)

        self.manager.swap_canvas()

    def _draw_sparkline_frame(
        self, stock: dict[str, Any], tick: float | None = None
    ) -> None:
        """One index in detail with its intraday chart"""
        self.manager.clear_canvas()
        self._draw_header(tick)

        price_str = self._format_price(stock['price'])
        change_pct = stock['change_pct']
        color = self._change_color(change_pct)

        self.manager.draw_text(
            'tiny_bold', 2, 21, self.STOCK_WHITE, stock['symbol'])
        self.manager.draw_text(
            'tiny_bold', 94 - len(price_str) * 6, 21,
            self.STOCK_YELLOW, price_str)

        # Intraday chart across the middle of the screen
        points = self._scale_points(stock['sparkline'], 3, 24, 90, 16)
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            steps = max(abs(x2 - x1), abs(y2 - y1))
            for s in range(steps + 1):
                px = x1 + round((x2 - x1) * s / steps) if steps else x1
                py = y1 + round((y2 - y1) * s / steps) if steps else y1
                self.manager.draw_pixel(px, py, *color)
        # Blinking dot on the latest price
        if points and (tick is None or int(tick * 2) % 2):
            lx, ly = points[-1]
            for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
                self.manager.draw_pixel(
                    lx + dx, ly + dy, *self.STOCK_WHITE)

        # Day change along the bottom
        sign = '+' if change_pct > 0 else '-' if change_pct < 0 else ''
        pct_str = f"{sign}{abs(change_pct):.2f}% TODAY"
        pct_x = max(2, (DisplayConfig.MATRIX_COLS - len(pct_str) * 4) // 2)
        self._draw_change_triangle(pct_x - 7, 43, change_pct, color)
        self.manager.draw_text('micro', pct_x, 47, color, pct_str)

        self.manager.swap_canvas()

    def _draw_no_data_frame(self, tick: float | None = None) -> None:
        self.manager.clear_canvas()
        self._draw_header(tick)
        self.manager.draw_text(
            'micro', 20, 32, self.STOCK_WHITE, 'NO MARKET DATA')
        self.manager.swap_canvas()

    def display_stock_ticker(self, duration: int = 180) -> None:
        """Display the market dashboard, cycling through index sparklines"""
        stocks = self._get_stock_data()

        start_time = time.time()
        while time.time() - start_time < duration:
            try:
                tick = time.time()
                if not stocks:
                    self._draw_no_data_frame(tick)
                    time.sleep(1)
                    stocks = self._get_stock_data()
                    continue

                view, index = self._view_for_tick(
                    tick - start_time, len(stocks))
                if view == 'sparkline' and len(
                        stocks[index].get('sparkline', [])) >= 2:
                    self._draw_sparkline_frame(stocks[index], tick)
                else:
                    self._draw_dashboard_frame(stocks, tick)

                time.sleep(0.25)
                stocks = self._get_stock_data()

            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"Error in stock ticker display: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(1)

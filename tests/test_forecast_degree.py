"""Degree-symbol placement in the 3-day forecast rows.

The symbol used to sit at a hardcoded x that assumed a two-digit temperature,
so a 3-digit one (100+) drew the 'o' on top of the last digit.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from weather_display import WeatherDisplay

TINY_BOLD_CHAR_W = 5   # fonts/5x8.bdf
HIGH_X = 30
LOW_X = 54


def draw(temp_high: int, temp_low: int) -> list[tuple]:
    """Render one forecast row and return the draw_text calls."""
    display = WeatherDisplay(MagicMock())
    display.forecast_data = {'list': []}
    forecasts = [{
        'day': 'MON',
        'temp_high': temp_high,
        'temp_low': temp_low,
        'condition': 'Clear',
    }]
    with patch.object(display, '_build_daily_forecasts', return_value=forecasts), \
            patch.object(display, '_load_weather_icon', return_value=None):
        display._draw_forecast()
    return [c.args for c in display.manager.draw_text.call_args_list]


def degree_x(calls: list[tuple], color: tuple) -> int:
    """x of the 'o' degree glyph drawn in the given colour."""
    return next(c[1] for c in calls
                if c[0] == 'micro' and c[4] == 'o' and c[3] == color)


def temp_call(calls: list[tuple], text: str) -> tuple:
    return next(c for c in calls if c[4] == text)


class TestDegreeSymbolPlacement:
    def test_two_digit_placement_unchanged(self):
        # Regression guard: the common case must keep its existing look.
        calls = draw(85, 62)
        high_color = temp_call(calls, '85')[3]
        low_color = temp_call(calls, '62')[3]
        assert degree_x(calls, high_color) == 42
        assert degree_x(calls, low_color) == 66

    def test_three_digit_high_does_not_overlap_digits(self):
        calls = draw(100, 78)
        high_color = temp_call(calls, '100')[3]
        end_of_digits = HIGH_X + len('100') * TINY_BOLD_CHAR_W
        assert degree_x(calls, high_color) >= end_of_digits

    def test_three_digit_low_does_not_overlap_digits(self):
        calls = draw(105, 100)
        low_color = temp_call(calls, '100')[3]
        end_of_digits = LOW_X + len('100') * TINY_BOLD_CHAR_W
        assert degree_x(calls, low_color) >= end_of_digits

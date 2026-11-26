"""Holiday facts - pixel art and facts on the holiday itself, silent otherwise"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable

from scoreboard_config import DisplayConfig, RGBColor

EFFECTS: tuple[str, ...] = (
    'snow', 'leaves', 'hearts', 'confetti', 'fireworks', 'twinkle', 'none')

# Advance of each font used for holiday lettering, for centering
_CHAR_WIDTH: dict[str, int] = {
    'medium_bold': 9, 'small_bold': 6, 'tiny_bold': 5}

WHITE: RGBColor = (255, 255, 255)
CREAM: RGBColor = (255, 240, 200)
GOLD: RGBColor = (255, 210, 60)
RED: RGBColor = (240, 60, 60)
PINK: RGBColor = (255, 110, 160)
ORANGE: RGBColor = (255, 140, 40)
GREEN: RGBColor = (70, 220, 100)
BLUE: RGBColor = (90, 170, 255)
PURPLE: RGBColor = (190, 120, 255)
LAVENDER: RGBColor = (205, 195, 225)
TAN: RGBColor = (215, 165, 100)


@dataclass(frozen=True)
class TextLine:
    """One line of lettering drawn over the art"""
    font: str
    x: int
    baseline: int
    color: RGBColor
    text: str


@dataclass(frozen=True)
class Holiday:
    slug: str
    rule: Callable[[int], date]  # year -> the date it falls on
    effect: str
    card_left: int  # x where the card's lettering region starts
    band_left: int  # same for the facts band
    card_text: tuple[TextLine, ...]
    band_text: tuple[TextLine, ...]
    effect_colors: tuple[RGBColor, ...] = ()


def easter_date(year: int) -> date:
    """Western Easter by the anonymous Gregorian (Meeus) algorithm"""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    el = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * el) // 451
    month, day = divmod(h + el - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _fixed(month: int, day: int) -> Callable[[int], date]:
    return lambda year: date(year, month, day)


def _nth_weekday(month: int, weekday: int, n: int) -> Callable[[int], date]:
    """The nth given weekday (Monday=0) of a month"""
    def rule(year: int) -> date:
        first = date(year, month, 1)
        offset = (weekday - first.weekday()) % 7
        return first + timedelta(days=offset + 7 * (n - 1))
    return rule


def _before_easter(days: int) -> Callable[[int], date]:
    return lambda year: easter_date(year) - timedelta(days=days)


def _lines(left: int, *specs: tuple[str, int, RGBColor, str]
           ) -> tuple[TextLine, ...]:
    """Lines centered in the region from `left` to the right edge;
    each spec is (font, baseline, color, text)"""
    region = DisplayConfig.MATRIX_COLS - left
    return tuple(
        TextLine(font, left + (region - len(text) * _CHAR_WIDTH[font]) // 2,
                 baseline, color, text)
        for font, baseline, color, text in specs)


def _holiday(slug: str, rule: Callable[[int], date], effect: str,
             card: tuple[tuple[str, int, RGBColor, str], ...],
             band: tuple[tuple[str, int, RGBColor, str], ...],
             card_left: int = 40, band_left: int = 34,
             effect_colors: tuple[RGBColor, ...] = ()) -> Holiday:
    return Holiday(slug, rule, effect, card_left, band_left,
                   _lines(card_left, *card), _lines(band_left, *band),
                   effect_colors)


M, S, T = 'medium_bold', 'small_bold', 'tiny_bold'

HOLIDAYS: tuple[Holiday, ...] = (
    _holiday('new_years_day', _fixed(1, 1), 'confetti',
             ((M, 20, WHITE, 'HAPPY'), (S, 36, GOLD, 'NEW YEAR')),
             ((S, 12, WHITE, 'HAPPY'), (S, 24, GOLD, 'NEW YEAR'))),
    _holiday('groundhog_day', _fixed(2, 2), 'snow',
             ((S, 21, TAN, 'GROUNDHOG'), (M, 38, WHITE, 'DAY')),
             ((S, 12, TAN, 'GROUNDHOG'), (S, 24, WHITE, 'DAY'))),
    _holiday('valentines_day', _fixed(2, 14), 'hearts',
             ((S, 15, WHITE, 'HAPPY'), (T, 27, PINK, "VALENTINE'S"),
              (S, 41, WHITE, 'DAY')),
             ((T, 12, PINK, "VALENTINE'S"), (S, 24, WHITE, 'DAY'))),
    _holiday('st_patricks_day', _fixed(3, 17), 'confetti',
             ((S, 15, WHITE, 'HAPPY'), (T, 27, GREEN, "ST. PATRICK'S"),
              (S, 41, GOLD, 'DAY')),
             ((T, 12, GREEN, "ST. PATRICK'S"), (S, 24, GOLD, 'DAY')),
             card_left=30, band_left=30,
             effect_colors=((40, 170, 70), (90, 230, 110), GOLD)),
    _holiday('palm_sunday', _before_easter(7), 'none',
             ((M, 20, GREEN, 'PALM'), (M, 38, CREAM, 'SUNDAY')),
             ((S, 12, GREEN, 'PALM'), (S, 24, CREAM, 'SUNDAY'))),
    _holiday('good_friday', _before_easter(2), 'none',
             ((M, 20, LAVENDER, 'GOOD'), (M, 38, LAVENDER, 'FRIDAY')),
             ((S, 12, LAVENDER, 'GOOD'), (S, 24, LAVENDER, 'FRIDAY'))),
    _holiday('easter', easter_date, 'none',
             ((M, 20, CREAM, 'HAPPY'), (M, 38, PINK, 'EASTER')),
             ((S, 12, CREAM, 'HAPPY'), (S, 24, PINK, 'EASTER'))),
    _holiday('april_fools', _fixed(4, 1), 'confetti',
             ((S, 15, GOLD, 'APRIL'), (S, 28, PURPLE, "FOOLS'"),
              (S, 41, BLUE, 'DAY')),
             ((S, 12, GOLD, 'APRIL'), (S, 24, PURPLE, "FOOLS' DAY"))),
    _holiday('earth_day', _fixed(4, 22), 'twinkle',
             ((M, 20, WHITE, 'HAPPY'), (S, 36, GREEN, 'EARTH DAY')),
             ((S, 12, BLUE, 'EARTH'), (S, 24, GREEN, 'DAY'))),
    _holiday('cinco_de_mayo', _fixed(5, 5), 'confetti',
             ((M, 20, RED, 'CINCO'), (S, 36, GREEN, 'DE MAYO')),
             ((S, 12, RED, 'CINCO'), (S, 24, GREEN, 'DE MAYO')),
             effect_colors=(RED, WHITE, (60, 200, 90), GOLD)),
    _holiday('mothers_day', _nth_weekday(5, 6, 2), 'hearts',
             ((S, 15, WHITE, 'HAPPY'), (S, 28, PINK, "MOTHER'S"),
              (S, 41, WHITE, 'DAY')),
             ((S, 12, PINK, "MOTHER'S"), (S, 24, WHITE, 'DAY'))),
    _holiday('fathers_day', _nth_weekday(6, 6, 3), 'none',
             ((S, 15, WHITE, 'HAPPY'), (S, 28, BLUE, "FATHER'S"),
              (S, 41, WHITE, 'DAY')),
             ((S, 12, BLUE, "FATHER'S"), (S, 24, WHITE, 'DAY'))),
    _holiday('independence_day', _fixed(7, 4), 'fireworks',
             ((S, 15, WHITE, 'HAPPY'), (S, 28, RED, '4TH OF'),
              (S, 41, BLUE, 'JULY')),
             ((S, 12, RED, '4TH OF'), (S, 24, BLUE, 'JULY'))),
    _holiday('halloween', _fixed(10, 31), 'twinkle',
             ((M, 20, ORANGE, 'HAPPY'), (S, 36, PURPLE, 'HALLOWEEN')),
             ((S, 12, ORANGE, 'HAPPY'), (S, 24, PURPLE, 'HALLOWEEN'))),
    _holiday('thanksgiving', _nth_weekday(11, 3, 4), 'leaves',
             ((M, 20, GOLD, 'HAPPY'), (T, 35, ORANGE, 'THANKSGIVING')),
             ((S, 12, GOLD, 'HAPPY'), (T, 24, ORANGE, 'THANKSGIVING')),
             card_left=34),
    _holiday('christmas_eve', _fixed(12, 24), 'twinkle',
             ((S, 21, CREAM, 'CHRISTMAS'), (M, 38, WHITE, 'EVE')),
             ((S, 12, CREAM, 'CHRISTMAS'), (S, 24, WHITE, 'EVE'))),
    _holiday('christmas', _fixed(12, 25), 'snow',
             ((M, 20, RED, 'MERRY'), (S, 36, WHITE, 'CHRISTMAS')),
             ((S, 12, RED, 'MERRY'), (S, 24, WHITE, 'CHRISTMAS'))),
    _holiday('new_years_eve', _fixed(12, 31), 'fireworks',
             ((S, 21, GOLD, "NEW YEAR'S"), (M, 38, WHITE, 'EVE')),
             ((S, 12, GOLD, "NEW YEAR'S"), (S, 24, WHITE, 'EVE')),
             card_left=36),
)

HOLIDAYS_BY_SLUG: dict[str, Holiday] = {h.slug: h for h in HOLIDAYS}

# One holiday per day: these win when two rules land on the same date,
# so Good Friday never shares the screen with April Fools' or Earth Day
_WINS_CLASH: tuple[str, ...] = ('palm_sunday', 'good_friday', 'easter')


def holiday_on(day: date) -> Holiday | None:
    """The one holiday that falls on this date, if any"""
    matches = [h for h in HOLIDAYS if h.rule(day.year) == day]
    for holiday in matches:
        if holiday.slug in _WINS_CLASH:
            return holiday
    return matches[0] if matches else None

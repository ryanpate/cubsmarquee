"""Holiday facts - pixel art and facts on the holiday itself, silent otherwise"""

from __future__ import annotations

import json
import math
import random
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Callable

import pendulum
from PIL import Image, ImageChops

from scoreboard_config import (
    DisplayConfig, GameConfig, RGBColor, get_scroll_delay, load_user_config)
from teams import data_path_candidates

if TYPE_CHECKING:
    from scoreboard_manager import ScoreboardManager

ART_DIR = 'holidays'

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
             ((S, 10, WHITE, 'HAPPY'), (S, 22, GREEN, 'ST.'),
              (S, 34, GREEN, "PATRICK'S"), (S, 46, GOLD, 'DAY')),
             ((T, 12, GREEN, "ST. PATRICK'S"), (S, 24, GOLD, 'DAY')),
             band_left=30,
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


def load_holiday_facts() -> dict[str, list[str]]:
    """Facts keyed by holiday slug; empty when the file is unreadable"""
    for path in data_path_candidates('holiday_facts.json'):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except (OSError, ValueError):
            continue
    print('holiday_facts.json not found')
    return {}


# ---------------------------------------------------------------------------
# Effects: each is a pure function of the tick, so a frame can be redrawn
# (or rendered for a preview) without any state
# ---------------------------------------------------------------------------

COLS = DisplayConfig.MATRIX_COLS
BAND_ROWS = 30
FACT_BASELINE = 45

_CONFETTI: tuple[RGBColor, ...] = (
    (255, 90, 90), (255, 210, 60), (90, 200, 255),
    (120, 230, 120), (240, 130, 240), (255, 160, 60))
_LEAVES: tuple[RGBColor, ...] = (
    (210, 70, 30), (240, 140, 30), (250, 205, 60), (175, 95, 35))
_HEARTS: tuple[RGBColor, ...] = ((255, 90, 130), (255, 170, 190), (235, 40, 70))
_FIREWORKS: tuple[RGBColor, ...] = (
    (255, 80, 80), (255, 220, 90), (120, 180, 255), (255, 255, 255),
    (120, 255, 150))


def _plot(manager, sky, height: int, x: int, y: int, color: RGBColor) -> None:
    """One effect pixel, clipped to the rows above `height` and, when a
    sky mask is given, to open sky"""
    if not (0 <= x < COLS and 0 <= y < height):
        return
    if sky is not None and not sky.getpixel((x, y)):
        return
    manager.draw_pixel(x, y, *color)


def _snow(manager, tick: float, height: int, colors, sky) -> None:
    for i in range(height * 3 // 10):
        x = (i * 37 + 11 + int(1.5 * math.sin(tick * 0.8 + i))) % COLS
        y = int(i * 13 + tick * (5 + (i * 7) % 6)) % height
        _plot(manager, None, height, x, y, WHITE)
        if i % 3 == 0:  # nearer flakes, the weather screen's soft shape
            for dx, dy in ((-1, 0), (1, 0), (0, -1)):
                _plot(manager, None, height, x + dx, y + dy, (240, 240, 245))


def _leaves(manager, tick: float, height: int, colors, sky) -> None:
    for i in range(height // 4):
        x = (i * 41 + 7 + int(4 * math.sin(tick * 1.3 + i * 2))) % COLS
        y = int(i * 17 + tick * (4 + i % 4)) % height
        color = _LEAVES[i % len(_LEAVES)]
        lean = 1 if int(tick * 2 + i) % 2 else -1
        _plot(manager, None, height, x, y, color)
        _plot(manager, None, height, x + lean, y + 1, color)


def _hearts(manager, tick: float, height: int, colors, sky) -> None:
    for i in range(height // 6):
        x = (i * 43 + 9 + int(2 * math.sin(tick + i * 1.9))) % COLS
        y = height + 2 - int(i * 11 + tick * (4 + i % 3)) % (height + 6)
        color = _HEARTS[i % len(_HEARTS)]
        for dx, dy in ((-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1), (0, 2)):
            _plot(manager, None, height, x + dx, y + dy, color)


def _confetti(manager, tick: float, height: int, colors, sky) -> None:
    palette = colors or _CONFETTI
    for i in range(height * 5 // 8):
        x = (i * 29 + 13) % COLS
        y = int(i * 11 + tick * (6 + (i * 7) % 9)) % height
        color = palette[i % len(palette)]
        _plot(manager, None, height, x, y, color)
        _plot(manager, None, height, x, (y + 1) % height, color)


def _fireworks(manager, tick: float, height: int, colors, sky) -> None:
    period, reach = 2.4, 6 + height // 8
    ceiling = height - 3  # stay clear of the skyline / ground rows
    for slot in range(3):
        clock = tick + slot * 0.8
        burst, phase = int(clock / period), (clock % period) / period
        cx = 6 + (burst * 37 + slot * 53) % (COLS - 12)
        cy = 5 + (burst * 19 + slot * 29) % max(1, height // 2 - 4)
        color = _FIREWORKS[(burst + slot) % len(_FIREWORKS)]
        if phase < 0.2:  # the rocket climbing
            y = height - 1 - int(phase / 0.2 * (height - 1 - cy))
            _plot(manager, sky, ceiling, cx, y, (255, 240, 200))
            _plot(manager, sky, ceiling, cx, y + 1, (150, 120, 70))
            continue
        spread = (phase - 0.2) / 0.8
        fade = 1.0 - spread ** 3 * 0.7
        for ring, count in ((1.0, 12), (0.55, 8)):
            for k in range(count):
                angle = 2 * math.pi * k / count + ring
                # each spark drags a dimmer tail one step behind it
                for lag, dim in ((0.14, 0.6), (0.0, 1.0)):
                    step = max(0.0, spread - lag)
                    radius = reach * ring * (1 - (1 - step) ** 2)
                    x = cx + int(round(radius * math.cos(angle)))
                    y = cy + int(round(radius * math.sin(angle)
                                       + step * step * reach * 0.35))
                    _plot(manager, sky, ceiling, x, y,
                          tuple(int(c * fade * dim) for c in color))


def _twinkle(manager, tick: float, height: int, colors, sky) -> None:
    for i in range(height // 3):
        x = (i * 29 + 13) % COLS
        y = (i * 17 + 5) % max(1, height * 3 // 5)
        glow = 0.5 + 0.5 * math.sin(tick * 2 + i * 1.7)
        if glow < 0.25:
            continue
        level = int(255 * glow)
        _plot(manager, sky, height - 3, x, y, (level, level, int(level * 0.9)))


_EFFECT_DRAWERS = {
    'snow': _snow, 'leaves': _leaves, 'hearts': _hearts,
    'confetti': _confetti, 'fireworks': _fireworks, 'twinkle': _twinkle,
}


def draw_effect(manager, effect: str, tick: float, height: int,
                colors: tuple[RGBColor, ...] = (),
                sky: Image.Image | None = None) -> None:
    """Draw one frame of an effect on the rows above `height`.

    Falling effects pass in front of the art. Stars and fireworks belong
    behind it: given a `sky` mask they only light pixels of open sky.
    """
    drawer = _EFFECT_DRAWERS.get(effect)
    if drawer is not None:
        drawer(manager, tick, height, colors, sky)


def _sky_mask(art: Image.Image) -> Image.Image:
    """Pixels still showing the plain background. The lettering side of
    every picture is bare background, so the right-hand column gives each
    row's background color."""
    backdrop = art.crop((COLS - 1, 0, COLS, art.height)).resize(
        art.size, Image.NEAREST)
    difference = ImageChops.difference(art, backdrop).convert('L')
    return difference.point(lambda value: 255 if value == 0 else 0)


class HolidayDisplay:
    """Title card, then a picture band with facts, on the holiday itself"""

    def __init__(self, scoreboard_manager: ScoreboardManager) -> None:
        self.manager = scoreboard_manager
        self.facts: dict[str, list[str]] = load_holiday_facts()
        # (picture, sky mask) per '<slug>_card' / '<slug>_band'
        self._art: dict[str, tuple[Image.Image, Image.Image]] = {}
        self._deck: list[str] = []
        self._deck_slug: str | None = None
        self._deck_index: int = 0

    def current_holiday(self, today: date | None = None) -> Holiday | None:
        """Today's holiday, or the one named by the holiday_preview key
        in config.json (for checking a screen on a Pi before its date)"""
        preview = load_user_config().get('holiday_preview')
        if preview in HOLIDAYS_BY_SLUG:
            return HOLIDAYS_BY_SLUG[preview]
        if today is None:
            now = pendulum.now('America/Chicago')
            today = date(now.year, now.month, now.day)
        return holiday_on(today)

    def _picture(self, holiday: Holiday, kind: str
                 ) -> tuple[Image.Image, Image.Image]:
        key = f'{holiday.slug}_{kind}'
        if key not in self._art:
            with Image.open(f'{ART_DIR}/{key}.png') as source:
                art = source.convert('RGB')
            self._art[key] = (art, _sky_mask(art))
        return self._art[key]

    def _next_fact(self, holiday: Holiday) -> str:
        """Walk a shuffled deck, re-dealt only when the holiday changes;
        wrapping without a re-shuffle keeps a fact from repeating back
        to back"""
        if holiday.slug != self._deck_slug:
            deck = self.facts[holiday.slug]
            self._deck = random.sample(deck, len(deck))
            self._deck_slug = holiday.slug
            self._deck_index = 0
        fact = self._deck[self._deck_index]
        self._deck_index = (self._deck_index + 1) % len(self._deck)
        return fact

    def _draw(self, holiday: Holiday, kind: str, lines: tuple[TextLine, ...],
              tick: float) -> None:
        art, sky = self._picture(holiday, kind)
        self.manager.clear_canvas()
        self.manager.set_image(art, 0, 0)
        draw_effect(self.manager, holiday.effect, tick, art.height,
                    holiday.effect_colors, sky)
        for line in lines:
            self.manager.draw_text(
                line.font, line.x, line.baseline, line.color, line.text)

    def draw_card(self, holiday: Holiday, tick: float) -> None:
        """The full-screen title card (does not swap the canvas)"""
        self._draw(holiday, 'card', holiday.card_text, tick)

    def draw_band(self, holiday: Holiday, tick: float, fact: str,
                  scroll_x: int) -> None:
        """Picture band on top, the fact below (does not swap)"""
        self._draw(holiday, 'band', holiday.band_text, tick)
        self.manager.draw_text(
            'medium_bold', scroll_x, FACT_BASELINE, CREAM, fact)

    def display_holiday(self, duration: float = 120) -> bool:
        """Show today's holiday; False when there is nothing to show"""
        holiday = self.current_holiday()
        if holiday is None:
            return False
        if not self.facts.get(holiday.slug):
            print(f'No holiday facts for {holiday.slug}')
            return False
        try:
            self._picture(holiday, 'card')
            self._picture(holiday, 'band')
        except OSError as e:
            print(f'Holiday art missing for {holiday.slug}: {e}')
            return False

        print(f'Displaying holiday facts: {holiday.slug}')
        start = time.time()
        while time.time() - start < min(
                GameConfig.HOLIDAY_CARD_SECONDS, duration):
            self.draw_card(holiday, time.time() - start)
            self.manager.swap_canvas()
            time.sleep(0.1)

        fact = self._next_fact(holiday)
        scroll_x = COLS
        while time.time() - start < duration:
            self.draw_band(holiday, time.time() - start, fact, scroll_x)
            self.manager.swap_canvas()
            scroll_x -= 1
            if scroll_x + len(fact) * _CHAR_WIDTH['medium_bold'] < 0:
                scroll_x = COLS
                fact = self._next_fact(holiday)
            time.sleep(get_scroll_delay(
                load_user_config().get('scroll_speed_holiday_facts', 5)))
        return True

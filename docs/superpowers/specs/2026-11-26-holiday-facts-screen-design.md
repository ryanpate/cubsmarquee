# Holiday Facts Screen

## Intent

On a holiday, the marquee should look like it knows what day it is: a
greeting card with pixel art for that holiday, then fun facts about it.
The rest of the year the screen does not exist. Ryan asked for "graphics
and fun images", so the art is the point, not decoration around a text
scroll.

Today the marquee has no idea when a holiday is. The existing
"Holidays & birthdays" screen (`celebration_display.py`) only fires on
dates hand-typed into `config.json`, draws confetti and `HAPPY X!`, and
has no art.

## Goals

- On each of 18 holidays, and only on that calendar date, a holiday slot
  joins the content rotation.
- Each slot opens with a full-screen title card, then shows a picture
  band with facts about that holiday scrolling underneath.
- Every holiday has its own art and its own facts.
- One switch in the admin console turns the whole screen on or off.
- Every card and band can be rendered to PNG on a Mac for review, and
  any one holiday can be forced onto a real Pi before its date.

## Non-goals

- No run-up or countdown before a holiday, and nothing the day after.
- No per-holiday switches and no way to add holidays from the admin.
- No patriotic/federal days (MLK, Presidents', Memorial, Juneteenth,
  Labor, Veterans) and no other faiths' days. Ryan chose the list below.
- No change to the existing "Holidays & birthdays" screen or its toggle.
- No deploy to any Pi. Merged work reaches them through the nightly
  updater.

## Anti-goals

- A wrong fact on the sign. Facts must be well established; skip
  anything that is "commonly said" but doubtful, and skip statistics
  that go stale.
- A joke screen on a solemn day. Good Friday must never show April
  Fools' content or party effects.
- Muddy art. No shrunk-down photos or generated images; everything is
  drawn at 96x48 for an LED panel.

## What Ryan decided

- The screen appears only on the actual holiday date.
- Holidays: the big ones, family and fun days, Christian calendar days
  (table below).
- Layout "C, then B": full-screen title card first, then a picture band
  on top with the fact scrolling below.
- Art is PNG files, so a picture can be touched up in a pixel editor.
- On an in-season holiday the screen also shows before the game and on
  off days, not only once the rotation starts after the final.

## Approaches considered for the art

1. **PNG art files (chosen).** Two PNGs per holiday in `holidays/`, a
   table row per holiday, one shared renderer. Pixel fixes happen in an
   image editor; adding a holiday is two pictures and a row. Matches how
   the weather icons and logos already work.
2. **Drawn in code at runtime.** No image files and easier moving parts
   inside a scene, but every pixel tweak is a code change and the module
   carries 36 drawing routines.
3. **AI-generated images, downscaled.** Rejected: muddy at 96x48 and
   costs image credits.

The calendar, facts file and rotation slot each had one sensible way to
build, described below.

## The holidays

"Today" is the date in `America/Chicago`, as `celebration_display.py`
already does.

| Slug | Date rule | Greeting | Art subject | Effect |
|------|-----------|----------|-------------|--------|
| `new_years_day` | Jan 1 | HAPPY NEW YEAR | balloons, party hat, streamers | confetti |
| `groundhog_day` | Feb 2 | GROUNDHOG DAY | groundhog in a snowy burrow with its shadow | snow |
| `valentines_day` | Feb 14 | HAPPY VALENTINE'S DAY | big heart with an arrow | hearts |
| `st_patricks_day` | Mar 17 | HAPPY ST. PATRICK'S DAY | shamrock, rainbow, pot of gold | confetti (greens and gold) |
| `palm_sunday` | Easter − 7 days | PALM SUNDAY | palm branches, road to a city gate | none |
| `good_friday` | Easter − 2 days | GOOD FRIDAY | three crosses on a hill, dusk sky | none |
| `easter` | Western Easter | HAPPY EASTER | decorated eggs, bunny, spring grass | none |
| `april_fools` | Apr 1 | APRIL FOOLS' DAY | jester hat | confetti |
| `earth_day` | Apr 22 | HAPPY EARTH DAY | globe, sapling | twinkle |
| `cinco_de_mayo` | May 5 | CINCO DE MAYO | sombrero, maracas, cactus, paper banners | confetti |
| `mothers_day` | 2nd Sunday of May | HAPPY MOTHER'S DAY | bouquet of tulips | hearts |
| `fathers_day` | 3rd Sunday of June | HAPPY FATHER'S DAY | necktie, baseball glove and ball | none |
| `independence_day` | Jul 4 | HAPPY 4TH OF JULY | flag, night skyline | fireworks |
| `halloween` | Oct 31 | HAPPY HALLOWEEN | jack-o'-lantern, bat, moon, ghost | twinkle |
| `thanksgiving` | 4th Thursday of Nov | HAPPY THANKSGIVING | turkey, pumpkin | leaves |
| `christmas_eve` | Dec 24 | CHRISTMAS EVE | star over a Bethlehem stable silhouette | twinkle |
| `christmas` | Dec 25 | MERRY CHRISTMAS | tree, presents, snowy ground | snow |
| `new_years_eve` | Dec 31 | NEW YEAR'S EVE | clock near midnight, skyline | fireworks |

Easter uses the standard Gregorian calculation (anonymous/Meeus
algorithm). No new pip dependency: the updater does not install
packages.

**One holiday per day.** When two rules land on the same date, a
Christian calendar day (`palm_sunday`, `good_friday`, `easter`) wins and
the other is not shown. Easter fell on April 1 in 2018 and does again in
2029; Good Friday was April 22 (Earth Day) in 2011. *(Claude's call.)*

## What it looks like

**Title card** (first 8 seconds of the slot): the 96x48 card PNG, the
effect animating over it, the greeting drawn on top by code.

```
+------------------------------------------------+
|    *        .        .      .                  |
|   /^\   .       M E R R Y        .             |
|  /^^^\      .                                  |
| /^^^^^\   C H R I S T M A S   .                |
|   |_|  [#]                                     |
|________________________________________________|
```

**Facts band** (rest of the slot): the 96x30 band PNG across rows 0–29
with the effect confined to those rows and the holiday name drawn by
code; the fact scrolls across rows 30–47 in `medium_bold` at baseline
45, in the same large font as the other fact screens.

```
+------------------------------------------------+
|   /^\  .    MERRY      .                       |
|  /^^^\[#]   CHRISTMAS       .                  |
|________________________________________________|
|  RUDOLPH WAS CREATED IN 1939 FOR ...     <<<   |
+------------------------------------------------+
```

Lettering is never baked into the PNGs. The table gives each holiday
its text lines, font, position and color for the card and for the band,
so greetings stay crisp and art can be redrawn without re-lettering.
Long names wrap (`HAPPY` / `ST. PATRICK'S` / `DAY`); the band may use a
shortened name and a smaller font where the art leaves less room.
Placement per holiday is the builder's, checked against the previews.

**Effects** are drawn by code over the art and under the text:
`snow`, `leaves`, `hearts`, `confetti`, `fireworks`, `twinkle`, `none`.
Snow should look like the weather screen's snow (white pixel with soft
neighbours); Ryan prefers reusing the weather animations' look. Effects
must be cheap enough that the fact scroll stays smooth. Good Friday and
Palm Sunday have no effect and no confetti-style colors.

## Parts

### `holiday_display.py` (new)

- `easter_date(year)` and `holiday_on(date)`: pure functions, no I/O.
  `holiday_on` returns the one holiday for that date or `None`.
- `HOLIDAYS`: the table above as data (slug, rule, text lines and
  placement for card and band, effect, colors).
- `HolidayDisplay(manager).display_holiday(duration) -> bool`: returns
  `False` at once when today is not a holiday (same contract as
  `CelebrationDisplay.display_celebrations`), otherwise shows the card
  for `GameConfig.HOLIDAY_CARD_SECONDS` (8) and the facts band for the
  rest of `duration`, then returns `True`.
- Facts are shuffled once per day and wrap around the deck without
  re-shuffling, like the Bible facts, so a fact cannot repeat back to
  back.
- A `holiday_preview` key in `config.json` holding a slug forces that
  holiday whatever the date. It is for checking on real hardware, is
  not in the admin, and is documented in `CLAUDE.md`. *(Claude's call.)*

### `holidays/` (new, 36 PNGs)

`<slug>_card.png` is exactly 96x48 and `<slug>_band.png` exactly 96x30,
both RGB. First drafts come from `dev/draw_holiday_art.py`, which sits
with the other asset scripts. Once a PNG has been hand-edited the PNG is
the truth; the script's header must warn that re-running overwrites
hand edits.

### `holiday_facts.json` (new)

`{"<slug>": ["FACT ...", ...]}`, at least 15 facts per holiday.
Uppercase, plain ASCII (the bitmap fonts are latin-1), family friendly,
100 characters or fewer. At the default speed a 100-character fact takes
about 32 seconds to cross, so roughly three show per appearance; that is
accepted rather than lengthening the slot. *(Claude's call.)* Christian
calendar days draw on scripture and church tradition in the register of
`bible_facts.json`; Good Friday facts are plain statements with no
"fun fact" framing or exclamation marks. Easter facts cover both the
resurrection and the traditions (eggs, sunrise services).

### Rotation (`off_season_handler.py`, `scoreboard_config.py`)

A `holiday_facts` slot directly after the existing celebration slot,
gated by `enable_holiday_facts` (default on), lasting
`GameConfig.HOLIDAY_FACTS_DURATION` (2 minutes), once per rotation pass
like every other screen. It follows the celebration slot's pattern: the
between-segment tick only runs when the screen actually showed.

### In-season holidays (`game_state_handler.py`)

About half the list falls in the baseball season, and on a Pi in
`display_mode: auto` the rotation does not run before a game or on an
off day: `display_no_game` loops on the next-game scroll and standings
until the game state changes. Ryan decided the holiday screen shows all
day there too.

In that loop's non-cycling path (regular season and postseason, i.e.
where `cycle_content` is false and the game is not spring training),
one holiday pass runs after the standings / playoff screens on each
trip round, giving next game, standings, holiday, repeat. It uses the
same `display_holiday()` call, toggle and duration as the rotation
slot, reached through the `off_season_handler` reference the loop
already uses for the NFL and basketball checks, and does nothing when
today is not a holiday. The `cycle_content` and spring-training paths
are unchanged because the rotation already follows them. Live games
still take the whole screen.

### Admin (`wifi_config_server.py`)

- Toggle `enable_holiday_facts` in the "Faith & fun" group: **Holiday
  fun facts** — "On holidays like Christmas, Easter and Thanksgiving,
  shows a themed picture and fun facts about the day. Only appears on
  the holiday itself."
- Speed slider `scroll_speed_holiday_facts` (default 5) with the other
  fact-screen sliders. *(Claude's call; every other facts screen has
  one.)*
- Both keys go through the same five places each existing toggle and
  slider does: allowed-keys list, defaults, template, load script, save
  script.

### Previews (`tools/render_holiday_previews.py`, new)

Modeled on `tools/render_ncaab_previews.py`: renders the card and the
band of all 18 holidays to `holiday_previews/` at 1x and 8x, plus one
contact sheet of everything. This is how Ryan reviews the art.

### Tests

- Date rules against known years: Easter 2026-04-05, 2027-03-28,
  2028-04-16; Thanksgiving 2026-11-26 and 2027-11-25; Mother's Day
  2027-05-09; Father's Day 2027-06-20; an ordinary day returns `None`.
- Collision: 2029-04-01 is `easter`, not `april_fools`.
- Completeness: every holiday has both PNGs at the exact size and at
  least 15 facts; every fact is uppercase ASCII within the length limit.
- The rotation slot is skipped when the toggle is off and when today is
  not a holiday; `holiday_preview` forces one.
- The pre-game loop shows the holiday pass on a holiday in its
  non-cycling path, and not in the `cycle_content` or spring-training
  paths.
- The two admin keys save and load, and the existing rotation tests that
  enumerate segments and toggles include the new ones.

### `CLAUDE.md`

Add the new files to the tables, the two config keys and
`holiday_preview`, and the preview command.

## Left to the builder

- The pixel art itself, within the subjects above, and where the text
  sits on each card and band.
- How the effects are implemented, and their colors and density.
- The facts themselves, within the rules above.
- Module internals and test layout.

## Calls Claude made that Ryan should check

1. Easter art is eggs, bunny and spring grass; Palm Sunday, Good Friday
   and Christmas Eve carry the sacred imagery. Christmas Day is the tree
   and presents.
2. One holiday per day, Christian calendar days winning a clash.
3. The screen shows once per rotation pass for 2 minutes (8-second card,
   then facts), the same weight as any other screen on the holiday.
4. A scroll-speed slider is added alongside the toggle.
5. A hidden `holiday_preview` config key exists for testing on a Pi.
6. The existing "Holidays & birthdays" toggle keeps its label, although
   it will now sit next to "Holiday fun facts" and only covers
   hand-entered dates.

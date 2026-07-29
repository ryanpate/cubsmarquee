# Admin Config Control Audit

Audit of `wifi_config_server.py`'s config tab: every control's HTML id, its
presence in the `saveConfig()` JS payload, its restoration on page load, its
server-side default in `load_config()`, and whether the scoreboard Python
code actually reads the key. Produced for Task 7 of the multi-team-support
plan; feeds Task 8's admin redesign (dead rows below must not be carried
into the new layout without a human decision).

## Methodology

Four inventories were extracted directly from `wifi_config_server.py`:

1. **HTML control ids** — every `<input>`/`<select>`/`<textarea>` id inside
   the `config-tab` div (lines 572-930).
2. **`saveConfig()` payload keys** — the JS object built and POSTed to
   `/save_config` (lines 1282-1338).
3. **Page-load restore** — keys assigned in `window.onload` (lines
   1034-1136). Three keys (`zip_code`, `weather_api_key`, `custom_message`)
   are restored a different way: their HTML `value`/textarea content is
   rendered server-side via Jinja (`{{ config.x }}`) rather than set by the
   `window.onload` JS. That's a real, working round-trip — just a different
   mechanism — so these are marked OK with a note rather than BROKEN.
4. **`load_config()` server defaults** (lines 138-188) — the dict returned
   when `/home/pi/config.json` doesn't yet have a key.

For each key, its Python consumer was found with:

```bash
grep -rn "\.get('<key>'" --include="*.py" . | grep -v wifi_config_server | grep -v tests
```

A first pass using a looser pattern (`grep "'<key>'"` anywhere in a `.py`
file) produced false positives: a key can appear as a *default-dict entry*
(e.g. `off_season_handler.py`'s own `_load_config()` default dict, or a
purely decorative field) without ever being read back with `.get(...)`.
Two keys — `scroll_speed_stocks` and `flight_tracking_address` — looked like
they had consumers under the loose grep but have none under the strict one;
they are genuinely dead. Two other keys — `adsb_receiver_url` and
`flight_max_range_nm` — looked consumer-less under a naive single-line
`.get('key'` grep only because `flight_display.py` wraps the call across two
lines (`config.get(\n    'key', default)`); manual inspection confirmed both
have real consumers.

Verdicts:
- **OK** — all four layers agree and a real Python consumer exists.
- **BROKEN** — a control exists but the layers disagree (fixed in this task).
- **DEAD** — all four layers agree, but no Python code ever reads the value
  (left in place; removal deferred to Task 8 pending human sign-off, per
  this task's brief).

## Audit table

| Key | In HTML | In saveConfig | Restored on load | Server default | Consumer | Verdict |
|---|---|---|---|---|---|---|
| `display_mode` | yes | yes | yes | yes (`'auto'`) | `main.py`, `off_season_handler.py` | OK |
| `enable_weather` | yes | yes | yes | yes | `off_season_handler.py` | OK |
| `enable_bears` | yes | yes | yes | yes | `off_season_handler.py` | OK |
| `enable_bears_news` | yes | yes | yes | yes | `off_season_handler.py` | OK |
| `enable_pga` | yes | yes | yes | yes | `off_season_handler.py` | OK |
| `enable_pga_news` | yes | yes | yes | yes | `off_season_handler.py` | OK |
| `enable_pga_facts` | yes | yes | yes | yes | `off_season_handler.py` | OK |
| `enable_cubs_facts` | yes | yes | yes | yes | `off_season_handler.py` | OK |
| `enable_cubs_news` | yes | yes | yes | yes | `off_season_handler.py` | OK |
| `enable_bible` | yes | yes | yes | yes | `off_season_handler.py` | OK |
| `enable_bible_facts` | yes | yes | yes | yes | `off_season_handler.py` | OK |
| `enable_newsmax` | yes | yes | yes | yes | `off_season_handler.py` | OK |
| `enable_stocks` | yes | yes | yes | yes | `off_season_handler.py` | OK |
| `enable_spring_training` | yes | yes | yes | yes | `off_season_handler.py` | OK |
| `enable_playoff_race` | yes | yes | yes | yes | `game_state_handler.py` | OK |
| `enable_flights` | yes | yes | yes | yes | `live_game_handler.py`, `off_season_handler.py` | OK |
| `enable_flight_radar` | yes | yes | yes | yes | `flight_display.py` | OK |
| `enable_clock` | yes | yes | yes | yes | `off_season_handler.py` | OK |
| `enable_cubs_history` | yes | yes | yes | yes | `off_season_handler.py` | OK |
| `enable_sky` | yes | yes | yes | yes | `off_season_handler.py` | OK |
| `enable_iss` | yes | yes | yes | yes | `off_season_handler.py` | OK |
| `enable_celebrations` | yes | yes | yes | yes | `off_season_handler.py` | OK |
| `flights_between_displays` | yes | yes | yes | yes | `off_season_handler.py` | OK |
| `scroll_speed_bears` | yes | yes | yes | yes | `bears_display.py` | OK |
| `scroll_speed_bears_news` | yes | yes | yes | yes | `off_season_handler.py` | OK |
| `scroll_speed_pga` | yes | yes | yes | yes | `pga_display.py` | OK |
| `scroll_speed_pga_news` | yes | yes | yes | yes | `pga_display.py` | OK |
| `scroll_speed_pga_facts` | yes | yes | yes | yes | `pga_display.py` | OK |
| `scroll_speed_cubs_facts` | yes | yes | yes | yes | `game_state_handler.py`, `off_season_handler.py` | OK |
| `scroll_speed_cubs_news` | yes | yes | yes | yes | `off_season_handler.py` | OK |
| `scroll_speed_bible` | yes | yes | yes | yes | `bible_display.py` | OK |
| `scroll_speed_bible_facts` | yes | yes | yes | yes | `bible_display.py` | OK |
| `scroll_speed_newsmax` | yes | yes | yes | yes | `newsmax_display.py` | OK |
| `scroll_speed_stocks` | yes | yes | yes | yes | **none** | **DEAD** (no consumer — `stock_display.py` never reads a scroll speed) |
| `scroll_speed_spring_training` | yes | yes | yes | yes | `spring_training_display.py` | OK |
| `scroll_speed_flights` | yes | yes | yes | yes | `flight_display.py` | OK |
| `flight_tracking_latitude` | yes | yes | yes | yes | `flight_display.py` | OK |
| `flight_tracking_longitude` | yes | yes | yes | yes | `flight_display.py` | OK |
| `flight_tracking_address` | yes | yes | yes | yes | **none** | **DEAD** (persisted so the admin page shows what the user typed and JS can re-geocode, but no Python display code ever reads it) |
| `flight_source` | yes (radio group) | yes | yes | yes (`'adsb_lol'`) | `flight_display.py` | OK |
| `adsb_receiver_url` | yes (dual: Jinja `value=` + JS restore) | yes | yes | yes | `flight_display.py` | OK |
| `flight_max_range_nm` | yes (dual: Jinja `value=` + JS restore) | yes | yes | yes | `flight_display.py` | OK |
| `airlabs_api_key` | yes (dual: Jinja `value=` + JS restore) | yes | yes | yes | `flight_display.py` | OK |
| `zip_code` | yes (Jinja `value=`) | yes | yes, via Jinja render not JS | yes | `weather_display.py`, `off_season_handler.py` | OK |
| `weather_api_key` | yes (Jinja `value=`) | yes | yes, via Jinja render not JS | yes | `weather_display.py`, `off_season_handler.py` | OK |
| `custom_message` | yes (Jinja textarea content) | yes | yes, via Jinja render not JS | yes | `off_season_handler.py` | OK |
| `brightness` | yes | yes | yes | yes (`100`) | `scoreboard_manager.py`, `weather_display.py` | OK |
| `dim_enabled` | yes | yes | yes | **was missing** | `scoreboard_manager.py` | **BROKEN → fixed** (added `'dim_enabled': False` to `load_config()` defaults) |
| `dim_start` | yes | yes | yes | **was missing** | `scoreboard_manager.py` | **BROKEN → fixed** (added `'dim_start': '22:00'`) |
| `dim_end` | yes | yes | yes | **was missing** | `scoreboard_manager.py` | **BROKEN → fixed** (added `'dim_end': '07:00'`) |
| `dim_brightness` | yes | yes | yes | **was missing** | `scoreboard_manager.py` | **BROKEN → fixed** (added `'dim_brightness': 30`) |

**Totals: 45 OK, 4 BROKEN (all fixed), 2 DEAD.**

## Fix applied

`load_config()`'s `default_config` dict (around line 140) was missing
`dim_enabled`, `dim_start`, `dim_end`, and `dim_brightness`. Every other
layer (HTML control, `saveConfig()` payload, `window.onload` restore, and
the `/save_config` route's own validated defaults at lines 1876-1879) already
agreed on these keys and their defaults (`False`, `'22:00'`, `'07:00'`,
`30`). Because `save_config()` always writes the *full* merged config back
to `config.json`, the missing defaults were self-healing after the first
save — but before any save (e.g. a fresh Pi), `load_config()` returned a
dict without these keys, disagreeing with the other three layers. Added the
four missing keys to `load_config()`'s default dict with values matching
the save route's own fallbacks, so all four layers now agree unconditionally.

No other round-trip bugs were found; no other server code needed to change.

## Out-of-scope finding: `enable_allstar`

While tracing consumers, one additional config key surfaced:
`enable_allstar`, read at `off_season_handler.py:780`
(`self.config.get('enable_allstar', True)`) and defined only in that file's
own internal default dict (`off_season_handler.py:180`). It has **no
admin UI at all** — no HTML control, no `saveConfig()` entry, no restore
JS, and no `load_config()` default in `wifi_config_server.py`. This isn't a
round-trip bug on an existing control (which is what this task's brief
scopes "BROKEN" fixes to) — it's a toggle that was never exposed to the
admin panel in the first place. It's called out here, not fixed, so Task 8's
redesign can decide whether to add a control for it.

## Dead rows carried forward (not removed)

Per this task's scope, dead controls are **not** deleted here:

- `scroll_speed_stocks` — slider round-trips correctly but
  `stock_display.py` has no scroll-speed-driven animation to apply it to.
- `flight_tracking_address` — text field round-trips correctly (and drives
  the client-side "Calculate Coordinates" geocode button), but the address
  string itself is never read by any Python display code; only the derived
  `flight_tracking_latitude`/`flight_tracking_longitude` are consumed.

These stay in the admin panel as-is until a human decides whether to remove
them in Task 8.

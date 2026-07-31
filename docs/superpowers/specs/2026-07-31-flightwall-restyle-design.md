# FlightWall-Style Flight Display Restyle

**Date:** 2026-07-31
**Status:** Approved design, pending implementation plan

## Goal

Restyle all flight-tracking screens in `flight_display.py` to match the visual
language of the FlightWall Mini LED display
(https://theflightwall.com/products/flightwall-mini-flight-tracking-led-display):
pure black background, pixel-art airline logo, mixed-case terminal-style text,
white labels with cyan data values.

The FlightWall Mini is 128x64; our matrix is 96x48 (exactly 3/4 scale in each
dimension), so the layout translates directly with smaller fonts and a smaller
logo.

## Scope

All three flight screens are restyled. **No data-fetching, rotation, or timing
logic changes.**

1. Detail card (`_draw_detail_frame`) — full FlightWall card layout
2. Summary view (`_display_summary_view`) — restyle only
3. Radar view (`_display_radar_view`) — restyle only

The `_display_no_location` and `_display_no_flights` screens adopt the black
background and text styling so no screen keeps the old gradient header.

## Shared Aesthetic

- **Background:** pure black on every flight screen. The sky-gradient header,
  its cached background image (`_create_flight_header_background`), and the
  header airplane silhouette with blinking beacon are removed from all screens
  (the summary keeps a small plane motif, see below).
- **Color system:** labels and names in white; data values in cyan.
  New constant `Colors.FLIGHT_CYAN = (120, 220, 255)` in
  `scoreboard_config.py` (exact shade tunable during visual review).
- **Case:** mixed-case text wherever shown ("United", "Flying to",
  "A321neo"). Airline names from `AIRLINE_NAMES` are title-cased for display.
- **Fonts:** ID lines (airline/route/type) use 5x7 `tiny` or 6x9 (proportional
  match to FlightWall) — final choice made visually via the render script.
  Metric lines use 4x6 `micro` (22-char metric line = 88px, fits in 96).

## Detail Card Layout (96x48)

```
+--------------------------------+
| [20x20 ]  United               |  logo at (2,2); 3 ID lines beside it, white
| [logo  ]  ORD-LAX              |
| [      ]  A321neo              |
|                                |
| Alt:4.1kft Spd:250mph          |  page A: labels white, values cyan (micro)
| Trk:263deg Vr:-1088fpm         |
+--------------------------------+
```

- **Line 1:** airline display name (title-cased), fallback to callsign.
- **Line 2:** route `ORD-LAX` when `origin_iata`/`dest_iata` known; fallback
  to callsign (if line 1 shows airline) or registration.
- **Line 3:** aircraft type code; blank if unknown.
- **Bottom section alternates every 4 seconds:**
  - **Page A (metrics):** `Alt:4.1kft Spd:250mph` / `Trk:263deg Vr:-1088fpm`.
    Labels (`Alt:` etc.) white, values cyan.
  - **Page B (destination):** `Flying to` (white) / destination city (cyan),
    e.g. `Chicago`. Falls back to registration line when destination unknown.
- **Units:** altitude in kft (one decimal below 10k, e.g. `4.1kft`; whole
  above, e.g. `34kft`), speed mph, track degrees, vertical rate fpm (native
  ADS-B units).
- **Counter:** dim gray `2/5` (flight N of M) bottom-right in micro font,
  replacing the old "N OF M" header text.
- Removed from this screen: aircraft category icon, climb/descend triangle,
  compass arrow, cardinal direction, altitude-based text coloring
  (`_get_altitude_color` remains for the radar dots).

## Airline Logos

- New asset directory `logos/airlines/` with hand-crafted 20x20 pixel-art
  PNGs, named by lowercase ICAO prefix (`ual.png`, `aal.png`, ...).
- Initial set (Chicagoland traffic): United, American, Delta, Southwest,
  SkyWest, Republic, Envoy, Spirit, Frontier, JetBlue, Alaska, FedEx, UPS.
- Loaded once at `FlightDisplay.__init__` into `dict[str, Image.Image]`
  keyed by ICAO prefix. Missing/corrupt files are skipped gracefully.
- **Fallback monogram badge:** unknown airlines get a drawn 20x20 rounded
  square in a color deterministically derived from the callsign prefix, with
  the 2-letter IATA code (from `_icao_to_iata_callsign` mapping) or first two
  callsign characters in white.

## Summary View

Same stats, restyled: black background, small plane silhouette motif kept,
headline `5 aircraft` in white, stat lines (closest distance, highest/lowest
altitude) with white labels and cyan values. No gradient header.

## Radar View

Behavior, geometry, and sweep logic untouched. Restyle only:

- Background `(5, 15, 30)` -> pure black.
- Range rings and cardinal labels: dim cyan.
- Sweep stays green phosphor; center crosshair stays green.
- Info bar: callsign/altitude white, destination/distance cyan; counter dim
  gray. Separator line dim cyan.

## Error/Empty Screens

`_display_no_location` and `_display_no_flights`: black background, white
mixed-case message text. No header.

## Verification

- Extend the existing headless render/parity test approach: a script renders
  one frame of each screen (detail page A, detail page B, summary, radar,
  no-flights) with fixture flight data and saves PNGs for pixel review.
- Existing pytest suite must still pass (`pytest tests/ -v`); any tests
  asserting on old layout/colors are updated to the new design.
- Final acceptance is visual, on rendered PNGs first, then on the Pi
  (deploy = git push; nightly timer applies).

## Out of Scope

- No changes to data sources (adsb.lol / local receiver / OpenSky), route
  enrichment, caching, or rotation timing.
- No config/admin-panel changes.
- No new metrics beyond what is already fetched.

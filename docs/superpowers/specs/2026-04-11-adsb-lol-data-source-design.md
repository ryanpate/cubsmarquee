# adsb.lol Data Source with Route Enrichment — Design

**Date:** 2026-04-11
**Status:** Approved for planning

## Goal

Make the Cubs Marquee flight display work on mass-produced units that do not have a local ADS-B receiver. Replace the current PiAware/readsb default with the public `adsb.lol` API and enrich each flight with origin → destination airport codes so the display can show `UAL1740 · ORD → RSW · 35,000 ft · 450 mph`. Keep the existing local-receiver path as a power-user override for units that do have their own antenna (like the project owner's personal Pi).

## Approach

Introduce a pluggable data-source abstraction in `flight_display.py` with two implementations: a new `AdsbLolSource` (default) and `LocalReadsbSource` (renamed from the current `_fetch_from_adsb_receiver` path). The source is picked at startup based on whether the user has filled in the `adsb_receiver_url` config field. Route information is fetched from adsb.lol's `/api/0/routeset` endpoint, cached in a local SQLite file, and attached to each aircraft before rendering.

Mass-produced units get working flight tracking with zero configuration and no hardware to buy. The project owner's personal unit keeps the sub-second local feed by pointing `adsb_receiver_url` at `http://piaware.local/skyaware/data/aircraft.json`.

## Architecture

### Data sources

```
flight_display.py
    ├── source: DataSource                  (chosen at __init__)
    │    ├── AdsbLolSource                  (default, when adsb_receiver_url is empty)
    │    │    ├── fetch_aircraft(lat, lon, range_nm) -> list[Aircraft]
    │    │    └── enrich_routes(aircraft)   (populates origin_iata/dest_iata)
    │    └── LocalReadsbSource              (override, when adsb_receiver_url is set)
    │         └── fetch_aircraft(lat, lon, range_nm) -> list[Aircraft]
    │         (no route enrichment — local readsb has no route info)
    └── route_cache: RouteCache             (SQLite-backed, 24h TTL)
```

Both sources return a `list[Aircraft]` using the same dataclass, so downstream rendering code does not care which source it came from. `AdsbLolSource` calls `route_cache.get()` / `route_cache.put_many()` during enrichment; `LocalReadsbSource` does not touch the cache and leaves route fields as `None`.

### Source selection

Picked once at startup in `FlightDisplay.__init__`:

```python
if not config.get("adsb_receiver_url", "").strip():
    self.source = AdsbLolSource(route_cache)
else:
    self.source = LocalReadsbSource(config["adsb_receiver_url"])
```

The source is not swapped at runtime. If `adsb.lol` goes down during a session, the display shows "no aircraft" until it is back. If the user changes their config, they must restart the scoreboard.

## Components

### `route_cache.py` (new file)

Thin wrapper around `sqlite3` at `/home/pi/flight_routes.db`. Python stdlib only, no new dependencies.

**Public interface:**

- `RouteCache(db_path: str = "/home/pi/flight_routes.db")` — creates the file and schema on first use
- `get(callsign: str) -> Optional[RouteInfo]` — returns the row if fetched within 24 hours, else `None`. Returns rows even if `origin_iata` is `None` (negative cache hit).
- `put_many(rows: list[RouteInfo]) -> None` — upserts a batch of rows. Called once per `/routeset` response.

**`RouteInfo` dataclass:**
```python
@dataclass
class RouteInfo:
    callsign: str
    origin_iata: Optional[str]
    dest_iata: Optional[str]
    airline_code: Optional[str]
    plausible: bool
    fetched_at: int  # unix timestamp
```

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS routes (
    callsign TEXT PRIMARY KEY,
    origin_iata TEXT,
    dest_iata TEXT,
    airline_code TEXT,
    plausible INTEGER NOT NULL DEFAULT 0,
    fetched_at INTEGER NOT NULL
);
```

**Negative caching:** When `/routeset` returns no route for a callsign (private flights, GA aircraft, or implausible matches), `AdsbLolSource` still calls `put_many()` with `origin_iata=None`, `dest_iata=None`, `plausible=False`. `get()` returns those rows, so the cache prevents re-querying the same callsign for 24 hours.

**Errors:** `sqlite3.Error` during `get` is caught and returns `None`. During `put_many` it is caught and logged. The display never crashes on cache errors.

### `adsb_lol_source.py` (new file)

Implements the adsb.lol data path.

**`AdsbLolSource(route_cache: RouteCache, base_url: str = "https://api.adsb.lol")`**

**`fetch_aircraft(lat: float, lon: float, range_nm: int) -> list[Aircraft]`**

- GETs `{base_url}/v2/lat/{lat}/lon/{lon}/dist/{range_nm}` with 5-second timeout
- Parses the `ac` array from the response
- Maps each entry to an `Aircraft` dataclass:

```python
@dataclass
class Aircraft:
    callsign: Optional[str]
    hex: Optional[str]
    lat: float
    lon: float
    alt_baro: Optional[int]
    gs: Optional[float]          # ground speed, knots
    track: Optional[float]       # heading
    type: Optional[str]          # ICAO type code, e.g. "A21N"
    registration: Optional[str]  # tail number
    distance_nm: Optional[float] # dst from adsb.lol
    # Populated by enrich_routes:
    origin_iata: Optional[str] = None
    dest_iata: Optional[str] = None
    airline_code: Optional[str] = None
```

- Strips trailing whitespace from `flight` field to get clean callsign
- Returns empty list on any HTTP error, timeout, or JSON parse failure. Logs the error.

**`enrich_routes(aircraft: list[Aircraft]) -> None`**

- For each aircraft with a non-empty callsign:
  - `cached = route_cache.get(callsign)`
  - If cached: attach `origin_iata`/`dest_iata`/`airline_code` to the aircraft
  - If not cached: add `(callsign, lat, lon)` to `uncached`
- If `uncached` is non-empty:
  - POST to `{base_url}/api/0/routeset` with body `{"planes": [{"callsign": c, "lat": lat, "lng": lng}, ...]}`
  - 10-second timeout
  - Response is a list of route objects; build `RouteInfo` for each (use `_airport_codes_iata` field to extract origin/dest, split on `-`)
  - Call `route_cache.put_many(rows)` with all results (including implausible matches as negative cache entries)
  - Attach route fields to the corresponding `Aircraft` objects
- On any network or parse error: log warning, leave route fields as `None`, do not raise. Display still renders, falling back to aircraft type.

### `local_readsb_source.py` (new file)

Extracts the current `_fetch_from_adsb_receiver()` logic from `flight_display.py` into its own file.

**`LocalReadsbSource(url: str)`**

- `fetch_aircraft(lat, lon, range_nm) -> list[Aircraft]` — GETs the configured URL, parses the `aircraft` array, maps to `Aircraft` dataclass
- No `enrich_routes` method (or a no-op implementation) — local readsb has no route data
- The `lat`/`lon`/`range_nm` params are accepted for interface compatibility but only used for post-filtering (existing behavior — local readsb returns everything in range of the antenna)

### `flight_display.py` (modified)

Changes:

1. Import the new modules: `from route_cache import RouteCache`, `from adsb_lol_source import AdsbLolSource, Aircraft`, `from local_readsb_source import LocalReadsbSource`
2. In `__init__`, after loading config:
   - Create `self.route_cache = RouteCache()`
   - Pick source based on `config.adsb_receiver_url`
3. Replace the body of the current `_fetch_from_adsb_receiver` method with a call to `self.source.fetch_aircraft(...)` and `self.source.enrich_routes(...)` (if the source has that method — `hasattr` check)
4. Update the rendering code that currently shows `callsign · type · alt · speed`. Change the order/content to:
   - If `aircraft.origin_iata` and `aircraft.dest_iata` are both set: show `callsign · ORIG → DEST · alt · speed`
   - Otherwise: show `callsign · type · alt · speed` (current behavior)

The "show route OR type" decision is a single `if` in whichever function formats the text line. Render the arrow as a Unicode `→` character if the font supports it, otherwise the ASCII `->`.

### `wifi_config_server.py` (modified)

Wrap the existing `adsb_receiver_url` text input in a collapsible `<details>` block:

```html
<details>
    <summary>Advanced: Local ADS-B Receiver</summary>
    <div class="form-group">
        <label for="adsb_receiver_url">Local Receiver URL:</label>
        <input type="text" id="adsb_receiver_url"
               placeholder="Leave blank to use adsb.lol (recommended)"
               value="{{ config.adsb_receiver_url }}">
        <small>Only set this if you run your own PiAware or readsb on your network.
               Leave blank to use the free adsb.lol public API.</small>
    </div>
</details>
```

Default config value for new installs: `adsb_receiver_url` is `""` (empty string). Existing installs that already have a URL keep it — the config loader must not overwrite existing non-empty values when applying new defaults.

### `scoreboard_config.py` (modified)

- `ADSB_RECEIVER_URL: str = ""` — empty means "use adsb.lol"
- `ADSB_LOL_BASE_URL: str = "https://api.adsb.lol"` — new constant
- `ROUTE_CACHE_DB_PATH: str = "/home/pi/flight_routes.db"` — new constant
- `ROUTE_CACHE_TTL_HOURS: int = 24` — new constant

## Data Flow

Per refresh cycle (every `FLIGHT_UPDATE_INTERVAL` ≈ 30 seconds):

1. `flight_display.FlightDisplay.update()` calls `self.source.fetch_aircraft(lat, lon, range_nm)`
2. `AdsbLolSource.fetch_aircraft`:
   - GET `https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{range_nm}`
   - Parse `ac` → `list[Aircraft]`
3. `AdsbLolSource.enrich_routes(aircraft)`:
   - For each aircraft with a callsign, check `route_cache.get(callsign)`
   - Collect `uncached_callsigns` (list of tuples with callsign + position)
   - If non-empty, POST to `/api/0/routeset` with all uncached callsigns
   - Parse response, build `RouteInfo` objects (including negative cache rows for implausible/missing results)
   - Call `route_cache.put_many(rows)`
   - Attach `origin_iata`/`dest_iata`/`airline_code` to each `Aircraft` from cache or fresh fetch
4. `flight_display` chooses which aircraft to render (existing "most interesting" logic, unchanged)
5. Rendering function shows route when available, aircraft type as fallback

### First-boot behavior on a fresh unit

Cache is empty. First refresh: every visible callsign (~10-30) triggers one batched `/routeset` POST. After that, most callsigns hit the cache on subsequent refreshes. By the end of the first day, the cache contains most regularly-seen airlines in the local bounding box, and daily traffic to `/routeset` drops to near-zero. Total first-day traffic is typically 100-300 POSTs.

### Error paths

| Failure | Behavior |
|---|---|
| `fetch_aircraft` network error or timeout | Return empty list. Display shows "no aircraft" (existing behavior) |
| `fetch_aircraft` JSON parse error | Return empty list. Log error. |
| `enrich_routes` network error | Log warning. Leave route fields as `None`. Display falls back to aircraft type. |
| `enrich_routes` partial response (some callsigns missing) | Treat missing ones as negative cache hits (`put_many` with `None` origin/dest). |
| SQLite permission / disk full during `get` | Return `None`. Aircraft display without route. |
| SQLite permission / disk full during `put_many` | Log error. No-op. Aircraft still display this cycle; re-query next cycle. |

The main display update path is never blocked by a failed route lookup.

## Testing

Unit tests (all run on Mac without real hardware):

### `tests/test_route_cache.py`

- Temporary SQLite DB fixture (`tmp_path` pytest fixture)
- `get` returns `None` for unknown callsign
- `put_many` followed by `get` returns the inserted row
- `get` returns `None` for a row older than 24 hours
- `put_many` twice with the same callsign upserts (latest fetched_at wins)
- Negative cache: `put_many` with `origin_iata=None` stores and `get` returns it
- Empty `put_many` call is a no-op

### `tests/test_adsb_lol_source.py`

- Mock `requests.get` and `requests.post`
- `fetch_aircraft` parses `{"ac": [...]}` correctly, maps all fields to `Aircraft` dataclass
- `fetch_aircraft` strips trailing whitespace from callsign
- `fetch_aircraft` returns empty list on HTTP 500
- `fetch_aircraft` returns empty list on `requests.Timeout`
- `enrich_routes` only POSTs callsigns that are not in cache
- `enrich_routes` attaches route info from cache hits without POSTing
- `enrich_routes` parses `_airport_codes_iata` response format (`"ORD-RSW"` → `("ORD", "RSW")`)
- `enrich_routes` handles aircraft with no route in response (stores negative cache entry)
- `enrich_routes` does not raise on network error, leaves route fields `None`

### `tests/test_flight_display_source_selection.py`

- Empty `adsb_receiver_url` config → `FlightDisplay.source` is `AdsbLolSource`
- Non-empty `adsb_receiver_url` config → `FlightDisplay.source` is `LocalReadsbSource` with that URL
- (Use `rgbmatrix` mock from existing `conftest.py`)

### Manual hardware verification (project owner's Pi)

1. Set `adsb_receiver_url` to `""` in `/home/pi/config.json`, restart scoreboard
2. Watch `tail -f /home/pi/scoreboard_logs/scoreboard.log` — should see "Using AdsbLolSource", see HTTP requests to `api.adsb.lol`, aircraft appearing on the display
3. Verify `ORIG → DEST` shows on at least one flight after ~1 minute
4. Verify `/home/pi/flight_routes.db` exists: `sqlite3 /home/pi/flight_routes.db "SELECT callsign, origin_iata, dest_iata FROM routes LIMIT 10"` should show rows
5. Set `adsb_receiver_url` back to `http://piaware.local/skyaware/data/aircraft.json`, restart
6. Watch logs — should see "Using LocalReadsbSource", aircraft from PiAware, no calls to adsb.lol, display shows aircraft type again (not routes)

## Out of Scope

- **Airline name enrichment beyond 3-letter ICAO code.** `UAL` stays as `UAL`. Future work could add a static JSON lookup table.
- **Full airport name display** — 96×48 matrix does not have room. Just IATA codes.
- **Historical / playback data** — adsb.lol does not support it.
- **Pre-populated route cache shipped on the SD card image.** Cache warms up naturally within a day.
- **Automatic runtime failover between adsb.lol and local.** Source is chosen at startup and fixed until restart.
- **Rate limiting or backoff.** adsb.lol is free and unmetered. Add if throttling ever becomes an issue.
- **Touching `airplanes.live` hex enrichment** — that path stays as-is in the current code. It is orthogonal to the data source swap.
- **Migrating the AirLabs or OpenSky fallback paths** — those remain as lower-priority fallbacks inside `LocalReadsbSource` if they existed before. `AdsbLolSource` has no fallbacks; if it fails, the display shows no aircraft.

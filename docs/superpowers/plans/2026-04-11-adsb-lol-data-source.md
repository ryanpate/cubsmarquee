# adsb.lol Data Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the flight display work on units that do not have a local ADS-B receiver by switching the default data source to the public adsb.lol API, with route enrichment (origin → destination airports) cached in a local SQLite file. Keep the existing local readsb/PiAware path as a power-user override.

**Architecture:** Add two new pure-function modules (`route_cache.py`, `adsb_lol_source.py`) and modify `flight_display.py` to dispatch between the new adsb.lol path and the existing local-receiver path based on whether `adsb_receiver_url` is set in config. The new path fetches aircraft from `https://api.adsb.lol/v2/lat/.../lon/.../dist/...`, enriches each callsign with route info via `POST /api/0/routeset`, and caches results in `/home/pi/flight_routes.db`. The existing `_fetch_from_adsb_receiver` method stays untouched for backward compatibility.

**Tech Stack:** Python 3.9+, stdlib `sqlite3`, existing `requests` and `Pillow`, pytest for tests. Target: Raspberry Pi OS.

**Reference spec:** `docs/superpowers/specs/2026-04-11-adsb-lol-data-source-design.md`

---

## File Structure

**Created:**
- `route_cache.py` — SQLite-backed cache for `callsign → (origin, dest, airline)` with 24h TTL
- `adsb_lol_source.py` — two pure functions: `fetch_aircraft()` and `enrich_routes()`
- `tests/test_route_cache.py`
- `tests/test_adsb_lol_source.py`

**Modified:**
- `flight_display.py` — add source dispatch in fetch path, add route enrichment call, update rendering to show `ORIG → DEST` when available
- `wifi_config_server.py` — wrap `adsb_receiver_url` input in a collapsible `<details>` block and change its default to empty string
- `scoreboard_config.py` — `ADSB_RECEIVER_URL` default becomes empty string, add `ADSB_LOL_BASE_URL`, `ROUTE_CACHE_DB_PATH`, `ROUTE_CACHE_TTL_HOURS` constants

**Data shape contract:** `fetch_aircraft()` must return a list of dicts with **exactly** the same keys the existing `_fetch_from_adsb_receiver()` method produces, plus three new keys (`origin_iata`, `dest_iata`, `airline_code`). This way the existing rendering/filtering code keeps working unchanged.

Required dict keys (existing):
```python
{
    'callsign': str,
    'altitude_ft': int,
    'velocity_mph': int,
    'distance': float,       # miles from home
    'latitude': float,
    'longitude': float,
    'aircraft_type': str,    # ICAO type code like "A21N"
    'registration': str,
    'vertical_rate': int | None,
    'heading': float | None,
    'icao_hex': str,
    'destination': str,      # kept as "UNKNOWN" — enrichment populates origin_iata/dest_iata instead
}
```

New keys added by `enrich_routes`:
```python
{
    'origin_iata': str | None,
    'dest_iata': str | None,
    'airline_code': str | None,
}
```

---

## Task 1: `scoreboard_config.py` — new constants

**Files:**
- Modify: `scoreboard_config.py`

- [ ] **Step 1: Find the flight tracking settings block**

Run: `grep -n "ADSB_RECEIVER_URL\|FLIGHT_UPDATE_INTERVAL" scoreboard_config.py`
Expected output points to lines ~236-241 in the `GameConfig` class.

- [ ] **Step 2: Change the default and add new constants**

Edit `scoreboard_config.py`. Find:

```python
    # Flight tracking settings
    FLIGHT_UPDATE_INTERVAL: int = 30  # seconds between API updates
    FLIGHT_BOUNDING_BOX_SIZE: float = 0.125  # degrees lat/long around center point (~7-8 mile radius)
    ADSB_RECEIVER_URL: str = 'http://piaware.local/skyaware/data/aircraft.json'
    FLIGHT_MAX_RANGE_NM: int = 50  # nautical miles max range for local receiver
    FLIGHT_REFRESH_INTERVAL: int = 30  # seconds between data refreshes during display
```

Replace with:

```python
    # Flight tracking settings
    FLIGHT_UPDATE_INTERVAL: int = 30  # seconds between API updates
    FLIGHT_BOUNDING_BOX_SIZE: float = 0.125  # degrees lat/long around center point (~7-8 mile radius)
    # Empty ADSB_RECEIVER_URL means "use adsb.lol public API". Set to a local readsb/PiAware URL
    # (e.g. http://piaware.local/skyaware/data/aircraft.json) to use a local receiver instead.
    ADSB_RECEIVER_URL: str = ''
    ADSB_LOL_BASE_URL: str = 'https://api.adsb.lol'
    ROUTE_CACHE_DB_PATH: str = '/home/pi/flight_routes.db'
    ROUTE_CACHE_TTL_HOURS: int = 24
    FLIGHT_MAX_RANGE_NM: int = 50  # nautical miles max range for local receiver
    FLIGHT_REFRESH_INTERVAL: int = 30  # seconds between data refreshes during display
```

- [ ] **Step 3: Verify the change parses**

Run: `cd /Users/ryanpate/cubsmarquee && python3 -c "from scoreboard_config import GameConfig; print(repr(GameConfig.ADSB_RECEIVER_URL), GameConfig.ADSB_LOL_BASE_URL, GameConfig.ROUTE_CACHE_DB_PATH, GameConfig.ROUTE_CACHE_TTL_HOURS)"`
Expected: `''  https://api.adsb.lol  /home/pi/flight_routes.db  24`

- [ ] **Step 4: Commit**

```bash
cd /Users/ryanpate/cubsmarquee
git add scoreboard_config.py
git commit -m "Add adsb.lol config constants and empty default for ADSB_RECEIVER_URL"
```

---

## Task 2: `route_cache.py` — SQLite schema and `put_many`

**Files:**
- Create: `route_cache.py`
- Create: `tests/test_route_cache.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_route_cache.py`:

```python
"""Tests for route_cache module."""
from __future__ import annotations

import time
import pytest

from route_cache import RouteCache, RouteInfo


class TestRouteCacheBasics:
    def test_get_returns_none_for_unknown_callsign(self, tmp_path):
        cache = RouteCache(str(tmp_path / "routes.db"))
        assert cache.get("NOPE1234") is None

    def test_put_many_then_get_returns_row(self, tmp_path):
        cache = RouteCache(str(tmp_path / "routes.db"))
        row = RouteInfo(
            callsign="UAL1740",
            origin_iata="ORD",
            dest_iata="RSW",
            airline_code="UAL",
            plausible=True,
            fetched_at=int(time.time()),
        )
        cache.put_many([row])
        got = cache.get("UAL1740")
        assert got is not None
        assert got.origin_iata == "ORD"
        assert got.dest_iata == "RSW"
        assert got.airline_code == "UAL"
        assert got.plausible is True

    def test_put_many_empty_list_is_noop(self, tmp_path):
        cache = RouteCache(str(tmp_path / "routes.db"))
        cache.put_many([])  # must not raise
        assert cache.get("ANYTHING") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ryanpate/cubsmarquee && pytest tests/test_route_cache.py -v`
Expected: `ModuleNotFoundError: No module named 'route_cache'`

- [ ] **Step 3: Create the module**

Create `/Users/ryanpate/cubsmarquee/route_cache.py`:

```python
"""SQLite-backed cache for flight route info (callsign -> origin/dest/airline)."""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from typing import Optional

from logger import get_logger

logger = get_logger("route_cache")


@dataclass
class RouteInfo:
    callsign: str
    origin_iata: Optional[str]
    dest_iata: Optional[str]
    airline_code: Optional[str]
    plausible: bool
    fetched_at: int  # unix timestamp


_SCHEMA = """
CREATE TABLE IF NOT EXISTS routes (
    callsign TEXT PRIMARY KEY,
    origin_iata TEXT,
    dest_iata TEXT,
    airline_code TEXT,
    plausible INTEGER NOT NULL DEFAULT 0,
    fetched_at INTEGER NOT NULL
);
"""


class RouteCache:
    def __init__(self, db_path: str = "/home/pi/flight_routes.db", ttl_hours: int = 24) -> None:
        self.db_path = db_path
        self.ttl_seconds = ttl_hours * 3600
        try:
            with self._conn() as conn:
                conn.execute(_SCHEMA)
        except sqlite3.Error as e:
            logger.error("Failed to initialize route cache at %s: %s", db_path, e)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    def get(self, callsign: str) -> Optional[RouteInfo]:
        """Return the cached route for a callsign if fetched within TTL, else None."""
        if not callsign:
            return None
        try:
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT callsign, origin_iata, dest_iata, airline_code, plausible, fetched_at "
                    "FROM routes WHERE callsign = ?",
                    (callsign,),
                ).fetchone()
                if row is None:
                    return None
                if int(time.time()) - row["fetched_at"] > self.ttl_seconds:
                    return None
                return RouteInfo(
                    callsign=row["callsign"],
                    origin_iata=row["origin_iata"],
                    dest_iata=row["dest_iata"],
                    airline_code=row["airline_code"],
                    plausible=bool(row["plausible"]),
                    fetched_at=row["fetched_at"],
                )
        except sqlite3.Error as e:
            logger.warning("route cache get failed for %s: %s", callsign, e)
            return None

    def put_many(self, rows: list[RouteInfo]) -> None:
        """Upsert a batch of route rows."""
        if not rows:
            return
        try:
            with self._conn() as conn:
                conn.executemany(
                    "INSERT INTO routes (callsign, origin_iata, dest_iata, airline_code, plausible, fetched_at) "
                    "VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(callsign) DO UPDATE SET "
                    "origin_iata=excluded.origin_iata, "
                    "dest_iata=excluded.dest_iata, "
                    "airline_code=excluded.airline_code, "
                    "plausible=excluded.plausible, "
                    "fetched_at=excluded.fetched_at",
                    [
                        (
                            r.callsign,
                            r.origin_iata,
                            r.dest_iata,
                            r.airline_code,
                            1 if r.plausible else 0,
                            r.fetched_at,
                        )
                        for r in rows
                    ],
                )
        except sqlite3.Error as e:
            logger.warning("route cache put_many failed: %s", e)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/ryanpate/cubsmarquee && pytest tests/test_route_cache.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add route_cache.py tests/test_route_cache.py
git commit -m "Add RouteCache SQLite module with put_many and get"
```

---

## Task 3: `route_cache.py` — TTL expiration and negative caching

**Files:**
- Modify: `tests/test_route_cache.py` (append tests)

The core module already handles these cases — this task just adds test coverage.

- [ ] **Step 1: Append tests**

Append to `tests/test_route_cache.py`:

```python
class TestRouteCacheTTL:
    def test_get_returns_none_for_expired_row(self, tmp_path):
        cache = RouteCache(str(tmp_path / "routes.db"), ttl_hours=1)
        stale_time = int(time.time()) - 3700  # > 1 hour ago
        row = RouteInfo(
            callsign="UAL999",
            origin_iata="ORD",
            dest_iata="LAX",
            airline_code="UAL",
            plausible=True,
            fetched_at=stale_time,
        )
        cache.put_many([row])
        assert cache.get("UAL999") is None

    def test_put_many_upserts_on_duplicate_callsign(self, tmp_path):
        cache = RouteCache(str(tmp_path / "routes.db"))
        now = int(time.time())
        r1 = RouteInfo("UAL1", "ORD", "LAX", "UAL", True, now - 100)
        r2 = RouteInfo("UAL1", "ORD", "SFO", "UAL", True, now)
        cache.put_many([r1])
        cache.put_many([r2])
        got = cache.get("UAL1")
        assert got is not None
        assert got.dest_iata == "SFO"
        assert got.fetched_at == now


class TestRouteCacheNegative:
    def test_negative_cache_stores_none_origin(self, tmp_path):
        cache = RouteCache(str(tmp_path / "routes.db"))
        row = RouteInfo(
            callsign="PRIVATE1",
            origin_iata=None,
            dest_iata=None,
            airline_code=None,
            plausible=False,
            fetched_at=int(time.time()),
        )
        cache.put_many([row])
        got = cache.get("PRIVATE1")
        assert got is not None
        assert got.origin_iata is None
        assert got.dest_iata is None
        assert got.plausible is False
```

- [ ] **Step 2: Run tests**

Run: `cd /Users/ryanpate/cubsmarquee && pytest tests/test_route_cache.py -v`
Expected: 6 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_route_cache.py
git commit -m "Add TTL and negative-cache tests for RouteCache"
```

---

## Task 4: `adsb_lol_source.py` — `fetch_aircraft`

**Files:**
- Create: `adsb_lol_source.py`
- Create: `tests/test_adsb_lol_source.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_adsb_lol_source.py`:

```python
"""Tests for adsb_lol_source module."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from adsb_lol_source import fetch_aircraft


SAMPLE_AC_RESPONSE = {
    "ac": [
        {
            "hex": "a55fa2",
            "flight": "UAL1740 ",
            "r": "N44501",
            "t": "A21N",
            "alt_baro": 35000,
            "gs": 450.0,
            "track": 90.0,
            "lat": 41.968,
            "lon": -87.874,
            "baro_rate": 0,
            "seen": 0.1,
            "dst": 5.0,
        },
        {
            # On the ground - should be filtered
            "hex": "ground1",
            "flight": "GND1 ",
            "alt_baro": "ground",
            "lat": 41.9,
            "lon": -87.9,
            "seen": 0.5,
        },
        {
            # Below min altitude - should be filtered
            "hex": "low1",
            "flight": "LOW1 ",
            "alt_baro": 100,
            "lat": 41.95,
            "lon": -87.9,
            "gs": 100,
            "seen": 0.5,
        },
    ]
}


class TestFetchAircraft:
    def test_parses_ac_array_to_dict_shape(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_AC_RESPONSE
        with patch("adsb_lol_source.requests.get", return_value=mock_resp):
            flights = fetch_aircraft(
                base_url="https://api.adsb.lol",
                home_lat=41.95,
                home_lon=-87.65,
                range_nm=50,
                min_altitude_ft=500,
            )
        assert len(flights) == 1
        f = flights[0]
        assert f["callsign"] == "UAL1740"
        assert f["altitude_ft"] == 35000
        assert f["velocity_mph"] == int(450.0 * 1.15078)
        assert f["aircraft_type"] == "A21N"
        assert f["registration"] == "N44501"
        assert f["icao_hex"] == "a55fa2"
        assert f["heading"] == 90.0
        assert f["vertical_rate"] == 0
        assert f["destination"] == "UNKNOWN"
        assert f["origin_iata"] is None
        assert f["dest_iata"] is None
        assert f["airline_code"] is None

    def test_filters_ground_and_low_altitude(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_AC_RESPONSE
        with patch("adsb_lol_source.requests.get", return_value=mock_resp):
            flights = fetch_aircraft(
                base_url="https://api.adsb.lol",
                home_lat=41.95,
                home_lon=-87.65,
                range_nm=50,
                min_altitude_ft=500,
            )
        callsigns = [f["callsign"] for f in flights]
        assert "GND1" not in callsigns
        assert "LOW1" not in callsigns

    def test_returns_empty_list_on_http_error(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.json.return_value = {}
        with patch("adsb_lol_source.requests.get", return_value=mock_resp):
            flights = fetch_aircraft(
                base_url="https://api.adsb.lol",
                home_lat=41.95,
                home_lon=-87.65,
                range_nm=50,
                min_altitude_ft=500,
            )
        assert flights == []

    def test_returns_empty_list_on_timeout(self):
        import requests
        with patch("adsb_lol_source.requests.get", side_effect=requests.Timeout):
            flights = fetch_aircraft(
                base_url="https://api.adsb.lol",
                home_lat=41.95,
                home_lon=-87.65,
                range_nm=50,
                min_altitude_ft=500,
            )
        assert flights == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/ryanpate/cubsmarquee && pytest tests/test_adsb_lol_source.py -v`
Expected: `ModuleNotFoundError: No module named 'adsb_lol_source'`

- [ ] **Step 3: Create `adsb_lol_source.py` with `fetch_aircraft`**

Create `/Users/ryanpate/cubsmarquee/adsb_lol_source.py`:

```python
"""adsb.lol data source: fetches aircraft and enriches with route info."""
from __future__ import annotations

import math
from typing import Any, Optional

import requests

from logger import get_logger

logger = get_logger("adsb_lol_source")

FETCH_TIMEOUT_SEC = 5
ROUTESET_TIMEOUT_SEC = 10
KNOTS_TO_MPH = 1.15078


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in statute miles."""
    r_miles = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r_miles * c


def fetch_aircraft(
    base_url: str,
    home_lat: float,
    home_lon: float,
    range_nm: int,
    min_altitude_ft: int,
) -> list[dict[str, Any]]:
    """Fetch aircraft from adsb.lol and return a list of flight dicts.

    Returns dicts with the same shape flight_display._fetch_from_adsb_receiver produces,
    plus three new keys: origin_iata, dest_iata, airline_code (all initially None).
    Returns an empty list on any error.
    """
    url = f"{base_url}/v2/lat/{home_lat}/lon/{home_lon}/dist/{range_nm}"
    try:
        response = requests.get(url, timeout=FETCH_TIMEOUT_SEC)
        if response.status_code != 200:
            logger.warning("adsb.lol returned HTTP %s", response.status_code)
            return []
        data = response.json()
    except requests.Timeout:
        logger.warning("adsb.lol fetch timed out")
        return []
    except requests.RequestException as e:
        logger.warning("adsb.lol fetch failed: %s", e)
        return []
    except ValueError as e:
        logger.warning("adsb.lol returned invalid JSON: %s", e)
        return []

    aircraft_list = data.get("ac", []) or []
    max_range_mi = range_nm * KNOTS_TO_MPH
    flights: list[dict[str, Any]] = []

    for ac in aircraft_list:
        lat = ac.get("lat")
        lon = ac.get("lon")
        alt_baro = ac.get("alt_baro")

        if lat is None or lon is None:
            continue
        if alt_baro == "ground" or alt_baro is None:
            continue
        if isinstance(alt_baro, str):
            continue
        altitude_ft = int(alt_baro)
        if altitude_ft < min_altitude_ft:
            continue

        seen = ac.get("seen", 999)
        if seen > 60:
            continue

        distance = _haversine_miles(home_lat, home_lon, lat, lon)
        if distance > max_range_mi:
            continue

        callsign = (ac.get("flight") or "").strip()
        gs_knots = ac.get("gs")
        velocity_mph = int(gs_knots * KNOTS_TO_MPH) if gs_knots else 0

        flights.append(
            {
                "callsign": callsign or ac.get("r", "") or ac.get("hex", "").upper(),
                "altitude_ft": altitude_ft,
                "velocity_mph": velocity_mph,
                "distance": distance,
                "latitude": lat,
                "longitude": lon,
                "aircraft_type": ac.get("t", ""),
                "registration": ac.get("r", ""),
                "vertical_rate": ac.get("baro_rate"),
                "heading": ac.get("track"),
                "icao_hex": ac.get("hex", ""),
                "destination": "UNKNOWN",
                "origin_iata": None,
                "dest_iata": None,
                "airline_code": None,
            }
        )

    flights.sort(key=lambda x: x["distance"])
    return flights[:15]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/ryanpate/cubsmarquee && pytest tests/test_adsb_lol_source.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add adsb_lol_source.py tests/test_adsb_lol_source.py
git commit -m "Add adsb_lol_source.fetch_aircraft with filtering"
```

---

## Task 5: `adsb_lol_source.py` — `enrich_routes`

**Files:**
- Modify: `adsb_lol_source.py` (append function)
- Modify: `tests/test_adsb_lol_source.py` (append tests)

- [ ] **Step 1: Append failing tests**

Append to `tests/test_adsb_lol_source.py`:

```python
class TestEnrichRoutes:
    def _make_flight(self, callsign, lat=41.9, lon=-87.6):
        return {
            "callsign": callsign,
            "altitude_ft": 35000,
            "velocity_mph": 500,
            "distance": 10.0,
            "latitude": lat,
            "longitude": lon,
            "aircraft_type": "A21N",
            "registration": "N1",
            "vertical_rate": 0,
            "heading": 90.0,
            "icao_hex": "abc123",
            "destination": "UNKNOWN",
            "origin_iata": None,
            "dest_iata": None,
            "airline_code": None,
        }

    def test_enrich_uses_cache_and_posts_only_uncached(self):
        from adsb_lol_source import enrich_routes
        from route_cache import RouteInfo
        import time as _t

        mock_cache = MagicMock()

        def fake_get(cs):
            if cs == "UAL1":
                return RouteInfo("UAL1", "ORD", "LAX", "UAL", True, int(_t.time()))
            return None

        mock_cache.get.side_effect = fake_get

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = [
            {
                "callsign": "UAL2",
                "airline_code": "UAL",
                "number": "2",
                "_airport_codes_iata": "DEN-SEA",
                "plausible": True,
            }
        ]

        flights = [self._make_flight("UAL1"), self._make_flight("UAL2")]

        with patch("adsb_lol_source.requests.post", return_value=mock_post_resp) as mock_post:
            enrich_routes("https://api.adsb.lol", flights, mock_cache)

        # UAL1 attached from cache, no POST needed for it
        assert flights[0]["origin_iata"] == "ORD"
        assert flights[0]["dest_iata"] == "LAX"
        # UAL2 enriched from POST response
        assert flights[1]["origin_iata"] == "DEN"
        assert flights[1]["dest_iata"] == "SEA"
        # POST called once, with only UAL2 in the body
        assert mock_post.call_count == 1
        body = mock_post.call_args.kwargs.get("json") or mock_post.call_args.args[1]
        planes = body["planes"] if isinstance(body, dict) else body
        # accept either positional or keyword json
        if "planes" not in (body if isinstance(body, dict) else {}):
            body = mock_post.call_args.kwargs["json"]
        assert len(body["planes"]) == 1
        assert body["planes"][0]["callsign"] == "UAL2"

    def test_enrich_stores_negative_cache_for_missing_routes(self):
        from adsb_lol_source import enrich_routes

        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        # POST returns empty list — no routes found
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = []

        flights = [self._make_flight("UAL3")]

        with patch("adsb_lol_source.requests.post", return_value=mock_post_resp):
            enrich_routes("https://api.adsb.lol", flights, mock_cache)

        # Route fields remain None
        assert flights[0]["origin_iata"] is None
        assert flights[0]["dest_iata"] is None
        # Negative cache was written
        mock_cache.put_many.assert_called_once()
        rows = mock_cache.put_many.call_args.args[0]
        assert len(rows) == 1
        assert rows[0].callsign == "UAL3"
        assert rows[0].origin_iata is None
        assert rows[0].plausible is False

    def test_enrich_on_network_error_leaves_fields_none(self):
        from adsb_lol_source import enrich_routes

        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        flights = [self._make_flight("UAL4")]

        with patch("adsb_lol_source.requests.post", side_effect=requests.RequestException("boom")):
            enrich_routes("https://api.adsb.lol", flights, mock_cache)

        assert flights[0]["origin_iata"] is None
        assert flights[0]["dest_iata"] is None

    def test_enrich_skips_flights_with_empty_callsign(self):
        from adsb_lol_source import enrich_routes

        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = []

        flights = [self._make_flight("")]

        with patch("adsb_lol_source.requests.post", return_value=mock_post_resp) as mock_post:
            enrich_routes("https://api.adsb.lol", flights, mock_cache)

        # No POST — nothing to enrich
        assert mock_post.call_count == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/ryanpate/cubsmarquee && pytest tests/test_adsb_lol_source.py::TestEnrichRoutes -v`
Expected: `ImportError: cannot import name 'enrich_routes' from 'adsb_lol_source'`

- [ ] **Step 3: Append `enrich_routes` to `adsb_lol_source.py`**

Append to `adsb_lol_source.py`:

```python
import time as _time

from route_cache import RouteCache, RouteInfo


def _parse_iata_pair(airport_codes_iata: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Split 'ORD-RSW' into ('ORD', 'RSW'). Return (None, None) if invalid."""
    if not airport_codes_iata or "-" not in airport_codes_iata:
        return (None, None)
    parts = airport_codes_iata.split("-", 1)
    if len(parts) != 2:
        return (None, None)
    origin = parts[0].strip() or None
    dest = parts[1].strip() or None
    return (origin, dest)


def enrich_routes(
    base_url: str,
    flights: list[dict[str, Any]],
    cache: RouteCache,
) -> None:
    """Populate origin_iata, dest_iata, airline_code on each flight dict.

    Checks the cache first; only POSTs callsigns that are not cached. Negative
    results (no route found) are stored in the cache to avoid re-querying.
    Errors are logged and silently skipped — the display is never blocked.
    """
    if not flights:
        return

    uncached: list[dict[str, Any]] = []

    for f in flights:
        callsign = (f.get("callsign") or "").strip()
        if not callsign:
            continue
        cached = cache.get(callsign)
        if cached is not None:
            f["origin_iata"] = cached.origin_iata
            f["dest_iata"] = cached.dest_iata
            f["airline_code"] = cached.airline_code
        else:
            uncached.append(f)

    if not uncached:
        return

    payload = {
        "planes": [
            {
                "callsign": (f["callsign"] or "").strip(),
                "lat": f["latitude"],
                "lng": f["longitude"],
            }
            for f in uncached
        ]
    }

    try:
        response = requests.post(
            f"{base_url}/api/0/routeset",
            json=payload,
            timeout=ROUTESET_TIMEOUT_SEC,
        )
        if response.status_code != 200:
            logger.warning("routeset returned HTTP %s", response.status_code)
            return
        results = response.json()
    except requests.Timeout:
        logger.warning("routeset request timed out")
        return
    except requests.RequestException as e:
        logger.warning("routeset request failed: %s", e)
        return
    except ValueError as e:
        logger.warning("routeset returned invalid JSON: %s", e)
        return

    now = int(_time.time())
    by_callsign: dict[str, dict[str, Any]] = {}
    for item in results or []:
        cs = (item.get("callsign") or "").strip()
        if cs:
            by_callsign[cs] = item

    rows_to_cache: list[RouteInfo] = []
    for f in uncached:
        cs = (f["callsign"] or "").strip()
        item = by_callsign.get(cs)
        if item and item.get("plausible"):
            origin, dest = _parse_iata_pair(item.get("_airport_codes_iata"))
            airline = item.get("airline_code")
            f["origin_iata"] = origin
            f["dest_iata"] = dest
            f["airline_code"] = airline
            rows_to_cache.append(
                RouteInfo(
                    callsign=cs,
                    origin_iata=origin,
                    dest_iata=dest,
                    airline_code=airline,
                    plausible=True,
                    fetched_at=now,
                )
            )
        else:
            # Negative cache entry
            rows_to_cache.append(
                RouteInfo(
                    callsign=cs,
                    origin_iata=None,
                    dest_iata=None,
                    airline_code=None,
                    plausible=False,
                    fetched_at=now,
                )
            )

    cache.put_many(rows_to_cache)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/ryanpate/cubsmarquee && pytest tests/test_adsb_lol_source.py -v`
Expected: 8 passed (4 from Task 4 + 4 new).

If the `test_enrich_uses_cache_and_posts_only_uncached` test body-extraction assertion fails, simplify it — the check that matters is `mock_post.call_count == 1` and the content of `mock_post.call_args.kwargs["json"]["planes"]`. Fix the test to use `body = mock_post.call_args.kwargs["json"]` directly, without the positional fallback.

- [ ] **Step 5: Commit**

```bash
git add adsb_lol_source.py tests/test_adsb_lol_source.py
git commit -m "Add enrich_routes with cache-aware batching and negative caching"
```

---

## Task 6: Wire into `flight_display.py` — source dispatch

**Files:**
- Modify: `flight_display.py`

- [ ] **Step 1: Find the relevant locations**

Run: `grep -n "_fetch_from_adsb_receiver\|self.adsb_receiver_url\|def update\|def _fetch\|self.flight_data" flight_display.py | head -20`

Note the line numbers for:
- `self.adsb_receiver_url` assignment in `__init__` (around line 51)
- The method that calls `_fetch_from_adsb_receiver` (look for the dispatcher/update method)
- The `_lookup_destinations` call site inside `_fetch_from_adsb_receiver`

- [ ] **Step 2: Add imports at the top of `flight_display.py`**

Find the existing imports block (near the top of the file, after `from __future__ import annotations`). Add these imports with the other project-local imports:

```python
from adsb_lol_source import fetch_aircraft as adsb_lol_fetch_aircraft
from adsb_lol_source import enrich_routes as adsb_lol_enrich_routes
from route_cache import RouteCache
```

- [ ] **Step 3: Initialize the source selector and cache in `__init__`**

Find this line in `FlightDisplay.__init__`:

```python
        self.adsb_receiver_url: str = GameConfig.ADSB_RECEIVER_URL
```

Immediately after it (still in `__init__`), add:

```python
        self.route_cache: RouteCache = RouteCache(
            db_path=GameConfig.ROUTE_CACHE_DB_PATH,
            ttl_hours=GameConfig.ROUTE_CACHE_TTL_HOURS,
        )
```

Then, after `self._load_config()` is called (which may overwrite `self.adsb_receiver_url` from `/home/pi/config.json`), add this line:

```python
        self.use_adsb_lol: bool = not (self.adsb_receiver_url or "").strip()
        logger.info(
            "Flight data source: %s",
            "adsb.lol" if self.use_adsb_lol else f"local ({self.adsb_receiver_url})",
        )
```

If `flight_display.py` does not already import a logger, find the existing `print(...)` calls in the file and use `print` instead:

```python
        self.use_adsb_lol: bool = not (self.adsb_receiver_url or "").strip()
        print(
            f"Flight data source: "
            f"{'adsb.lol' if self.use_adsb_lol else f'local ({self.adsb_receiver_url})'}"
        )
```

- [ ] **Step 4: Add a new fetch method for the adsb.lol path**

Find the existing `_fetch_from_adsb_receiver` method (around line 469). Immediately before it, add a new method:

```python
    def _fetch_from_adsb_lol(self) -> bool:
        """Fetch flight data from adsb.lol. Returns True on success."""
        if not self.latitude or not self.longitude:
            return False

        flights = adsb_lol_fetch_aircraft(
            base_url=GameConfig.ADSB_LOL_BASE_URL,
            home_lat=self.latitude,
            home_lon=self.longitude,
            range_nm=self.flight_max_range_nm,
            min_altitude_ft=self.MIN_ALTITUDE_FT,
        )

        if not flights:
            return False

        adsb_lol_enrich_routes(
            base_url=GameConfig.ADSB_LOL_BASE_URL,
            flights=flights,
            cache=self.route_cache,
        )

        self.flight_data = flights
        print(f"adsb.lol: {len(self.flight_data)} flights found")
        return True
```

- [ ] **Step 5: Update the dispatcher**

Find the method that calls `self._fetch_from_adsb_receiver()`. It is likely named `fetch_flights` or similar, and lives around line 700 based on earlier grep output. Replace the existing call:

```python
        if self._fetch_from_adsb_receiver():
```

with:

```python
        fetch_ok = (
            self._fetch_from_adsb_lol()
            if self.use_adsb_lol
            else self._fetch_from_adsb_receiver()
        )
        if fetch_ok:
```

- [ ] **Step 6: Verify syntax**

Run: `cd /Users/ryanpate/cubsmarquee && python3 -m py_compile flight_display.py`
Expected: no output (syntax clean). A `ModuleNotFoundError: rgbmatrix` is NOT expected here — `py_compile` does not execute imports.

- [ ] **Step 7: Run full test suite**

Run: `cd /Users/ryanpate/cubsmarquee && pytest tests/ -v`
Expected: all tests pass (including the new `test_route_cache` and `test_adsb_lol_source` suites, plus existing tests). No regressions.

- [ ] **Step 8: Commit**

```bash
git add flight_display.py
git commit -m "Dispatch flight data fetch between adsb.lol and local readsb"
```

---

## Task 7: Update rendering to show `ORIG → DEST`

**Files:**
- Modify: `flight_display.py`

Find the code that renders the flight info line. Search for where `aircraft_type` is used in a drawing call.

- [ ] **Step 1: Find the render location**

Run: `grep -n "aircraft_type\|draw.text\|flight\['" flight_display.py | head -30`

Look for lines where the text being drawn includes `aircraft_type` or the callsign alongside it. Note the line number.

- [ ] **Step 2: Find the helper or inline location that composes the info text**

The existing rendering likely composes a string like `f"{callsign} {aircraft_type} {altitude_ft}"` or draws each token separately. If it's a single composed string, add a helper. If tokens are drawn individually, add a conditional before the aircraft_type draw.

Look for the pattern of the existing code. In the most common case you will find either (a) a `f"{callsign} {aircraft_type}..."` f-string or (b) separate `draw.text` calls per token.

- [ ] **Step 3: Add a helper near the top of the class**

Inside the `FlightDisplay` class, near other small helpers (such as `_create_flight_header_background`), add:

```python
    def _format_type_or_route(self, flight: dict[str, Any]) -> str:
        """Return 'ORIG -> DEST' if route is known, otherwise the ICAO aircraft type."""
        origin = flight.get("origin_iata")
        dest = flight.get("dest_iata")
        if origin and dest:
            return f"{origin}->{dest}"
        return flight.get("aircraft_type", "") or ""
```

We use `->` instead of `→` because bitmap fonts used on the LED matrix may not render the Unicode arrow. The existing fonts in the project are BDF bitmap fonts; stick with ASCII.

- [ ] **Step 4: Replace the `aircraft_type` usage**

Find every place in the rendering code where `flight["aircraft_type"]`, `flight.get("aircraft_type")`, or a local variable referring to the aircraft type is drawn. For each one, replace it with a call to `self._format_type_or_route(flight)`.

Example (the exact code will differ):

Before:
```python
ac_type = flight.get("aircraft_type", "")
draw.text((x, y), ac_type, font=font, fill=color)
```

After:
```python
ac_label = self._format_type_or_route(flight)
draw.text((x, y), ac_label, font=font, fill=color)
```

If there is only one place, make just one edit. If there are multiple (e.g., compact and detailed views), update each.

- [ ] **Step 5: Verify syntax**

Run: `cd /Users/ryanpate/cubsmarquee && python3 -m py_compile flight_display.py`
Expected: no output.

- [ ] **Step 6: Run tests**

Run: `cd /Users/ryanpate/cubsmarquee && pytest tests/ -v`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add flight_display.py
git commit -m "Show ORIG->DEST on flight display when route is known"
```

---

## Task 8: `wifi_config_server.py` — collapsible "Advanced" block

**Files:**
- Modify: `wifi_config_server.py`

- [ ] **Step 1: Change the default config value**

Find this line (around line 145):

```python
        'adsb_receiver_url': 'http://adsbexchange.local/tar1090/data/aircraft.json',
```

Replace with:

```python
        'adsb_receiver_url': '',
```

- [ ] **Step 2: Change the default in the save handler**

Find this line (around line 1562):

```python
            'adsb_receiver_url': data.get('adsb_receiver_url', 'http://adsbexchange.local/tar1090/data/aircraft.json'),
```

Replace with:

```python
            'adsb_receiver_url': data.get('adsb_receiver_url', ''),
```

- [ ] **Step 3: Update the JS restore line**

Find this line (around line 881):

```python
            document.getElementById('adsb_receiver_url').value = config.adsb_receiver_url || 'http://adsbexchange.local/tar1090/data/aircraft.json';
```

Replace with:

```python
            document.getElementById('adsb_receiver_url').value = config.adsb_receiver_url || '';
```

- [ ] **Step 4: Wrap the input in a collapsible details block**

Find the existing form group (around line 744):

```python
            <div class="form-group">
                <label for="adsb_receiver_url">ADS-B Receiver URL:</label>
                <input type="text" id="adsb_receiver_url" placeholder="http://adsbexchange.local/tar1090/data/aircraft.json" value="{{ config.adsb_receiver_url }}">
            </div>
```

Replace with:

```python
            <details style="margin-top: 15px; padding: 10px; background: #f5f5f5; border-radius: 5px;">
                <summary style="cursor: pointer; font-weight: bold; color: #0C2340;">Advanced: Local ADS-B Receiver</summary>
                <div class="form-group" style="margin-top: 10px;">
                    <label for="adsb_receiver_url">Local Receiver URL:</label>
                    <input type="text" id="adsb_receiver_url"
                           placeholder="Leave blank to use adsb.lol (recommended)"
                           value="{{ config.adsb_receiver_url }}">
                    <small style="display: block; margin-top: 5px; color: #666;">
                        Leave blank to use the free adsb.lol public API (recommended).
                        Only set this if you run your own PiAware or readsb receiver on your network.
                        Example: <code>http://piaware.local/skyaware/data/aircraft.json</code>
                    </small>
                </div>
            </details>
```

- [ ] **Step 5: Smoke-test**

Run: `cd /Users/ryanpate/cubsmarquee && python3 -c "import wifi_config_server; print('ok')"`
Expected: `ok` (no syntax error). A Flask deprecation warning is acceptable.

- [ ] **Step 6: Commit**

```bash
git add wifi_config_server.py
git commit -m "Wrap local ADS-B URL in Advanced collapsible, default to empty"
```

---

## Task 9: Manual hardware verification

**Files:** none

This cannot be automated — it requires the real Pi.

- [ ] **Step 1: Deploy files to the Pi**

```bash
cd /Users/ryanpate/cubsmarquee
sshpass -p raspberry scp \
  route_cache.py adsb_lol_source.py flight_display.py \
  scoreboard_config.py wifi_config_server.py \
  pi@192.168.4.244:/home/pi/
```

- [ ] **Step 2: Test the adsb.lol path first**

Blank the `adsb_receiver_url` in the Pi's config:

```bash
sshpass -p raspberry ssh pi@192.168.4.244 \
  "sudo python3 -c \"import json; p='/home/pi/config.json'; c=json.load(open(p)); c['adsb_receiver_url']=''; json.dump(c, open(p,'w'), indent=2); print('cleared')\""
```

Restart the scoreboard:

```bash
sshpass -p raspberry ssh pi@192.168.4.244 "sudo systemctl restart cubs-scoreboard"
```

- [ ] **Step 3: Watch the logs and display**

```bash
sshpass -p raspberry ssh pi@192.168.4.244 "tail -f /home/pi/scoreboard_logs/scoreboard.log"
```

Expected within 60 seconds:
- Log line: `Flight data source: adsb.lol`
- Log line: `adsb.lol: N flights found` with N > 0 (assuming flights are in range)
- Display eventually shows a flight with `ORIG->DEST` format (after the cache warms up for the callsign, or immediately if routeset returns on the first fetch)

Ctrl+C to exit `tail`.

- [ ] **Step 4: Verify the cache file was created**

```bash
sshpass -p raspberry ssh pi@192.168.4.244 \
  "sqlite3 /home/pi/flight_routes.db 'SELECT callsign, origin_iata, dest_iata FROM routes LIMIT 10'"
```

Expected: several rows showing callsigns and their origin/dest codes. If the file does not exist yet, wait another refresh cycle and try again.

- [ ] **Step 5: Test the local path still works**

Restore the local receiver URL:

```bash
sshpass -p raspberry ssh pi@192.168.4.244 \
  "sudo python3 -c \"import json; p='/home/pi/config.json'; c=json.load(open(p)); c['adsb_receiver_url']='http://piaware.local/skyaware/data/aircraft.json'; json.dump(c, open(p,'w'), indent=2); print('restored')\""
sshpass -p raspberry ssh pi@192.168.4.244 "sudo systemctl restart cubs-scoreboard"
```

- [ ] **Step 6: Watch logs again**

```bash
sshpass -p raspberry ssh pi@192.168.4.244 "tail -f /home/pi/scoreboard_logs/scoreboard.log"
```

Expected:
- Log line: `Flight data source: local (http://piaware.local/skyaware/data/aircraft.json)`
- Log line: `ADS-B receiver: N flights found` (existing format from `_fetch_from_adsb_receiver`)
- No `adsb.lol` log lines
- Display shows aircraft type again (not `ORIG->DEST`) on the local-receiver path, since `enrich_routes` is not called

Ctrl+C to exit.

- [ ] **Step 7: Verify admin page collapsible**

Visit `http://cubsmarquee.local/admin` from a phone or laptop on the same network. Scroll to the Flight Tracking section. Confirm:
- The ADS-B Receiver URL field is **hidden inside a collapsed "Advanced: Local ADS-B Receiver" block**
- Clicking the block expands it and shows the current URL
- Helper text explains when to set it and when to leave blank

- [ ] **Step 8: Document any deviations**

If anything failed, note the symptom and fix before marking the task complete. Common issues:
- `sqlite3 permission denied` writing to `/home/pi/flight_routes.db` → the `cubs-scoreboard` service may run as a different user. Adjust ownership or pick a writable location.
- `adsb.lol fetch timed out` → usually transient; verify by running `curl -s https://api.adsb.lol/v2/lat/41.95/lon/-87.65/dist/50` from the Pi.
- Display shows aircraft type not route → cache may not be populating. Check `sqlite3 /home/pi/flight_routes.db 'SELECT count(*) FROM routes'`.

---

## Self-Review Notes

**Spec coverage:**
- `route_cache.py` module with schema, `get`, `put_many`, TTL, negative cache → Tasks 2, 3
- `adsb_lol_source.py` `fetch_aircraft` with field mapping, filtering, error handling → Task 4
- `adsb_lol_source.py` `enrich_routes` with cache-aware batching, negative caching, error handling → Task 5
- Source selection at startup based on `adsb_receiver_url` → Task 6
- Rendering fallback (show route when available, type otherwise) → Task 7
- Admin page collapsible `<details>` and empty default → Task 8
- `scoreboard_config.py` constants → Task 1
- Manual hardware verification → Task 9

**Placeholder scan:** No TBDs. Each code step shows the complete code. Task 7's rendering-replace step is the one step with slight flexibility — the exact location in `flight_display.py` depends on the existing rendering shape, so the task tells the implementer to grep for `aircraft_type` usages and replace each with the new helper. This is unavoidable without reading the whole file inline, but the replacement pattern is fully spelled out.

**Type consistency:** `RouteInfo` has the same field list in Tasks 2, 3, and 5. `fetch_aircraft` returns the same dict shape in Task 4 that `enrich_routes` expects in Task 5. The `use_adsb_lol` flag name is consistent in Task 6. `_format_type_or_route` is defined once in Task 7.

**Known footguns called out:**
- Task 6 Step 3: fallback to `print` if `logger` is not already imported in `flight_display.py`.
- Task 5 Step 4: note that the body-extraction assertion in one test may need simplification (positional vs keyword).
- Task 9 Step 8: sqlite permission issue if `cubs-scoreboard` runs as non-pi user.

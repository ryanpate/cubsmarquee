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
        # One malformed record must not abort the whole fetch
        try:
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
        except Exception as e:
            logger.warning("Skipping malformed aircraft record: %s", e)
            continue

    flights.sort(key=lambda x: x["distance"])
    return flights[:15]


import time as _time

from route_cache import RouteCache, RouteInfo


def _parse_iata_pair(airport_codes_iata: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Parse an adsb.lol route string into (origin, destination).

    Handles simple two-leg routes ('ORD-RSW') and multi-leg routes like
    round trips ('ORD-LIT-ORD') or sequential stops ('ATL-MSP-ORD') by
    treating the first segment as the current leg: origin = first code,
    destination = second code. For a round trip A-B-A, this gives A -> B,
    which is the useful non-home destination.
    """
    if not airport_codes_iata or "-" not in airport_codes_iata:
        return (None, None)
    parts = [p.strip() for p in airport_codes_iata.split("-") if p.strip()]
    if len(parts) < 2:
        return (None, None)
    return (parts[0] or None, parts[1] or None)


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
        # adsb.lol answers this POST with 201, so accept any 2xx
        if not 200 <= response.status_code < 300:
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

    if not isinstance(results, list):
        logger.warning(
            "routeset returned unexpected payload type: %s",
            type(results).__name__,
        )
        return

    now = int(_time.time())
    by_callsign: dict[str, dict[str, Any]] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
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

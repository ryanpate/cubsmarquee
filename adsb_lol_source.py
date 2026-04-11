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

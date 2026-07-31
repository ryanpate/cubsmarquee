"""Persistent IATA -> city map, learned from routeset airport data.

The routeset API's `_airports` entries carry each airport's city
("location"), so every successful route lookup teaches us codes the
static AIRPORT_CITIES dict doesn't know (BMI, ICT, ...). Learned pairs
are merged into a small JSON file that survives restarts.
"""

from __future__ import annotations

import json
import os

from logger import get_logger

logger = get_logger("airport_cities")

CACHE_FILE = '/var/tmp/airport_cities.json'
CACHE_FILE_ALT = './airport_cities.json'


def _cache_path() -> str:
    if os.access(os.path.dirname(CACHE_FILE), os.W_OK):
        return CACHE_FILE
    return CACHE_FILE_ALT


def load_learned(path: str | None = None) -> dict[str, str]:
    """The learned IATA -> city map; empty on any problem"""
    path = path or _cache_path()
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(k).upper(): str(v) for k, v in data.items()
                    if k and v}
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("airport city cache unreadable (%s): %s", path, e)
    return {}


def learn(mapping: dict[str, str], path: str | None = None) -> None:
    """Merge new IATA -> city pairs into the persistent map"""
    if not mapping:
        return
    path = path or _cache_path()
    current = load_learned(path)
    merged = {**current,
              **{str(k).upper(): str(v) for k, v in mapping.items()
                 if k and v}}
    if merged == current:
        return
    try:
        with open(path, 'w') as f:
            json.dump(merged, f)
    except OSError as e:
        logger.warning("could not write airport city cache (%s): %s", path, e)

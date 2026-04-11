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

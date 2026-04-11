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

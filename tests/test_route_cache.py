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

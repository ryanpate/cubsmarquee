"""Flight source fallback chain.

A dead local ADS-B receiver must degrade to adsb.lol before OpenSky. OpenSky's
anonymous feed returns almost nothing, so falling straight to it leaves the
display empty even though a working remote source is already wired up.
"""

from __future__ import annotations

from unittest.mock import Mock


def _display(*, use_adsb_lol: bool):
    from flight_display import FlightDisplay

    d = FlightDisplay.__new__(FlightDisplay)
    d.latitude = 39.74949
    d.longitude = -89.53176
    d.use_adsb_lol = use_adsb_lol
    d.flight_data = []
    d.route_cache = {}
    d.learned_cities = {}
    d.last_fetch_time = 0.0
    return d


class TestLocalReceiverFallback:
    def test_dead_receiver_falls_back_to_adsb_lol_not_opensky(self) -> None:
        d = _display(use_adsb_lol=False)
        d._fetch_from_adsb_receiver = Mock(return_value=False)
        d._fetch_from_adsb_lol = Mock(return_value=True)
        d._fetch_from_opensky = Mock(return_value=True)

        assert d._fetch_flight_data() is True
        d._fetch_from_adsb_lol.assert_called_once()
        d._fetch_from_opensky.assert_not_called()

    def test_opensky_is_last_resort_when_both_adsb_sources_fail(self) -> None:
        d = _display(use_adsb_lol=False)
        d._fetch_from_adsb_receiver = Mock(return_value=False)
        d._fetch_from_adsb_lol = Mock(return_value=False)
        d._fetch_from_opensky = Mock(return_value=True)

        assert d._fetch_flight_data() is True
        d._fetch_from_opensky.assert_called_once()

    def test_all_sources_failing_returns_false(self) -> None:
        d = _display(use_adsb_lol=False)
        d._fetch_from_adsb_receiver = Mock(return_value=False)
        d._fetch_from_adsb_lol = Mock(return_value=False)
        d._fetch_from_opensky = Mock(return_value=False)

        assert d._fetch_flight_data() is False


class TestAdsbLolPrimaryUnchanged:
    def test_adsb_lol_primary_does_not_retry_itself_before_opensky(self) -> None:
        d = _display(use_adsb_lol=True)
        d._fetch_from_adsb_receiver = Mock(return_value=True)
        d._fetch_from_adsb_lol = Mock(return_value=False)
        d._fetch_from_opensky = Mock(return_value=True)

        assert d._fetch_flight_data() is True
        d._fetch_from_adsb_lol.assert_called_once()
        d._fetch_from_adsb_receiver.assert_not_called()
        d._fetch_from_opensky.assert_called_once()

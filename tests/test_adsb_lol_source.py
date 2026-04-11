"""Tests for adsb_lol_source module."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

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
            "hex": "ground1",
            "flight": "GND1 ",
            "alt_baro": "ground",
            "lat": 41.9,
            "lon": -87.9,
            "seen": 0.5,
        },
        {
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
        with patch("adsb_lol_source.requests.get", side_effect=requests.Timeout):
            flights = fetch_aircraft(
                base_url="https://api.adsb.lol",
                home_lat=41.95,
                home_lon=-87.65,
                range_nm=50,
                min_altitude_ft=500,
            )
        assert flights == []

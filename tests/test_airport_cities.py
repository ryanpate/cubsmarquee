"""Learned IATA -> city map from routeset airport data"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestAirportCitiesStore:
    def test_learn_and_load_roundtrip(self, tmp_path):
        import airport_cities

        p = str(tmp_path / 'cities.json')
        airport_cities.learn({'ict': 'Wichita'}, path=p)
        airport_cities.learn({'BMI': 'Bloomington'}, path=p)

        assert airport_cities.load_learned(path=p) == {
            'ICT': 'Wichita', 'BMI': 'Bloomington'}

    def test_load_missing_file_returns_empty(self, tmp_path):
        import airport_cities

        assert airport_cities.load_learned(path=str(tmp_path / 'x.json')) == {}

    def test_load_corrupt_file_returns_empty(self, tmp_path):
        import airport_cities

        p = tmp_path / 'bad.json'
        p.write_text('not json')

        assert airport_cities.load_learned(path=str(p)) == {}


class TestDisplayUsesLearnedCities:
    def test_get_airport_city_falls_back_to_learned_map(self):
        from flight_display import FlightDisplay

        d = FlightDisplay.__new__(FlightDisplay)
        d.learned_cities = {'ICT': 'Wichita'}

        assert d._get_airport_city('ICT') == 'Wichita'
        assert d._get_airport_city('KICT') == 'Wichita'  # ICAO variant

    def test_static_dict_still_wins_and_code_is_last_resort(self):
        from flight_display import FlightDisplay

        d = FlightDisplay.__new__(FlightDisplay)
        d.learned_cities = {'ORD': 'WrongTown', 'ICT': 'Wichita'}

        assert d._get_airport_city('ORD') == 'CHICAGO'  # static dict first
        d.learned_cities = {}
        assert d._get_airport_city('ICT') == 'ICT'      # unknown: raw code


class TestEnrichLearnsCities:
    def test_enrich_learns_airport_cities_from_response(self):
        from adsb_lol_source import enrich_routes

        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        flights = [{
            "callsign": "UAL6", "latitude": 41.9, "longitude": -87.6,
            "origin_iata": None, "dest_iata": None, "airline_code": None,
        }]
        good = MagicMock(status_code=200)
        good.json.return_value = [{
            "callsign": "UAL6", "plausible": True,
            "_airport_codes_iata": "ORD-ICT", "airline_code": "UAL",
            "_airports": [
                {"iata": "ORD", "location": "Chicago"},
                {"iata": "ICT", "location": "Wichita"},
            ],
        }]

        with patch("adsb_lol_source.requests.post", return_value=good), \
                patch("adsb_lol_source.airport_cities") as mock_ac:
            enrich_routes("https://api.adsb.lol", flights, mock_cache)

        mock_ac.learn.assert_called_once_with(
            {'ORD': 'Chicago', 'ICT': 'Wichita'})

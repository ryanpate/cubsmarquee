"""FlightWall-style restyle: colors, logos, detail card, summary"""

from __future__ import annotations

from unittest.mock import Mock

import pytest


class TestFlightwallColors:
    def test_cyan_and_dim_constants_exist(self) -> None:
        from scoreboard_config import Colors

        assert Colors.FLIGHT_CYAN == (120, 220, 255)
        assert Colors.FLIGHT_DIM == (90, 90, 90)


class TestAirlineLogos:
    PREFIXES = ['UAL', 'AAL', 'DAL', 'SWA', 'SKW', 'RPA', 'ENY',
                'NKS', 'FFT', 'JBU', 'ASA', 'FDX', 'UPS']

    def _display(self):
        from flight_display import FlightDisplay

        d = FlightDisplay.__new__(FlightDisplay)
        d.airline_logos = d._load_airline_logos()
        return d

    def test_all_thirteen_logos_load(self) -> None:
        d = self._display()

        for prefix in self.PREFIXES:
            assert prefix in d.airline_logos, f'missing logo for {prefix}'
            assert d.airline_logos[prefix].size == (20, 20)

    def test_known_airline_returns_png(self) -> None:
        d = self._display()

        logo = d._airline_logo('UAL1837')
        assert logo is d.airline_logos['UAL']

    def test_unknown_airline_gets_cached_monogram(self) -> None:
        d = self._display()

        badge = d._airline_logo('XYZ999')
        assert badge.size == (20, 20)
        assert d._airline_logo('XYZ999') is badge  # built once, cached

    def test_monogram_is_deterministic(self) -> None:
        d = self._display()

        a = d._monogram_badge('XYZ999')
        b = d._monogram_badge('XYZ999')
        assert list(a.getdata()) == list(b.getdata())

    def test_iata_callsign_conversion_still_works(self) -> None:
        from flight_display import FlightDisplay

        d = FlightDisplay.__new__(FlightDisplay)
        assert d._icao_to_iata_callsign('UAL1837') == 'UA1837'
        assert d._icao_to_iata_callsign('XXX123') is None

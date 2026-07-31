"""FlightWall-style restyle: colors, logos, detail card, summary"""

from __future__ import annotations

from unittest.mock import Mock


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


UAL_FLIGHT = {
    'callsign': 'UAL1837', 'altitude_ft': 4100, 'velocity_mph': 250,
    'distance': 2.3, 'latitude': 41.97, 'longitude': -87.72,
    'aircraft_type': 'A21N', 'registration': 'N44501',
    'vertical_rate': -1088, 'heading': 263, 'icao_hex': 'a55fa2',
    'origin_iata': 'ORD', 'dest_iata': 'LAX', 'destination': 'LAX',
}

GA_FLIGHT = {
    'callsign': 'N425PC', 'altitude_ft': 2400, 'velocity_mph': 140,
    'distance': 4.1, 'latitude': 42.01, 'longitude': -87.60,
    'aircraft_type': 'SR22', 'registration': 'N425PC',
    'vertical_rate': None, 'heading': None, 'icao_hex': 'a4f2e1',
    'destination': 'UNKNOWN',
}


def _card_display():
    """FlightDisplay wired with a Mock manager and no logo files"""
    from flight_display import FlightDisplay
    from scoreboard_config import Colors

    d = FlightDisplay.__new__(FlightDisplay)
    d.manager = Mock()
    d.airline_logos = {}  # forces the monogram path: no filesystem needed
    d.FLIGHT_WHITE = Colors.WHITE
    d.FLIGHT_CYAN = Colors.FLIGHT_CYAN
    d.manager.fit_text_aa.side_effect = lambda text, max_width: text
    d.manager.measure_text_aa.side_effect = lambda text: len(text) * 6
    return d


def _texts(manager):
    """(color, text) for every draw_text and draw_text_aa call"""
    calls = [(c.args[3], c.args[4])
             for c in manager.draw_text.call_args_list]
    calls += [(c.args[2], c.args[3])
              for c in manager.draw_text_aa.call_args_list]
    return calls


class TestDetailCardFormatting:
    def _display(self):
        from flight_display import FlightDisplay

        return FlightDisplay.__new__(FlightDisplay)

    def test_fmt_alt(self) -> None:
        d = self._display()

        assert d._fmt_alt(732) == '732ft'
        assert d._fmt_alt(4100) == '4.1kft'
        assert d._fmt_alt(34000) == '34kft'

    def test_display_case_keeps_short_names_upper(self) -> None:
        d = self._display()

        assert d._display_case('UNITED') == 'United'
        assert d._display_case('AIR FRANCE') == 'Air France'
        assert d._display_case('UPS') == 'UPS'

    def test_friendly_type(self) -> None:
        d = self._display()

        assert d._friendly_type('A21N') == 'A321neo'
        assert d._friendly_type('B38M') == '737 MAX 8'
        assert d._friendly_type('ZZZZ') == 'ZZZZ'   # unknown: raw code
        assert d._friendly_type('') == ''
        assert d._friendly_type(None) == ''


class TestDetailCardFrame:
    def test_page_a_ids_and_metrics(self) -> None:
        from scoreboard_config import Colors

        d = _card_display()
        d._draw_detail_frame(dict(UAL_FLIGHT), '1/3', 0.0)

        texts = [t for _, t in _texts(d.manager)]
        assert 'United' in texts
        assert 'ORD-LAX' in texts
        assert 'A321neo' in texts
        assert 'Alt:' in texts and '4.1kft' in texts
        assert '250mph' in texts and '263deg' in texts and '-1088fpm' in texts
        # Values cyan, labels white
        colors = dict((t, c) for c, t in _texts(d.manager))
        assert colors['4.1kft'] == Colors.FLIGHT_CYAN
        assert colors['Alt:'] == Colors.WHITE
        # Counter only on page B
        assert '1/3' not in texts

    def test_page_b_destination_and_counter(self) -> None:
        d = _card_display()
        d._draw_detail_frame(dict(UAL_FLIGHT), '1/3', 4.0)

        texts = [t for _, t in _texts(d.manager)]
        assert 'Flying to' in texts
        assert 'Los Angeles' in texts
        assert '1/3' in texts
        assert 'Alt:' not in texts

    def test_logo_pasted_top_left(self) -> None:
        d = _card_display()
        d._draw_detail_frame(dict(UAL_FLIGHT), '1/3', 0.0)

        (img, x, y) = d.manager.set_image.call_args.args
        assert (x, y) == (2, 2)
        assert img.size == (20, 20)

    def test_ga_flight_fallbacks(self) -> None:
        d = _card_display()
        d._draw_detail_frame(dict(GA_FLIGHT), '3/3', 4.0)

        texts = [t for _, t in _texts(d.manager)]
        assert 'N425PC' in texts          # callsign as line 1
        # N425PC appears twice: once as ID line 1, once as the page-B
        # registration value (registration always drawn, even when it
        # repeats the callsign)
        assert texts.count('N425PC') == 2
        assert 'SR22' in texts
        assert 'Registration' in texts     # page B fallback


class TestSummaryRestyle:
    def _render_one_frame(self):
        from flight_display import FlightDisplay
        from scoreboard_config import Colors

        d = FlightDisplay.__new__(FlightDisplay)
        d.manager = Mock()
        d.FLIGHT_WHITE = Colors.WHITE
        d.FLIGHT_CYAN = Colors.FLIGHT_CYAN
        d.flight_data = [dict(UAL_FLIGHT), dict(GA_FLIGHT)]
        # Make swap_canvas trigger KeyboardInterrupt to exit after one frame
        d.manager.swap_canvas.side_effect = KeyboardInterrupt
        try:
            d._display_summary_view(5)
        except KeyboardInterrupt:
            pass
        return d

    def test_headline_and_cyan_values(self) -> None:
        from scoreboard_config import Colors

        d = self._render_one_frame()

        texts = dict((t, c) for c, t in _texts(d.manager))
        assert '2 aircraft' in texts
        assert texts['Closest:'] == Colors.WHITE
        assert texts['2.3mi'] == Colors.FLIGHT_CYAN
        assert texts['4.1kft'] == Colors.FLIGHT_CYAN   # highest
        assert texts['2.4kft'] == Colors.FLIGHT_CYAN   # lowest

    def test_plane_motif_drawn(self) -> None:
        d = self._render_one_frame()

        assert d.manager.draw_pixel.called  # silhouette pixels on black


class TestEmptyStateRestyle:
    def test_no_flights_screen_is_headerless(self) -> None:
        from flight_display import FlightDisplay
        from scoreboard_config import Colors

        d = FlightDisplay.__new__(FlightDisplay)
        d.manager = Mock()
        d.FLIGHT_WHITE = Colors.WHITE
        d.manager.swap_canvas.side_effect = KeyboardInterrupt
        d.manager.measure_text_aa.side_effect = lambda text: len(text) * 6
        try:
            d._display_no_flights(5)
        except KeyboardInterrupt:
            pass

        texts = [t for _, t in _texts(d.manager)]
        assert 'No flights' in texts
        assert 'overhead' in texts
        d.manager.set_image.assert_not_called()  # no gradient header image

    def test_header_machinery_removed(self) -> None:
        from flight_display import FlightDisplay

        assert not hasattr(FlightDisplay, '_draw_flight_header')
        assert not hasattr(FlightDisplay, '_create_flight_header_background')


class TestAATextOnFlightScreens:
    def test_detail_card_id_lines_use_aa(self) -> None:
        d = _card_display()
        d._draw_detail_frame(dict(UAL_FLIGHT), '1/3', 0.0)

        aa_texts = [c.args[3]
                    for c in d.manager.draw_text_aa.call_args_list]
        assert 'United' in aa_texts
        assert 'ORD-LAX' in aa_texts
        assert 'A321neo' in aa_texts
        # Metric rows stay bitmap micro
        bitmap_fonts = set(
            c.args[0] for c in d.manager.draw_text.call_args_list)
        assert bitmap_fonts == {'micro'}

    def test_id_lines_are_width_truncated(self) -> None:
        d = _card_display()
        d._draw_detail_frame(dict(UAL_FLIGHT), '1/3', 0.0)

        fitted_widths = [c.args[1]
                         for c in d.manager.fit_text_aa.call_args_list]
        assert 68 in fitted_widths  # 96 - 26 - 2 beside the logo

    def test_page_b_city_uses_aa_and_fits_beside_counter(self) -> None:
        d = _card_display()
        d._draw_detail_frame(dict(UAL_FLIGHT), '1/3', 4.0)

        aa_texts = [c.args[3]
                    for c in d.manager.draw_text_aa.call_args_list]
        assert 'Flying to' in aa_texts
        assert 'Los Angeles' in aa_texts

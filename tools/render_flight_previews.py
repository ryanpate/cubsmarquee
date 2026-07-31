#!/usr/bin/env python3
"""Render one PNG frame of each flight screen for visual review.

Runs headless: rgbmatrix is mocked exactly like tests/conftest.py, and
frames are captured from ScoreboardManager's PIL preview mirror.

Usage (from repo root): python3 tools/render_flight_previews.py
Output: flight_previews/<screen>.png plus 8x nearest-neighbor upscales.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)  # code uses relative ./fonts and ./logos paths

# Mock the rgbmatrix module before any imports that depend on it
sys.modules['rgbmatrix'] = MagicMock()
sys.modules['rgbmatrix.graphics'] = MagicMock()
mock_graphics = sys.modules['rgbmatrix.graphics']
mock_graphics.Font = MagicMock()
mock_graphics.Color = MagicMock()
mock_graphics.DrawText = MagicMock()

from PIL import Image  # noqa: E402

OUT_DIR = os.path.join(REPO_ROOT, 'flight_previews')

FIXTURE_FLIGHTS = [
    {   # Airliner with full data: logo, route, friendly type, destination
        'callsign': 'UAL1837', 'altitude_ft': 4100, 'velocity_mph': 250,
        'distance': 2.3, 'latitude': 41.97, 'longitude': -87.72,
        'aircraft_type': 'A21N', 'registration': 'N44501',
        'vertical_rate': -1088, 'heading': 263, 'icao_hex': 'a55fa2',
        'origin_iata': 'ORD', 'dest_iata': 'LAX', 'destination': 'LAX',
    },
    {   # Climbing Southwest 737 MAX 8
        'callsign': 'SWA452', 'altitude_ft': 12500, 'velocity_mph': 320,
        'distance': 6.8, 'latitude': 41.88, 'longitude': -87.55,
        'aircraft_type': 'B38M', 'registration': 'N8706W',
        'vertical_rate': 1856, 'heading': 45, 'icao_hex': 'ab34cd',
        'origin_iata': 'MDW', 'dest_iata': 'DEN', 'destination': 'DEN',
    },
    {   # GA prop: no airline, no route, no heading -> fallback paths
        'callsign': 'N425PC', 'altitude_ft': 2400, 'velocity_mph': 140,
        'distance': 4.1, 'latitude': 42.01, 'longitude': -87.60,
        'aircraft_type': 'SR22', 'registration': 'N425PC',
        'vertical_rate': None, 'heading': None, 'icao_hex': 'a4f2e1',
        'destination': 'UNKNOWN',
    },
]


class _FrameCaptured(Exception):
    """Raised from a patched swap_canvas to stop after one frame"""


def _make_display(manager):
    from flight_display import FlightDisplay
    from scoreboard_config import Colors

    d = FlightDisplay.__new__(FlightDisplay)
    d.manager = manager
    d.latitude, d.longitude = 41.9484, -87.6553
    d.flight_max_range_nm = 30
    d.enable_flight_radar = True
    d.flight_data = [dict(f) for f in FIXTURE_FLIGHTS]
    d.destination_cache = {}
    d.FLIGHT_BLUE = Colors.FLIGHT_BLUE
    d.FLIGHT_DARK_BLUE = Colors.FLIGHT_DARK_BLUE
    d.FLIGHT_WHITE = Colors.WHITE
    d.ALTITUDE_HIGH = Colors.FLIGHT_ALTITUDE_HIGH
    d.ALTITUDE_MED = Colors.FLIGHT_ALTITUDE_MED
    d.ALTITUDE_LOW = Colors.FLIGHT_ALTITUDE_LOW
    d.FLIGHT_CYAN = Colors.FLIGHT_CYAN
    # Pre-restyle only: the gradient header cache (removed in Task 6)
    if hasattr(d, '_create_flight_header_background'):
        d._flight_header_bg = d._create_flight_header_background()
    # Post-Task-2 only: airline logos
    if hasattr(d, '_load_airline_logos'):
        d.airline_logos = d._load_airline_logos()
    return d


def _save(manager, name):
    frame = manager.get_frame_copy()
    frame.save(os.path.join(OUT_DIR, f'{name}.png'))
    frame.resize((96 * 8, 48 * 8), Image.NEAREST).save(
        os.path.join(OUT_DIR, f'{name}@8x.png'))
    print(f'  wrote {name}.png')


def _capture(manager, name, fn):
    """Run fn, stopping at the first swap_canvas, and save the frame"""
    def stop(*args, **kwargs):
        raise _FrameCaptured
    manager.swap_canvas = stop
    try:
        fn()
    except _FrameCaptured:
        pass
    finally:
        del manager.swap_canvas  # restore the real method
    _save(manager, name)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    from scoreboard_manager import ScoreboardManager

    manager = ScoreboardManager()
    d = _make_display(manager)

    _capture(manager, 'detail_a',
             lambda: d._draw_detail_frame(d.flight_data[0], '1/3', 0.0))
    _capture(manager, 'detail_b',
             lambda: d._draw_detail_frame(d.flight_data[0], '1/3', 4.0))
    _capture(manager, 'detail_ga',
             lambda: d._draw_detail_frame(d.flight_data[2], '3/3', 4.0))
    _capture(manager, 'summary', lambda: d._display_summary_view(5))
    _capture(manager, 'radar', lambda: d._display_radar_view(0, 5))

    d.flight_data = []
    _capture(manager, 'no_flights', lambda: d._display_no_flights(5))
    print(f'Done. Previews in {OUT_DIR}')


if __name__ == '__main__':
    main()

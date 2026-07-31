"""FlightWall-style restyle: colors, logos, detail card, summary"""

from __future__ import annotations

from unittest.mock import Mock

import pytest


class TestFlightwallColors:
    def test_cyan_and_dim_constants_exist(self) -> None:
        from scoreboard_config import Colors

        assert Colors.FLIGHT_CYAN == (120, 220, 255)
        assert Colors.FLIGHT_DIM == (90, 90, 90)

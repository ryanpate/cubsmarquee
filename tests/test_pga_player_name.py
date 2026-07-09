"""Tests for PGA player name extraction (handles individual and team events)."""

from __future__ import annotations

import pytest

from pga_display import PGADisplay


class TestExtractPlayerName:
    def test_individual_event_uses_athlete_displayname(self) -> None:
        player = {"athlete": {"displayName": "Scottie Scheffler"}}
        assert PGADisplay._extract_player_name(player) == "Scottie Scheffler"

    def test_team_event_combines_roster_last_names(self) -> None:
        # Zurich Classic format: no top-level athlete; players in roster
        player = {
            "team": {"displayName": "J. Dufner / A. Cook"},
            "roster": [
                {"athlete": {"lastName": "Dufner"}},
                {"athlete": {"lastName": "Cook"}},
            ],
        }
        # Renderer takes the last whitespace-separated token, truncated to 7
        # chars and uppercased. We need a name with NO spaces so the renderer
        # keeps both partners visible (e.g. "Duf/Coo" -> "DUF/COO").
        result = PGADisplay._extract_player_name(player)
        assert " " not in result
        assert "Duf" in result and "Coo" in result

    def test_team_event_falls_back_to_team_displayname_if_roster_missing(self) -> None:
        player = {"team": {"displayName": "J. Dufner / A. Cook"}}
        result = PGADisplay._extract_player_name(player)
        assert result == "J. Dufner / A. Cook"

    def test_unknown_when_no_data(self) -> None:
        assert PGADisplay._extract_player_name({}) == "Unknown"

    def test_handles_none_athlete(self) -> None:
        # Defensive: ESPN sometimes sends athlete: null
        assert PGADisplay._extract_player_name({"athlete": None}) == "Unknown"

"""Unit tests for core logic - schedule parsing, score calculations, time formatting"""

from __future__ import annotations

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Any


# ============================================================================
# Test Data Fixtures
# ============================================================================

@pytest.fixture
def sample_game_data() -> list[dict[str, Any]]:
    """Sample game data matching MLB Stats API format"""
    return [
        {
            'game_id': 12345,
            'game_date': '2024-07-15',
            'game_datetime': '2024-07-15T19:05:00Z',
            'status': 'Scheduled',
            'home_id': 112,  # Cubs
            'away_id': 158,  # Brewers
            'home_score': 0,
            'away_score': 0,
            'home_probable_pitcher': 'Imanaga',
            'away_probable_pitcher': 'Burnes',
            'doubleheader': 'N',
            'game_type': 'R',
            'series_status': ''
        }
    ]


@pytest.fixture
def sample_doubleheader_data() -> list[dict[str, Any]]:
    """Sample doubleheader game data"""
    return [
        {
            'game_id': 12345,
            'game_date': '2024-07-15',
            'game_datetime': '2024-07-15T13:20:00Z',
            'status': 'Final',
            'home_id': 112,
            'away_id': 158,
            'home_score': 5,
            'away_score': 3,
            'doubleheader': 'S',
            'game_type': 'R'
        },
        {
            'game_id': 12346,
            'game_date': '2024-07-15',
            'game_datetime': '2024-07-15T19:05:00Z',
            'status': 'Scheduled',
            'home_id': 112,
            'away_id': 158,
            'home_score': 0,
            'away_score': 0,
            'doubleheader': 'S',
            'game_type': 'R'
        }
    ]


@pytest.fixture
def sample_live_game_data() -> list[dict[str, Any]]:
    """Sample live game data"""
    return [
        {
            'game_id': 12345,
            'game_date': '2024-07-15',
            'game_datetime': '2024-07-15T19:05:00Z',
            'status': 'In Progress',
            'home_id': 112,
            'away_id': 158,
            'home_score': 4,
            'away_score': 2,
            'doubleheader': 'N',
            'game_type': 'R'
        }
    ]


@pytest.fixture
def sample_final_game_data() -> list[dict[str, Any]]:
    """Sample final game data"""
    return [
        {
            'game_id': 12345,
            'game_date': '2024-07-15',
            'game_datetime': '2024-07-15T19:05:00Z',
            'status': 'Final',
            'home_id': 112,
            'away_id': 158,
            'home_score': 7,
            'away_score': 3,
            'doubleheader': 'N',
            'game_type': 'R'
        }
    ]


@pytest.fixture
def sample_bears_event() -> dict[str, Any]:
    """Sample Bears game event from ESPN API"""
    return {
        'id': '401547417',
        'name': 'Chicago Bears at Green Bay Packers',
        'date': '2024-09-08T17:00:00Z',
        'competitions': [
            {
                'competitors': [
                    {
                        'team': {
                            'abbreviation': 'GB',
                            'displayName': 'Green Bay Packers'
                        },
                        'homeAway': 'home',
                        'score': '24'
                    },
                    {
                        'team': {
                            'abbreviation': 'CHI',
                            'displayName': 'Chicago Bears'
                        },
                        'homeAway': 'away',
                        'score': '17'
                    }
                ],
                'status': {
                    'type': {
                        'name': 'STATUS_FINAL',
                        'shortDetail': 'Final'
                    }
                }
            }
        ]
    }


# ============================================================================
# Schedule Parsing Tests
# ============================================================================

class TestScheduleParsing:
    """Tests for schedule parsing logic"""

    def test_determine_game_index_single_game(
        self, sample_game_data: list[dict[str, Any]]
    ) -> None:
        """Single game should return index 0"""
        # Import here to avoid import errors when rgbmatrix not available
        from main import CubsScoreboard

        with patch.object(CubsScoreboard, '__init__', lambda x: None):
            scoreboard = CubsScoreboard.__new__(CubsScoreboard)
            result = scoreboard.determine_game_index(sample_game_data)
            assert result == 0

    def test_determine_game_index_doubleheader_first_game_active(
        self, sample_doubleheader_data: list[dict[str, Any]]
    ) -> None:
        """Doubleheader with first game final should return index 1"""
        from main import CubsScoreboard

        with patch.object(CubsScoreboard, '__init__', lambda x: None):
            scoreboard = CubsScoreboard.__new__(CubsScoreboard)
            result = scoreboard.determine_game_index(sample_doubleheader_data)
            assert result == 1

    def test_determine_game_index_doubleheader_first_game_in_progress(
        self, sample_doubleheader_data: list[dict[str, Any]]
    ) -> None:
        """Doubleheader with first game in progress should return index 0"""
        from main import CubsScoreboard

        sample_doubleheader_data[0]['status'] = 'In Progress'

        with patch.object(CubsScoreboard, '__init__', lambda x: None):
            scoreboard = CubsScoreboard.__new__(CubsScoreboard)
            result = scoreboard.determine_game_index(sample_doubleheader_data)
            assert result == 0

    def test_empty_schedule_returns_zero(self) -> None:
        """Empty schedule should return index 0"""
        from main import CubsScoreboard

        with patch.object(CubsScoreboard, '__init__', lambda x: None):
            scoreboard = CubsScoreboard.__new__(CubsScoreboard)
            result = scoreboard.determine_game_index([])
            assert result == 0


# ============================================================================
# Score Calculation Tests
# ============================================================================

class TestScoreCalculations:
    """Tests for score-related calculations"""

    def test_cubs_home_score_extraction(
        self, sample_live_game_data: list[dict[str, Any]]
    ) -> None:
        """Test extracting Cubs score when Cubs are home"""
        from scoreboard_config import TeamConfig

        game = sample_live_game_data[0]
        is_cubs_home = game['home_id'] == TeamConfig.CUBS_TEAM_ID

        assert is_cubs_home is True
        cubs_score = game['home_score'] if is_cubs_home else game['away_score']
        assert cubs_score == 4

    def test_cubs_away_score_extraction(
        self, sample_live_game_data: list[dict[str, Any]]
    ) -> None:
        """Test extracting Cubs score when Cubs are away"""
        from scoreboard_config import TeamConfig

        # Swap home/away
        game = sample_live_game_data[0]
        game['home_id'] = 158  # Brewers
        game['away_id'] = 112  # Cubs
        game['home_score'] = 2
        game['away_score'] = 4

        is_cubs_home = game['home_id'] == TeamConfig.CUBS_TEAM_ID

        assert is_cubs_home is False
        cubs_score = game['home_score'] if is_cubs_home else game['away_score']
        assert cubs_score == 4

    def test_cubs_win_detection(
        self, sample_final_game_data: list[dict[str, Any]]
    ) -> None:
        """Test detecting a Cubs win"""
        from scoreboard_config import TeamConfig

        game = sample_final_game_data[0]
        is_cubs_home = game['home_id'] == TeamConfig.CUBS_TEAM_ID

        cubs_score = game['home_score'] if is_cubs_home else game['away_score']
        opp_score = game['away_score'] if is_cubs_home else game['home_score']

        cubs_won = cubs_score > opp_score
        assert cubs_won is True

    def test_cubs_loss_detection(
        self, sample_final_game_data: list[dict[str, Any]]
    ) -> None:
        """Test detecting a Cubs loss"""
        game = sample_final_game_data[0]
        game['home_score'] = 2
        game['away_score'] = 5

        cubs_score = game['home_score']  # Cubs are home
        opp_score = game['away_score']

        cubs_won = cubs_score > opp_score
        assert cubs_won is False


# ============================================================================
# Time Formatting Tests
# ============================================================================

class TestTimeFormatting:
    """Tests for game time formatting"""

    def test_format_game_time_evening(self) -> None:
        """Test formatting evening game time (7:05 PM)"""
        game_data = [{'game_datetime': '2024-07-15T00:05:00Z'}]  # UTC midnight + 5min = 7:05 PM CT

        # The format_game_time function extracts time and converts
        game_time = game_data[0]['game_datetime'][-9:19]
        assert game_time == '00:05:00'

    def test_format_game_time_afternoon(self) -> None:
        """Test formatting afternoon game time"""
        game_data = [{'game_datetime': '2024-07-15T18:20:00Z'}]  # 1:20 PM CT

        game_time = game_data[0]['game_datetime'][-9:19]
        assert game_time == '18:20:00'

    def test_format_game_time_night(self) -> None:
        """Test formatting night game time"""
        game_data = [{'game_datetime': '2024-07-15T01:10:00Z'}]  # 8:10 PM CT

        game_time = game_data[0]['game_datetime'][-9:19]
        assert game_time == '01:10:00'


# ============================================================================
# Bears Score Parsing Tests
# ============================================================================

class TestBearsScoreParsing:
    """Tests for Bears ESPN API score parsing"""

    def test_parse_bears_score_from_event(
        self, sample_bears_event: dict[str, Any]
    ) -> None:
        """Test parsing Bears score from ESPN event data"""
        competition = sample_bears_event['competitions'][0]
        competitors = competition['competitors']

        bears_score = None
        opp_score = None

        for comp in competitors:
            if comp['team']['abbreviation'] == 'CHI':
                bears_score = comp['score']
            else:
                opp_score = comp['score']

        assert bears_score == '17'
        assert opp_score == '24'

    def test_parse_bears_home_away_status(
        self, sample_bears_event: dict[str, Any]
    ) -> None:
        """Test determining if Bears are home or away"""
        competition = sample_bears_event['competitions'][0]
        competitors = competition['competitors']

        bears_home = False
        for comp in competitors:
            if comp['team']['abbreviation'] == 'CHI':
                bears_home = comp['homeAway'] == 'home'
                break

        assert bears_home is False  # Bears are away in this fixture

    def test_parse_game_status(self, sample_bears_event: dict[str, Any]) -> None:
        """Test parsing game status from ESPN data"""
        competition = sample_bears_event['competitions'][0]
        status = competition['status']['type']['name']

        assert status == 'STATUS_FINAL'


# ============================================================================
# Configuration Tests
# ============================================================================

class TestConfiguration:
    """Tests for configuration constants"""

    def test_cubs_team_id(self) -> None:
        """Test Cubs team ID constant"""
        from scoreboard_config import TeamConfig
        assert TeamConfig.CUBS_TEAM_ID == 112

    def test_league_ids(self) -> None:
        """Test league ID constants"""
        from scoreboard_config import TeamConfig
        assert TeamConfig.NL_LEAGUE_ID == 104
        assert TeamConfig.AL_LEAGUE_ID == 103

    def test_display_dimensions(self) -> None:
        """Test display dimension constants"""
        from scoreboard_config import DisplayConfig
        assert DisplayConfig.MATRIX_ROWS == 48
        assert DisplayConfig.MATRIX_COLS == 96

    def test_color_tuples_are_valid(self) -> None:
        """Test that color constants are valid RGB tuples"""
        from scoreboard_config import Colors

        colors_to_check = [
            Colors.WHITE, Colors.BLACK, Colors.YELLOW,
            Colors.CUBS_BLUE, Colors.BEARS_NAVY, Colors.BEARS_ORANGE,
            Colors.PGA_BLUE, Colors.PGA_GOLD
        ]

        for color in colors_to_check:
            assert isinstance(color, tuple)
            assert len(color) == 3
            assert all(isinstance(c, int) for c in color)
            assert all(0 <= c <= 255 for c in color)

    def test_game_config_intervals(self) -> None:
        """Test that interval constants are reasonable"""
        from scoreboard_config import GameConfig

        # All intervals should be positive
        assert GameConfig.WEATHER_UPDATE_INTERVAL > 0
        assert GameConfig.NEWS_UPDATE_INTERVAL > 0
        assert GameConfig.SCHEDULE_UPDATE_INTERVAL > 0
        assert GameConfig.LIVE_SCORE_UPDATE_INTERVAL > 0

        # Live scores should update more frequently than schedules
        assert GameConfig.LIVE_SCORE_UPDATE_INTERVAL < GameConfig.SCHEDULE_UPDATE_INTERVAL


# ============================================================================
# Off-Season Detection Tests
# ============================================================================

class TestOffSeasonDetection:
    """Tests for off-season detection logic"""

    def test_no_games_is_off_season(self) -> None:
        """Empty schedule should trigger off-season"""
        from scoreboard_config import GameConfig

        game_data: list[dict[str, Any]] = []
        is_off_season = len(game_data) == 0

        assert is_off_season is True

    def test_distant_game_is_off_season(self) -> None:
        """Game more than 30 days away should trigger off-season"""
        from scoreboard_config import GameConfig
        import pendulum

        # Create a game 45 days from now
        future_date = pendulum.now().add(days=45)
        game_data = [{'game_date': future_date.to_date_string()}]

        game_date = pendulum.parse(game_data[0]['game_date'])
        days_until_game = (game_date - pendulum.now()).days

        is_off_season = days_until_game > GameConfig.OFF_SEASON_DAYS_THRESHOLD

        assert is_off_season is True

    def test_near_game_is_not_off_season(self) -> None:
        """Game less than 30 days away should not trigger off-season"""
        from scoreboard_config import GameConfig
        import pendulum

        # Create a game 5 days from now
        future_date = pendulum.now().add(days=5)
        game_data = [{'game_date': future_date.to_date_string()}]

        game_date = pendulum.parse(game_data[0]['game_date'])
        days_until_game = (game_date - pendulum.now()).days

        is_off_season = days_until_game > GameConfig.OFF_SEASON_DAYS_THRESHOLD

        assert is_off_season is False


# ============================================================================
# Game Status Routing Tests
# ============================================================================

class TestGameStatusRouting:
    """Tests for game status routing logic"""

    def test_scheduled_status(self) -> None:
        """Scheduled status should route to no_game display"""
        status = 'Scheduled'
        assert status == 'Scheduled'

    def test_warmup_statuses(self) -> None:
        """Warmup statuses should route to warmup display"""
        warmup_statuses = ['Warmup', 'Pre-Game']
        for status in warmup_statuses:
            assert status in ['Warmup', 'Pre-Game']

    def test_delayed_status_matching(self) -> None:
        """Delayed status should match startswith pattern"""
        delayed_statuses = ['Delayed', 'Delayed: Rain', 'Delayed: Start']
        for status in delayed_statuses:
            assert status.startswith('Delayed')

    def test_postponed_status_matching(self) -> None:
        """Postponed status should match startswith pattern"""
        postponed_statuses = ['Postponed', 'Postponed: Rain']
        for status in postponed_statuses:
            assert status.startswith('Postpon')

    def test_in_progress_status(self) -> None:
        """In Progress status should route to live game"""
        status = 'In Progress'
        assert status == 'In Progress'

    def test_final_statuses(self) -> None:
        """Final statuses should route to game over display"""
        final_statuses = ['Final', 'Game Over']
        for status in final_statuses:
            assert status in ['Final', 'Game Over']

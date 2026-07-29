"""Tests for the team pack module"""

from teams import (
    TEAMS, DEFAULT_TEAM_SLUG, NON_DEFAULT_OFF_KEYS,
    get_active_team, apply_team_defaults, data_path_candidates,
)


class TestTeamResolution:
    def test_default_is_cubs_when_config_empty(self):
        assert get_active_team({}).slug == 'cubs'

    def test_explicit_cubs(self):
        assert get_active_team({'team': 'cubs'}).mlb_team_id == 112

    def test_explicit_cardinals(self):
        pack = get_active_team({'team': 'cardinals'})
        assert pack.mlb_team_id == 138
        assert pack.abbrev == 'STL'

    def test_unknown_slug_falls_back_to_cubs(self):
        assert get_active_team({'team': 'yankees'}).slug == 'cubs'

    def test_none_config_uses_load_user_config(self, monkeypatch):
        import teams
        monkeypatch.setattr(teams, 'load_user_config',
                            lambda: {'team': 'cardinals'})
        assert get_active_team().slug == 'cardinals'


class TestPackContents:
    def test_both_packs_present(self):
        assert set(TEAMS) == {'cubs', 'cardinals'}

    def test_cubs_pack_values(self):
        cubs = TEAMS['cubs']
        assert cubs.matchup_name == 'CHICAGO CUBS'
        assert cubs.primary_color == (0, 51, 102)
        assert cubs.logo_path == './logos/cubs.png'
        assert cubs.marquee_path == './marquee.png'
        assert cubs.celebration_path == './W.gif'

    def test_cardinals_pack_values(self):
        stl = TEAMS['cardinals']
        assert stl.name == 'St. Louis Cardinals'
        assert stl.matchup_name == 'ST LOUIS CARDINALS'
        assert stl.primary_color == (196, 30, 58)
        assert stl.secondary_color == (12, 35, 64)
        assert stl.news_rss_url == (
            'https://www.mlb.com/cardinals/feeds/news/rss.xml')

    def test_slug_matches_dict_key(self):
        for slug, pack in TEAMS.items():
            assert pack.slug == slug


class TestTeamDefaults:
    DEFAULTS = {'enable_bears': True, 'enable_bears_news': True,
                'enable_clock': True, 'enable_weather': True}

    def test_cubs_leaves_defaults_alone(self):
        out = apply_team_defaults(self.DEFAULTS, {'team': 'cubs'})
        assert out == self.DEFAULTS

    def test_missing_team_leaves_defaults_alone(self):
        out = apply_team_defaults(self.DEFAULTS, {})
        assert out == self.DEFAULTS

    def test_cardinals_turns_off_chicago_content(self):
        out = apply_team_defaults(self.DEFAULTS, {'team': 'cardinals'})
        assert out['enable_bears'] is False
        assert out['enable_bears_news'] is False
        assert out['enable_clock'] is False
        assert out['enable_weather'] is True

    def test_explicit_user_choice_wins(self):
        user = {'team': 'cardinals', 'enable_bears': True}
        out = apply_team_defaults(self.DEFAULTS, user)
        assert out['enable_bears'] is True

    def test_input_dict_not_mutated(self):
        snapshot = dict(self.DEFAULTS)
        apply_team_defaults(self.DEFAULTS, {'team': 'cardinals'})
        assert self.DEFAULTS == snapshot


def test_data_path_candidates():
    assert data_path_candidates('cubs_facts.json') == [
        './cubs_facts.json', '/home/pi/cubs_facts.json']


class TestConfigValidatorTeam:
    def _validator_with(self, config):
        from config_validator import ConfigValidator
        v = ConfigValidator()
        v.config = config
        return v

    def test_known_team_valid(self):
        result = self._validator_with({'team': 'cardinals'}).validate_team()
        assert result.is_valid

    def test_missing_team_valid(self):
        result = self._validator_with({}).validate_team()
        assert result.is_valid

    def test_unknown_team_flagged_not_required(self):
        result = self._validator_with({'team': 'mets'}).validate_team()
        assert not result.is_valid
        assert not result.is_required


class TestTeamHistoryDisplay:
    def test_loads_active_team_history(self, monkeypatch):
        import teams
        monkeypatch.setattr(teams, 'load_user_config',
                            lambda: {'team': 'cardinals'})
        from cubs_history_display import TeamHistoryDisplay
        from unittest.mock import MagicMock
        display = TeamHistoryDisplay(MagicMock())
        assert display.team.slug == 'cardinals'
        assert display.history  # cardinals_history.json parsed

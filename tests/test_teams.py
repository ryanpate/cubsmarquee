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


class TestNewsKeywords:
    def test_both_packs_have_keywords(self):
        for pack in TEAMS.values():
            assert pack.news_keywords

    def test_cubs_keywords_contain_expected_terms(self):
        assert 'CUBS' in TEAMS['cubs'].news_keywords
        assert 'WRIGLEY FIELD' in TEAMS['cubs'].news_keywords

    def test_cardinals_keywords_contain_expected_terms(self):
        assert 'CARDINALS' in TEAMS['cardinals'].news_keywords
        assert 'BUSCH STADIUM' in TEAMS['cardinals'].news_keywords

    def test_cardinals_keywords_do_not_include_cubs(self):
        assert 'CUBS' not in TEAMS['cardinals'].news_keywords


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
        assert out['enable_bears'] is True
        assert out['enable_bears_news'] is True
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

    def test_cardinals_reword_custom_message_default(self):
        defaults = {'custom_message': 'GO CUBS GO! SEE YOU NEXT SEASON!'}
        out = apply_team_defaults(defaults, {'team': 'cardinals'})
        assert 'CUBS' not in out['custom_message']
        assert 'CARDINALS' in out['custom_message']

    def test_cubs_custom_message_default_unchanged(self):
        defaults = {'custom_message': 'GO CUBS GO! SEE YOU NEXT SEASON!'}
        out = apply_team_defaults(defaults, {'team': 'cubs'})
        assert out['custom_message'] == 'GO CUBS GO! SEE YOU NEXT SEASON!'

    def test_explicit_custom_message_wins_end_to_end(self):
        """apply_team_defaults() only adjusts the default; the caller
        (off_season_handler / wifi_config_server) applies the user's
        actual value with a subsequent defaults.update(user_config)."""
        defaults = {'custom_message': 'GO CUBS GO! SEE YOU NEXT SEASON!'}
        user = {'team': 'cardinals', 'custom_message': 'Go Birds!'}
        out = apply_team_defaults(defaults, user)
        out.update(user)
        assert out['custom_message'] == 'Go Birds!'


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

    def test_file_paths_use_active_team_assets(self):
        from config_validator import ValidationResult
        v = self._validator_with({'team': 'cardinals'})
        results = v.validate_file_paths()
        assert all(isinstance(r, ValidationResult) for r in results)
        fields = {r.field for r in results}
        assert './cardinals_marquee.png' in fields
        assert './logos/STL.png' in fields
        assert './marquee.png' not in fields
        assert './logos/cubs.png' not in fields
        # Team-agnostic asset is unaffected
        assert './baseball.png' in fields


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


class TestGetActiveNflTeam:
    def test_default_is_bears_when_config_empty(self):
        from teams import get_active_nfl_team
        assert get_active_nfl_team({}).slug == 'bears'

    def test_explicit_bears(self):
        from teams import get_active_nfl_team
        assert get_active_nfl_team({'nfl_team': 'bears'}).slug == 'bears'

    def test_explicit_chiefs(self):
        from teams import get_active_nfl_team
        pack = get_active_nfl_team({'nfl_team': 'chiefs'})
        assert pack.slug == 'chiefs'
        assert pack.abbrev == 'KC'

    def test_unknown_slug_falls_back_to_bears(self):
        from teams import get_active_nfl_team
        assert get_active_nfl_team({'nfl_team': 'packers'}).slug == 'bears'

    def test_none_config_uses_load_user_config(self, monkeypatch):
        import teams
        monkeypatch.setattr(
            teams, 'load_user_config', lambda: {'nfl_team': 'chiefs'})
        from teams import get_active_nfl_team
        assert get_active_nfl_team().slug == 'chiefs'


class TestNflPackValues:
    def test_both_packs_present(self):
        from teams import NFL_TEAMS, DEFAULT_NFL_TEAM_SLUG
        assert set(NFL_TEAMS) == {'bears', 'chiefs'}
        assert DEFAULT_NFL_TEAM_SLUG == 'bears'

    def test_slug_matches_dict_key(self):
        from teams import NFL_TEAMS
        for slug, pack in NFL_TEAMS.items():
            assert pack.slug == slug

    def test_bears_pack_values(self):
        from teams import NFL_TEAMS
        b = NFL_TEAMS['bears']
        assert b.espn_slug == 'chi'
        assert b.abbrev == 'CHI'
        assert b.header_name == 'CHICAGO BEARS'
        assert b.primary_color == (11, 22, 42)
        assert b.accent_color == (200, 56, 3)
        assert b.logo_path == './logos/nfl/CHI.png'
        assert b.news_rss_url == 'https://www.chicagobears.com/rss/news'

    def test_chiefs_pack_values(self):
        from teams import NFL_TEAMS
        c = NFL_TEAMS['chiefs']
        assert c.espn_slug == 'kc'
        assert c.abbrev == 'KC'
        assert c.header_name == 'KANSAS CITY CHIEFS'
        assert c.primary_color == (227, 24, 55)
        assert c.accent_color == (255, 184, 28)
        assert c.logo_path == './logos/nfl/KC.png'
        assert c.news_rss_url == 'https://www.chiefs.com/rss/news'

    def test_chiefs_keywords_sanity(self):
        from teams import NFL_TEAMS
        kw = NFL_TEAMS['chiefs'].news_keywords
        assert 'CHIEFS' in kw
        assert 'ARROWHEAD' in kw
        assert not any('BEARS' in k for k in kw)

    def test_bears_keywords_sanity(self):
        from teams import NFL_TEAMS
        kw = NFL_TEAMS['bears'].news_keywords
        assert 'BEARS' in kw
        assert 'SOLDIER FIELD' in kw
        assert not any('CHIEFS' in k for k in kw)


class TestNonDefaultOffKeysShrink:
    def test_only_clock_remains(self):
        from teams import NON_DEFAULT_OFF_KEYS
        assert NON_DEFAULT_OFF_KEYS == ('enable_clock',)

    def test_cardinals_keeps_bears_content_on(self):
        from teams import apply_team_defaults
        defaults = {'enable_bears': True, 'enable_bears_news': True,
                    'enable_clock': True}
        adjusted = apply_team_defaults(defaults, {'team': 'cardinals'})
        assert adjusted['enable_bears'] is True
        assert adjusted['enable_bears_news'] is True
        assert adjusted['enable_clock'] is False


class TestOffSeasonTeamContent:
    def _handler(self, monkeypatch, team_slug):
        import teams
        monkeypatch.setattr(teams, 'load_user_config',
                            lambda: {'team': team_slug})
        import off_season_handler as osh
        monkeypatch.setattr(osh, 'load_user_config',
                            lambda: {'team': team_slug})
        from unittest.mock import MagicMock
        return osh.OffSeasonHandler(MagicMock())

    def test_cardinals_facts_loaded(self, monkeypatch):
        handler = self._handler(monkeypatch, 'cardinals')
        facts = handler._load_cubs_facts()
        assert len(facts) >= 150
        assert not any('CUBS' in f and 'CARDINALS' not in f
                       for f in facts[:20])

    def test_cardinals_defaults_disable_clock_only(self, monkeypatch):
        handler = self._handler(monkeypatch, 'cardinals')
        assert handler.config['enable_bears'] is True
        assert handler.config['enable_bears_news'] is True
        assert handler.config['enable_clock'] is False

    def test_cubs_defaults_keep_bears(self, monkeypatch):
        handler = self._handler(monkeypatch, 'cubs')
        assert handler.config['enable_bears'] is True


class TestBearsDisplayTheming:
    def _make_display(self, monkeypatch, config):
        from unittest.mock import MagicMock
        import teams
        import bears_display
        monkeypatch.setattr(teams, 'load_user_config', lambda: config)
        return bears_display.BearsDisplay(MagicMock())

    def test_bears_default_theming(self, monkeypatch):
        d = self._make_display(monkeypatch, {})
        assert d.nfl_team.slug == 'bears'
        assert '/teams/chi/schedule' in d.schedule_url
        assert d.PRIMARY == (11, 22, 42)
        assert d.ACCENT == (200, 56, 3)

    def test_chiefs_theming(self, monkeypatch):
        d = self._make_display(monkeypatch, {'nfl_team': 'chiefs'})
        assert d.nfl_team.slug == 'chiefs'
        assert '/teams/kc/schedule' in d.schedule_url
        assert d.PRIMARY == (227, 24, 55)
        assert d.ACCENT == (255, 184, 28)

    def test_win_message_strings(self, monkeypatch):
        from unittest.mock import MagicMock
        for config, expected in (
                ({}, 'BEARS WIN!'),
                ({'nfl_team': 'chiefs'}, 'CHIEFS WIN!')):
            d = self._make_display(monkeypatch, config)
            d.manager = MagicMock()
            d._draw_final_content(
                {'bears_score': '21', 'opp_score': '14',
                 'opponent_abbr': 'GB'}, frame_count=0)
            drawn = [call.args[4] for call in
                     d.manager.draw_text.call_args_list]
            assert expected in drawn


class TestLiveGameRunAnimations:
    """Score animations must work for any active team pack"""

    def _make_handler(self, monkeypatch, slug):
        from unittest.mock import MagicMock
        import teams
        import live_game_handler
        monkeypatch.setattr(teams, 'load_user_config', lambda: {'team': slug})
        monkeypatch.setattr(live_game_handler.time, 'sleep', lambda s: None)
        return live_game_handler.LiveGameHandler(MagicMock())

    def test_team_run_animation_uses_pack_sprite(self, monkeypatch):
        import live_game_handler
        opened = []
        real_open = live_game_handler.Image.open

        def spy_open(path, *args, **kwargs):
            opened.append(str(path))
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr(live_game_handler.Image, 'open', spy_open)
        handler = self._make_handler(monkeypatch, 'cardinals')
        handler.animate_cubs_run()
        assert './logos/cardinals_run.png' in opened
        assert not any('run_scored.png' in p for p in opened)

    def test_team_run_animation_default_cubs_sprite(self, monkeypatch):
        import live_game_handler
        opened = []
        real_open = live_game_handler.Image.open

        def spy_open(path, *args, **kwargs):
            opened.append(str(path))
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr(live_game_handler.Image, 'open', spy_open)
        handler = self._make_handler(monkeypatch, 'cubs')
        handler.animate_cubs_run()
        assert './logos/run_scored.png' in opened

    def test_opponent_run_animation_with_non_cubs_team(self, monkeypatch):
        from PIL import Image as PILImage
        handler = self._make_handler(monkeypatch, 'cardinals')
        # Cardinals board playing the Cubs: opponent logo is CHC
        handler.manager.game_images = {
            'opponent': PILImage.open('./logos/CHC.png')}
        handler.animate_opponent_run()
        assert handler.manager.set_image.call_count == 72


class TestRedZoneAlertColor:
    def _make_display(self, monkeypatch, config):
        from unittest.mock import MagicMock
        import teams
        import bears_display
        monkeypatch.setattr(teams, 'load_user_config', lambda: config)
        return bears_display.BearsDisplay(MagicMock())

    def test_bears_navy_sweater_uses_red(self, monkeypatch):
        d = self._make_display(monkeypatch, {})
        assert d._red_zone_alert_color() == (255, 60, 60)

    def test_chiefs_red_sweater_uses_yellow(self, monkeypatch):
        from scoreboard_config import Colors
        d = self._make_display(monkeypatch, {'nfl_team': 'chiefs'})
        assert d._red_zone_alert_color() == Colors.BRIGHT_YELLOW


class TestGameOverBackground:
    def _make_handler(self, monkeypatch, slug):
        from unittest.mock import MagicMock
        import teams
        import live_game_handler
        monkeypatch.setattr(teams, 'load_user_config', lambda: {'team': slug})
        return live_game_handler.LiveGameHandler(MagicMock())

    def test_cubs_final_screen_keeps_primary_blue(self, monkeypatch):
        handler = self._make_handler(monkeypatch, 'cubs')
        assert handler._game_over_bg_color() == (0, 51, 102)

    def test_cardinals_final_screen_uses_secondary_navy(self, monkeypatch):
        handler = self._make_handler(monkeypatch, 'cardinals')
        assert handler._game_over_bg_color() == (12, 35, 64)

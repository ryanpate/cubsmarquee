"""Regression tests for status routing, logger fallback, RSS timeouts,
weather config reload, spring training rollover, and wpa_supplicant escaping"""

from __future__ import annotations

import logging
from unittest.mock import Mock, patch

import pendulum
import pytest
import requests


# ============================================================================
# Suspended / Cancelled game status routing
# ============================================================================

def _make_scoreboard():
    """Build a CubsScoreboard with mocked collaborators, bypassing __init__"""
    from main import CubsScoreboard

    sb = CubsScoreboard.__new__(CubsScoreboard)
    sb.current_game_index = 0
    sb.manager = Mock()
    sb.state_handler = Mock()
    sb.live_handler = Mock()
    sb.off_season_handler = Mock()
    sb.process_game_cycle = Mock()
    sb._get_display_mode = Mock(return_value='auto')
    return sb


class TestSuspendedCancelledRouting:
    """route_by_status must route Suspended/Cancelled to their displays"""

    def test_suspended_status_routes_to_display_suspended(self) -> None:
        sb = _make_scoreboard()
        game_data = [{'game_type': 'R'}]

        with patch('main.time.sleep'):
            sb.route_by_status(game_data, 12345, 'Suspended: Rain')

        sb.state_handler.display_suspended.assert_called_once_with(
            game_data, 0, None, 12345
        )

    def test_cancelled_status_routes_to_display_cancelled(self) -> None:
        sb = _make_scoreboard()
        game_data = [{'game_type': 'R'}]

        with patch('main.time.sleep'):
            sb.route_by_status(game_data, 12345, 'Cancelled')

        sb.state_handler.display_cancelled.assert_called_once_with(
            game_data, 0, None, 12345
        )

    def test_offseason_mode_finished_game_shows_game_over_screen(self) -> None:
        # Regression: hybrid 'offseason' mode showed the NEXT GAME screen
        # for a game that had already finished instead of the result
        sb = _make_scoreboard()
        sb._get_display_mode = Mock(return_value='offseason')
        game_data = [{'game_type': 'R'}]

        with patch('main.time.sleep'):
            sb.route_by_status(game_data, 12345, 'Game Over')

        sb.live_handler.display_game_over.assert_called_once_with(
            game_data, 0, 12345
        )
        sb.state_handler.display_no_game.assert_not_called()

    def test_offseason_mode_live_challenge_stays_on_live_display(self) -> None:
        sb = _make_scoreboard()
        sb._get_display_mode = Mock(return_value='offseason')
        game_data = [{'game_type': 'R'}]

        with patch('main.time.sleep'):
            sb.route_by_status(game_data, 12345, 'Player challenge')

        sb.live_handler.display_game_on.assert_called_once()
        sb.state_handler.display_no_game.assert_not_called()

    def test_offseason_mode_scheduled_game_still_hybrid_cycles(self) -> None:
        sb = _make_scoreboard()
        sb._get_display_mode = Mock(return_value='offseason')
        game_data = [{'game_type': 'R'}]

        with patch('main.time.sleep'):
            sb.route_by_status(game_data, 12345, 'Scheduled')

        sb.state_handler.display_no_game.assert_called_once_with(
            game_data, 0, cycle_content=True
        )
        sb.off_season_handler._display_rotation_cycle.assert_called_once()

    def test_completed_early_routes_to_game_over(self) -> None:
        sb = _make_scoreboard()
        game_data = [{'game_type': 'R'}]

        with patch('main.time.sleep'):
            sb.route_by_status(game_data, 12345, 'Completed Early: Rain')

        sb.live_handler.display_game_over.assert_called_once_with(
            game_data, 0, 12345
        )

    @pytest.mark.parametrize('status', [
        'Player challenge', 'Manager challenge', 'Umpire review',
    ])
    def test_challenge_and_review_states_route_to_live_display(
        self, status
    ) -> None:
        # Mid-game replay states are still a live game (seen from the real
        # API on 2026-07-08), not an "unknown status"
        sb = _make_scoreboard()
        game_data = [{'game_type': 'R'}]

        with patch('main.time.sleep'):
            sb.route_by_status(game_data, 12345, status)

        sb.live_handler.display_game_on.assert_called_once_with(
            game_data, 0, 12345
        )


# ============================================================================
# Logger fallback on read-only filesystem
# ============================================================================

class TestLoggerReadOnlyFilesystem:
    """setup_logging must not crash when /var/log is unwritable"""

    def test_setup_logging_survives_readonly_filesystem(
        self, tmp_path, monkeypatch
    ) -> None:
        import logger as logger_module

        monkeypatch.chdir(tmp_path)
        with patch.object(logger_module, 'LOG_DIR') as mock_dir:
            # Read-only SD card raises OSError (errno 30), not PermissionError
            mock_dir.mkdir.side_effect = OSError(30, 'Read-only file system')
            log = logger_module.setup_logging()

        assert any(isinstance(h, logging.Handler) for h in log.handlers)
        for handler in log.handlers:
            handler.close()
        log.handlers.clear()


# ============================================================================
# RSS fetches must use a network timeout
# ============================================================================

class TestFetchFeed:
    """rss_fetch.fetch_feed fetches with a timeout and never raises"""

    def test_fetch_feed_passes_timeout_to_requests(self, monkeypatch) -> None:
        import rss_fetch

        captured = {}

        def fake_get(url, timeout=None, **kwargs):
            captured['timeout'] = timeout
            resp = Mock()
            resp.content = (
                b'<?xml version="1.0"?><rss version="2.0"><channel>'
                b'<title>T</title><item><title>Headline</title></item>'
                b'</channel></rss>'
            )
            resp.raise_for_status = Mock()
            return resp

        monkeypatch.setattr(rss_fetch.requests, 'get', fake_get)
        feed = rss_fetch.fetch_feed('https://example.com/rss')

        assert captured['timeout'] is not None and captured['timeout'] > 0
        assert len(feed.entries) == 1
        assert feed.entries[0].title == 'Headline'

    def test_fetch_feed_returns_empty_feed_on_network_error(
        self, monkeypatch
    ) -> None:
        import rss_fetch

        def fake_get(url, timeout=None, **kwargs):
            raise requests.exceptions.ConnectTimeout('timed out')

        monkeypatch.setattr(rss_fetch.requests, 'get', fake_get)
        feed = rss_fetch.fetch_feed('https://example.com/rss')

        assert feed.entries == []


class TestRssCallSitesUseTimeout:
    """News fetchers must go through the timeout-aware fetch, not bare URLs"""

    def _patch_network(self, monkeypatch):
        import rss_fetch

        seen = {}

        def fake_get(url, timeout=None, **kwargs):
            seen[url] = timeout
            raise requests.exceptions.ConnectionError('down')

        monkeypatch.setattr(rss_fetch.requests, 'get', fake_get)
        return seen

    def test_cubs_news_fetch_uses_timeout(self, monkeypatch) -> None:
        import off_season_handler as osh

        seen = self._patch_network(monkeypatch)
        handler = osh.OffSeasonHandler.__new__(osh.OffSeasonHandler)

        result = handler._fetch_cubs_news_rss()

        assert result == []
        assert seen, "expected RSS fetches to go through rss_fetch"
        assert all(t and t > 0 for t in seen.values())

    def test_bears_news_fetch_uses_timeout(self, monkeypatch) -> None:
        import off_season_handler as osh

        seen = self._patch_network(monkeypatch)
        handler = osh.OffSeasonHandler.__new__(osh.OffSeasonHandler)

        result = handler._fetch_bears_news_rss()

        assert result == []
        assert seen, "expected RSS fetches to go through rss_fetch"
        assert all(t and t > 0 for t in seen.values())

    def test_newsmax_fetch_uses_timeout(self, monkeypatch) -> None:
        import newsmax_display as nd

        seen = self._patch_network(monkeypatch)
        display = nd.NewsmaxDisplay.__new__(nd.NewsmaxDisplay)

        result = display._fetch_newsmax_rss()

        assert result == []
        assert seen, "expected RSS fetches to go through rss_fetch"
        assert all(t and t > 0 for t in seen.values())


# ============================================================================
# Weather config added after startup must take effect
# ============================================================================

class TestWeatherConfigReload:
    """The no-weather message loop must notice weather config added later"""

    def _make_handler(self):
        import off_season_handler as osh

        handler = osh.OffSeasonHandler.__new__(osh.OffSeasonHandler)
        handler._should_check_season = Mock(return_value=False)
        handler._check_season_started = Mock(return_value=False)
        handler._display_custom_message = Mock()
        return handler

    def test_message_loop_exits_when_weather_gets_configured(self) -> None:
        handler = self._make_handler()
        # First pass: no weather config. Second pass: user added it via admin.
        handler._load_config = Mock(side_effect=[
            {},
            {'zip_code': '60614', 'weather_api_key': 'abc123'},
        ])
        # Safety net: fail loudly instead of hanging if the loop never exits
        handler._display_custom_message = Mock(
            side_effect=[None, None, RuntimeError('message loop never exited')]
        )

        result = handler._display_message_loop()

        assert result is True
        handler._display_custom_message.assert_called_once()

    def test_message_loop_returns_false_when_season_starts(self) -> None:
        handler = self._make_handler()
        handler._should_check_season = Mock(return_value=True)
        handler._check_season_started = Mock(return_value=True)
        handler._load_config = Mock(return_value={})

        assert handler._display_message_loop() is False

    def test_off_season_content_enters_rotation_after_weather_configured(
        self,
    ) -> None:
        handler = self._make_handler()
        handler.config = {}  # no weather configured at startup
        handler._display_message_loop = Mock(return_value=True)
        handler._load_config = Mock(return_value={
            'zip_code': '60614',
            'weather_api_key': 'abc123',
            'display_mode': 'weather_only',
        })
        # Break out of the infinite rotation loop after the first cycle
        handler._display_weather_cycle = Mock(side_effect=KeyboardInterrupt)

        with pytest.raises(KeyboardInterrupt):
            handler.display_off_season_content()

        handler._display_weather_cycle.assert_called_once()


# ============================================================================
# Spring training countdown rollover
# ============================================================================

class TestSpringTrainingRollover:
    """After Mar 31 the countdown must target next year's spring training"""

    def _display_at(self, monkeypatch, frozen: pendulum.DateTime):
        import spring_training_display as std

        monkeypatch.setattr(
            std.pendulum, 'now', lambda tz=None: frozen
        )
        display = std.SpringTrainingDisplay.__new__(std.SpringTrainingDisplay)
        display._opening_day_cache = None
        display._opening_day_cached_on = None
        display._get_opening_day = lambda: None  # keep tests off the network
        return display

    def test_early_april_counts_down_to_next_year(self, monkeypatch) -> None:
        frozen = pendulum.datetime(2026, 4, 5, tz='America/Chicago')
        display = self._display_at(monkeypatch, frozen)

        assert display._get_spring_training_date().year == 2027
        countdown = display._calculate_countdown()
        assert countdown['days'] > 300

    def test_during_spring_training_counts_current_year(
        self, monkeypatch
    ) -> None:
        frozen = pendulum.datetime(2026, 3, 1, tz='America/Chicago')
        display = self._display_at(monkeypatch, frozen)

        assert display._get_spring_training_date().year == 2026

    def test_january_counts_down_to_current_year(self, monkeypatch) -> None:
        frozen = pendulum.datetime(2026, 1, 15, tz='America/Chicago')
        display = self._display_at(monkeypatch, frozen)

        assert display._get_spring_training_date().year == 2026
        assert display._calculate_countdown()['days'] > 0


# ============================================================================
# wpa_supplicant.conf escaping and credential validation
# ============================================================================

class TestWpaSupplicantEscaping:
    """SSID/password must be escaped/validated before hitting wpa_supplicant"""

    def test_quotes_and_backslashes_are_escaped(self) -> None:
        import wifi_config_server as wcs

        block = wcs.build_wpa_network_block('My "Cool" Net', 'pass"word\\123')

        assert 'ssid="My \\"Cool\\" Net"' in block
        assert 'psk="pass\\"word\\\\123"' in block

    def test_normal_credentials_produce_plain_block(self) -> None:
        import wifi_config_server as wcs

        block = wcs.build_wpa_network_block('HomeWiFi', 'correcthorse')

        assert 'ssid="HomeWiFi"' in block
        assert 'psk="correcthorse"' in block
        assert 'key_mgmt=WPA-PSK' in block

    def test_validate_rejects_control_characters(self) -> None:
        import wifi_config_server as wcs

        assert wcs.validate_wifi_credentials('evil\nssid', 'password123')
        assert wcs.validate_wifi_credentials('Home', 'pass\nword123')

    def test_validate_rejects_bad_password_length(self) -> None:
        import wifi_config_server as wcs

        assert wcs.validate_wifi_credentials('Home', 'short')  # < 8 chars
        assert wcs.validate_wifi_credentials('Home', 'x' * 64)  # > 63 chars

    def test_validate_accepts_normal_credentials(self) -> None:
        import wifi_config_server as wcs

        assert wcs.validate_wifi_credentials('Home WiFi', 'password123') is None

    def test_connect_wifi_rejects_bad_input_without_touching_system(
        self, monkeypatch
    ) -> None:
        import wifi_config_server as wcs

        run_spy = Mock()
        monkeypatch.setattr(wcs.subprocess, 'run', run_spy)
        monkeypatch.setattr(wcs.time, 'sleep', Mock())
        client = wcs.app.test_client()

        resp = client.post('/connect_wifi', json={
            'ssid': 'evil"\nnetwork={',
            'password': 'password123',
        })

        assert resp.get_json()['success'] is False
        run_spy.assert_not_called()


# ============================================================================
# Admin server robustness: atomic saves, timeouts, threading, XSS
# ============================================================================

class TestAtomicConfigSave:
    """save_config must never leave a truncated config.json behind"""

    def test_save_and_reload_roundtrip(self, tmp_path, monkeypatch) -> None:
        import json
        import wifi_config_server as wcs

        cfg = tmp_path / 'config.json'
        monkeypatch.setattr(wcs, 'CONFIG_PATH', str(cfg))

        assert wcs.save_config({'brightness': 80}) is True
        assert json.loads(cfg.read_text())['brightness'] == 80

    def test_failed_save_preserves_existing_config(
        self, tmp_path, monkeypatch
    ) -> None:
        import json
        import wifi_config_server as wcs

        cfg = tmp_path / 'config.json'
        cfg.write_text('{"weather_api_key": "keepme"}')
        monkeypatch.setattr(wcs, 'CONFIG_PATH', str(cfg))

        # json.dump raises mid-write on a non-serializable value
        assert wcs.save_config({'bad': object()}) is False
        assert json.loads(cfg.read_text()) == {'weather_api_key': 'keepme'}


class TestAdminServerRobustness:
    """Blocking calls need timeouts; the server must handle them in parallel"""

    @staticmethod
    def _server_ast():
        import ast
        from pathlib import Path

        source = (Path(__file__).parent.parent / 'wifi_config_server.py')
        return ast.parse(source.read_text())

    def test_all_subprocess_run_calls_have_timeout(self) -> None:
        import ast

        missing = []
        for node in ast.walk(self._server_ast()):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == 'run'
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == 'subprocess'
            ):
                if not any(kw.arg == 'timeout' for kw in node.keywords):
                    missing.append(node.lineno)

        assert missing == [], f'subprocess.run without timeout at lines {missing}'

    def test_flask_app_runs_threaded(self) -> None:
        import ast

        for node in ast.walk(self._server_ast()):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == 'run'
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == 'app'
            ):
                threaded = [
                    kw for kw in node.keywords if kw.arg == 'threaded'
                ]
                assert threaded and threaded[0].value.value is True
                return
        pytest.fail('app.run(...) call not found')

    def test_scan_results_not_built_via_string_interpolation(self) -> None:
        import wifi_config_server as wcs

        # SSIDs must reach the DOM via textContent, never template literals
        assert '${network.ssid}' not in wcs.HTML_TEMPLATE


# ============================================================================
# Weather forecast: bucket by local day, not UTC day
# ============================================================================

class TestForecastTimezone:
    """OWM dt_txt is UTC; evening readings must stay on the local day"""

    def test_evening_utc_rollover_buckets_by_local_day(
        self, monkeypatch
    ) -> None:
        import weather_display as wd

        # 8 PM Central on Wed Jul 8 - UTC has already rolled to Jul 9
        frozen = pendulum.datetime(2026, 7, 8, 20, 0, tz='America/Chicago')
        monkeypatch.setattr(
            wd.pendulum, 'now',
            lambda tz=None: frozen if tz is None else frozen.in_timezone(tz),
        )

        display = wd.WeatherDisplay.__new__(wd.WeatherDisplay)
        display.forecast_data = {'list': [
            # 00:00 UTC Jul 9 == 7 PM Jul 8 local: still today, must be skipped
            {'dt_txt': '2026-07-09 00:00:00',
             'main': {'temp': 99}, 'weather': [{'main': 'Clear'}]},
            # Thursday Jul 9 local afternoon
            {'dt_txt': '2026-07-09 18:00:00',
             'main': {'temp': 80}, 'weather': [{'main': 'Clear'}]},
            {'dt_txt': '2026-07-09 21:00:00',
             'main': {'temp': 84}, 'weather': [{'main': 'Rain'}]},
            # Friday Jul 10 local
            {'dt_txt': '2026-07-10 18:00:00',
             'main': {'temp': 70}, 'weather': [{'main': 'Clouds'}]},
        ]}

        forecasts = display._build_daily_forecasts()

        assert forecasts[0]['day'] == 'THU'
        # The 99-degree reading belongs to today (7 PM local) and must not
        # inflate Thursday's high
        assert forecasts[0]['temp_high'] == 84
        assert forecasts[0]['temp_low'] == 80
        assert forecasts[1]['day'] == 'FRI'
        assert forecasts[1]['temp_high'] == 70


# ============================================================================
# adsb.lol failure isolation
# ============================================================================

class TestAdsbLolRobustness:
    """One bad record or payload must not kill the whole flight segment"""

    def test_fetch_aircraft_skips_malformed_record(self) -> None:
        from adsb_lol_source import fetch_aircraft

        payload = {'ac': [
            # hex explicitly null and no flight/r: crashes .upper() unguarded
            {'hex': None, 'alt_baro': 30000, 'lat': 41.96, 'lon': -87.87,
             'gs': 400, 'seen': 1},
            {'hex': 'a55fa2', 'flight': 'UAL1740 ', 'r': 'N44501',
             't': 'A21N', 'alt_baro': 35000, 'gs': 450.0, 'track': 90.0,
             'lat': 41.968, 'lon': -87.874, 'baro_rate': 0, 'seen': 0.1},
        ]}
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = payload

        with patch('adsb_lol_source.requests.get', return_value=mock_resp):
            flights = fetch_aircraft(
                base_url='https://api.adsb.lol', home_lat=41.95,
                home_lon=-87.65, range_nm=50, min_altitude_ft=500,
            )

        assert len(flights) == 1
        assert flights[0]['callsign'] == 'UAL1740'

    def test_enrich_routes_accepts_http_201(self) -> None:
        # adsb.lol answers the routeset POST with 201, not 200 (seen live
        # on 2026-07-08); a 200-only check silently drops every route
        from adsb_lol_source import enrich_routes

        cache = Mock()
        cache.get.return_value = None
        flights = [{
            'callsign': 'UAL123', 'latitude': 41.9, 'longitude': -87.6,
            'origin_iata': None, 'dest_iata': None, 'airline_code': None,
        }]
        mock_resp = Mock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = [{
            'callsign': 'UAL123', 'plausible': True,
            '_airport_codes_iata': 'ORD-RSW', 'airline_code': 'UAL',
        }]

        with patch('adsb_lol_source.requests.post', return_value=mock_resp):
            enrich_routes('https://api.adsb.lol', flights, cache)

        assert flights[0]['origin_iata'] == 'ORD'
        assert flights[0]['dest_iata'] == 'RSW'
        cache.put_many.assert_called_once()

    def test_enrich_routes_handles_non_list_response(self) -> None:
        from adsb_lol_source import enrich_routes

        cache = Mock()
        cache.get.return_value = None
        flights = [{
            'callsign': 'UAL123', 'latitude': 41.9, 'longitude': -87.6,
            'origin_iata': None, 'dest_iata': None, 'airline_code': None,
        }]
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {'error': 'rate limited'}

        with patch('adsb_lol_source.requests.post', return_value=mock_resp):
            enrich_routes('https://api.adsb.lol', flights, cache)

        assert flights[0]['dest_iata'] is None
        # Don't cache negatives from a garbage payload
        cache.put_many.assert_not_called()

    def test_flight_display_survives_enrichment_failure(
        self, monkeypatch
    ) -> None:
        import flight_display as fd

        display = fd.FlightDisplay.__new__(fd.FlightDisplay)
        display.latitude = 41.9
        display.longitude = -87.6
        display.flight_max_range_nm = 50
        display.route_cache = Mock()

        flight = {'callsign': 'UAL123'}
        monkeypatch.setattr(
            fd, 'adsb_lol_fetch_aircraft', lambda **kwargs: [flight]
        )

        def explode(**kwargs):
            raise RuntimeError('enrichment exploded')

        monkeypatch.setattr(fd, 'adsb_lol_enrich_routes', explode)

        assert display._fetch_from_adsb_lol() is True
        assert display.flight_data == [flight]


# ============================================================================
# Replay challenge / umpire review banner on the live game screen
# ============================================================================

class TestReviewBanner:
    """Challenge/review states must be visible on the live display"""

    def _make_handler(self):
        from live_game_handler import LiveGameHandler

        handler = LiveGameHandler.__new__(LiveGameHandler)
        handler.manager = Mock()
        return handler

    def test_banner_text_for_review_states(self) -> None:
        handler = self._make_handler()

        assert handler._get_review_banner('Player challenge') == 'PLAYER CHALLENGE'
        assert handler._get_review_banner('Manager challenge') == 'MANAGER CHALLENGE'
        assert handler._get_review_banner('Umpire review') == 'UMPIRE REVIEW'

    def test_no_banner_for_normal_play(self) -> None:
        handler = self._make_handler()

        assert handler._get_review_banner('In Progress') is None
        assert handler._get_review_banner('Final') is None

    def test_draw_review_banner_renders_text(self) -> None:
        handler = self._make_handler()

        handler._draw_review_banner('UMPIRE REVIEW')

        # Banner background fills the batter strip
        assert handler.manager.draw_pixel.call_count > 0
        # Text is drawn centered-ish with the banner content
        (font, x, y, color, text), _ = handler.manager.draw_text.call_args
        assert text == 'UMPIRE REVIEW'
        assert 0 <= x <= 96 - len(text) * 5


# ============================================================================
# Efficiency: batched lineup fetch
# ============================================================================

GAME_INFO_FIXTURE = {
    'liveData': {'boxscore': {'teams': {
        'home': {'team': {'name': 'Chicago Cubs'}, 'batters': [1, 2]},
        'away': {'team': {'name': 'Milwaukee Brewers'}, 'batters': [3, 4]},
    }}},
}

PEOPLE_FIXTURE = {'people': [
    {'id': 1, 'lastName': 'Happ', 'primaryPosition': {'abbreviation': 'LF'}},
    {'id': 2, 'lastName': 'Swanson', 'primaryPosition': {'abbreviation': 'SS'}},
    {'id': 3, 'lastName': 'Yelich', 'primaryPosition': {'abbreviation': 'DH'}},
    {'id': 4, 'lastName': 'Chourio', 'primaryPosition': {'abbreviation': 'CF'}},
]}


class TestLineupBatching:
    """get_lineup must fetch all players in one API call, not one per batter"""

    def _get_lineup(self):
        from scoreboard_manager import ScoreboardManager

        calls = []

        def fake_get(endpoint, params):
            calls.append((endpoint, params))
            if endpoint == 'game':
                return GAME_INFO_FIXTURE
            if endpoint == 'people':
                return PEOPLE_FIXTURE
            raise AssertionError(f'unexpected endpoint {endpoint}')

        manager = ScoreboardManager.__new__(ScoreboardManager)
        with patch('scoreboard_manager.statsapi.get', side_effect=fake_get):
            lineup = manager.get_lineup(12345)
        return lineup, calls

    def test_lineup_uses_two_api_calls_total(self) -> None:
        lineup, calls = self._get_lineup()

        assert len(calls) == 2, f'expected 2 API calls, got {len(calls)}'
        people_calls = [c for c in calls if c[0] == 'people']
        assert len(people_calls) == 1
        # All four batter IDs batched into a single comma-separated request
        ids = str(people_calls[0][1]['personIds'])
        assert sorted(ids.split(',')) == ['1', '2', '3', '4']

    def test_lineup_preserves_batting_order_and_content(self) -> None:
        lineup, _ = self._get_lineup()

        assert 'Chicago Cubs - LF:Happ SS:Swanson' in lineup
        assert 'Milwaukee Brewers - DH:Yelich CF:Chourio' in lineup


class TestLineupFetchScope:
    """Don't fetch the (expensive) lineup for statuses that never use it"""

    def test_in_progress_does_not_fetch_lineup(self) -> None:
        sb = _make_scoreboard()
        with patch('main.time.sleep'):
            sb.route_by_status([{'game_type': 'R'}], 12345, 'In Progress')
        sb.manager.get_lineup.assert_not_called()

    def test_warmup_still_fetches_lineup(self) -> None:
        sb = _make_scoreboard()
        with patch('main.time.sleep'):
            sb.route_by_status([{'game_type': 'R'}], 12345, 'Warmup')
        sb.manager.get_lineup.assert_called_once_with(12345)


# ============================================================================
# Efficiency: ranged schedule lookahead with caching
# ============================================================================

class TestScheduleLookahead:
    """No-game-today lookahead: one ranged query, cached, not 14 daily calls"""

    def _make_manager(self):
        from scoreboard_manager import ScoreboardManager

        manager = ScoreboardManager.__new__(ScoreboardManager)
        manager._lookahead_cache = None
        manager._lookahead_cached_at = 0.0
        return manager

    def test_game_today_returns_immediately(self) -> None:
        manager = self._make_manager()
        today_games = [{'game_date': '2026-07-08', 'status': 'Scheduled'}]

        with patch(
            'scoreboard_manager.statsapi.schedule', return_value=today_games
        ) as sched:
            assert manager.get_schedule() == today_games
        assert sched.call_count == 1

    def test_no_game_today_uses_single_ranged_query(self) -> None:
        manager = self._make_manager()
        future = [
            {'game_date': '2026-07-10', 'status': 'Scheduled'},
            {'game_date': '2026-07-12', 'status': 'Scheduled'},
        ]

        def fake_schedule(**kwargs):
            if 'end_date' in kwargs:
                return future
            return []

        with patch(
            'scoreboard_manager.statsapi.schedule', side_effect=fake_schedule
        ) as sched:
            result = manager.get_schedule()

        # Only the next game day is returned (matching old behavior)
        assert result == [future[0]]
        assert sched.call_count == 2, (
            f'expected 2 calls (today + ranged), got {sched.call_count}'
        )

    def test_lookahead_result_is_cached(self) -> None:
        manager = self._make_manager()
        future = [{'game_date': '2026-07-10', 'status': 'Scheduled'}]

        def fake_schedule(**kwargs):
            return future if 'end_date' in kwargs else []

        with patch(
            'scoreboard_manager.statsapi.schedule', side_effect=fake_schedule
        ) as sched:
            first = manager.get_schedule()
            second = manager.get_schedule()

        assert first == second == future
        # 2 calls for the first invocation, only the fresh today-check after
        assert sched.call_count == 3


# ============================================================================
# Efficiency: cached user-config loader
# ============================================================================

class TestCachedConfigLoader:
    """Per-frame config reads must hit a cache, not reparse the file"""

    def test_returns_parsed_config(self, tmp_path, monkeypatch) -> None:
        import json
        import scoreboard_config as sc

        cfg = tmp_path / 'config.json'
        cfg.write_text(json.dumps({'scroll_speed_pga': 7}))
        monkeypatch.setattr(sc, 'CONFIG_FILE_PATH', str(cfg))

        assert sc.load_user_config()['scroll_speed_pga'] == 7

    def test_missing_file_returns_empty_dict(self, monkeypatch) -> None:
        import scoreboard_config as sc

        monkeypatch.setattr(sc, 'CONFIG_FILE_PATH', '/nonexistent/config.json')
        assert sc.load_user_config() == {}

    def test_unchanged_file_is_parsed_only_once(
        self, tmp_path, monkeypatch
    ) -> None:
        import json
        import scoreboard_config as sc

        cfg = tmp_path / 'config.json'
        cfg.write_text(json.dumps({'brightness': 90}))
        monkeypatch.setattr(sc, 'CONFIG_FILE_PATH', str(cfg))

        parses = []
        real_load = json.load
        monkeypatch.setattr(
            sc.json, 'load', lambda f: parses.append(1) or real_load(f)
        )

        for _ in range(5):
            assert sc.load_user_config()['brightness'] == 90
        assert len(parses) == 1

    def test_modified_file_is_reloaded(self, tmp_path, monkeypatch) -> None:
        import json
        import os
        import scoreboard_config as sc

        cfg = tmp_path / 'config.json'
        cfg.write_text(json.dumps({'brightness': 90}))
        monkeypatch.setattr(sc, 'CONFIG_FILE_PATH', str(cfg))

        assert sc.load_user_config()['brightness'] == 90

        cfg.write_text(json.dumps({'brightness': 40}))
        st = os.stat(cfg)
        os.utime(cfg, (st.st_atime, st.st_mtime + 2))  # force mtime change

        assert sc.load_user_config()['brightness'] == 40

    def test_display_modules_use_shared_loader(
        self, tmp_path, monkeypatch
    ) -> None:
        import json
        import scoreboard_config as sc

        cfg = tmp_path / 'config.json'
        cfg.write_text(json.dumps({'scroll_speed_pga': 9, 'zip_code': '60614'}))
        monkeypatch.setattr(sc, 'CONFIG_FILE_PATH', str(cfg))

        import bears_display
        import bible_display
        import flight_display
        import newsmax_display
        import pga_display
        import spring_training_display
        import stock_display

        for module, cls_name in [
            (spring_training_display, 'SpringTrainingDisplay'),
            (bears_display, 'BearsDisplay'),
            (pga_display, 'PGADisplay'),
            (newsmax_display, 'NewsmaxDisplay'),
            (bible_display, 'BibleDisplay'),
            (stock_display, 'StockDisplay'),
            (flight_display, 'FlightDisplay'),
        ]:
            cls = getattr(module, cls_name)
            instance = cls.__new__(cls)
            loaded = instance._load_scroll_config()
            assert loaded.get('scroll_speed_pga') == 9, (
                f'{cls_name}._load_scroll_config did not use the shared loader'
            )

        import off_season_handler as osh
        handler = osh.OffSeasonHandler.__new__(osh.OffSeasonHandler)
        assert handler._load_config()['zip_code'] == '60614'


# ============================================================================
# Efficiency: destination cache saved once per lookup cycle
# ============================================================================

class TestDestinationCacheBatching:
    """The cache file must be written once per cycle, not once per flight"""

    def _make_display(self, monkeypatch):
        import flight_display as fd

        monkeypatch.setattr(fd.time, 'sleep', Mock())
        display = fd.FlightDisplay.__new__(fd.FlightDisplay)
        display.destination_cache = {}
        display.airlabs_api_key = ''
        display._save_destination_cache = Mock()
        return display

    def test_lookup_cycle_saves_cache_once(self, monkeypatch) -> None:
        display = self._make_display(monkeypatch)
        display.flight_data = [
            {'callsign': 'UAL123', 'icao_hex': 'abc001', 'destination': 'UNKNOWN'},
            {'callsign': 'AAL456', 'icao_hex': 'abc002', 'destination': 'UNKNOWN'},
        ]
        display._lookup_destination_airplaneslive = Mock(return_value='ORD')

        display._lookup_destinations()

        assert display._save_destination_cache.call_count == 1

    def test_airplaneslive_lookup_does_not_save_per_hit(
        self, monkeypatch
    ) -> None:
        import flight_display as fd

        display = self._make_display(monkeypatch)
        resp = Mock()
        resp.status_code = 200
        resp.json.return_value = {
            'ac': [{'dst': 'ORD', 'org': 'DEN'}],
        }
        monkeypatch.setattr(fd.requests, 'get', Mock(return_value=resp))

        assert display._lookup_destination_airplaneslive('abc001') == 'ORD'
        display._save_destination_cache.assert_not_called()

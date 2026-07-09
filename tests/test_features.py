"""Tests for auto-dim scheduling and the scoreboard status heartbeat"""

from __future__ import annotations

import json
import time
from unittest.mock import Mock, patch

import pendulum
import pytest


# ============================================================================
# Auto-dim: time window logic
# ============================================================================

class TestDimWindow:
    def _manager(self):
        from scoreboard_manager import ScoreboardManager

        manager = ScoreboardManager.__new__(ScoreboardManager)
        manager.matrix = Mock()
        manager._last_brightness_check = 0.0
        manager._applied_brightness = None
        return manager

    def test_overnight_window_wraps_midnight(self) -> None:
        from scoreboard_manager import ScoreboardManager

        is_dim = ScoreboardManager._is_dim_time
        start, end = 22 * 60, 7 * 60  # 22:00 -> 07:00

        assert is_dim(23 * 60, start, end) is True
        assert is_dim(3 * 60, start, end) is True
        assert is_dim(12 * 60, start, end) is False
        assert is_dim(22 * 60, start, end) is True   # boundary: starts dim
        assert is_dim(7 * 60, start, end) is False   # boundary: ends dim

    def test_same_day_window(self) -> None:
        from scoreboard_manager import ScoreboardManager

        is_dim = ScoreboardManager._is_dim_time
        start, end = 13 * 60, 15 * 60

        assert is_dim(14 * 60, start, end) is True
        assert is_dim(16 * 60, start, end) is False

    def test_equal_start_end_never_dims(self) -> None:
        from scoreboard_manager import ScoreboardManager

        assert ScoreboardManager._is_dim_time(600, 600, 600) is False

    def test_parse_hhmm(self) -> None:
        from scoreboard_manager import ScoreboardManager

        assert ScoreboardManager._parse_hhmm('22:00') == 22 * 60
        assert ScoreboardManager._parse_hhmm('7:30') == 7 * 60 + 30
        with pytest.raises(ValueError):
            ScoreboardManager._parse_hhmm('bedtime')


class TestEffectiveBrightness:
    def _manager(self, config, base=100, now_hour=23):
        import scoreboard_manager as sm

        manager = sm.ScoreboardManager.__new__(sm.ScoreboardManager)
        manager.matrix = Mock()
        manager._last_brightness_check = 0.0
        manager._applied_brightness = None
        manager._load_brightness = Mock(return_value=base)
        self._patches = [
            patch.object(sm, 'load_user_config', return_value=config),
            patch.object(
                sm.pendulum, 'now',
                lambda tz=None: pendulum.datetime(
                    2026, 7, 8, now_hour, 0, tz='America/Chicago'),
            ),
        ]
        for p in self._patches:
            p.start()
        return manager

    def teardown_method(self):
        for p in getattr(self, '_patches', []):
            p.stop()

    DIM_CONFIG = {
        'dim_enabled': True, 'dim_start': '22:00',
        'dim_end': '07:00', 'dim_brightness': 30,
    }

    def test_dim_disabled_returns_base(self) -> None:
        manager = self._manager({}, base=100, now_hour=23)
        assert manager.get_effective_brightness() == 100

    def test_inside_window_returns_dim_value(self) -> None:
        manager = self._manager(self.DIM_CONFIG, base=100, now_hour=23)
        assert manager.get_effective_brightness() == 30

    def test_outside_window_returns_base(self) -> None:
        manager = self._manager(self.DIM_CONFIG, base=100, now_hour=12)
        assert manager.get_effective_brightness() == 100

    def test_dim_never_raises_above_base(self) -> None:
        # Base 20 with dim 30: night must not be brighter than day
        manager = self._manager(self.DIM_CONFIG, base=20, now_hour=23)
        assert manager.get_effective_brightness() == 20

    def test_invalid_dim_time_falls_back_to_base(self) -> None:
        config = dict(self.DIM_CONFIG, dim_start='bedtime')
        manager = self._manager(config, base=100, now_hour=23)
        assert manager.get_effective_brightness() == 100


class TestRuntimeBrightnessApplication:
    def _manager(self):
        from scoreboard_manager import ScoreboardManager

        manager = ScoreboardManager.__new__(ScoreboardManager)
        manager.matrix = Mock()
        manager.canvas = Mock()
        manager._last_brightness_check = 0.0
        manager._applied_brightness = None
        return manager

    def test_update_brightness_sets_matrix(self) -> None:
        manager = self._manager()
        manager.get_effective_brightness = Mock(return_value=40)

        manager.update_brightness()

        assert manager.matrix.brightness == 40

    def test_update_brightness_is_throttled(self) -> None:
        manager = self._manager()
        manager.get_effective_brightness = Mock(return_value=40)

        manager.update_brightness()
        manager.update_brightness()  # immediately again

        assert manager.get_effective_brightness.call_count == 1

    def test_swap_canvas_applies_brightness(self) -> None:
        manager = self._manager()
        manager.update_brightness = Mock()

        manager.swap_canvas()

        manager.update_brightness.assert_called_once()


# ============================================================================
# Auto-dim: admin panel persistence
# ============================================================================

class TestAutoDimAdminConfig:
    def _post_config(self, tmp_path, monkeypatch, payload):
        import wifi_config_server as wcs

        monkeypatch.setattr(wcs, 'CONFIG_PATH', str(tmp_path / 'config.json'))
        client = wcs.app.test_client()
        resp = client.post('/save_config', json=payload)
        assert resp.get_json()['success'] is True
        return json.loads((tmp_path / 'config.json').read_text())

    def test_save_config_persists_dim_settings(
        self, tmp_path, monkeypatch
    ) -> None:
        saved = self._post_config(tmp_path, monkeypatch, {
            'dim_enabled': True, 'dim_start': '21:30',
            'dim_end': '06:00', 'dim_brightness': 25,
        })

        assert saved['dim_enabled'] is True
        assert saved['dim_start'] == '21:30'
        assert saved['dim_end'] == '06:00'
        assert saved['dim_brightness'] == 25

    def test_save_config_sanitizes_bad_dim_values(
        self, tmp_path, monkeypatch
    ) -> None:
        saved = self._post_config(tmp_path, monkeypatch, {
            'dim_enabled': True, 'dim_start': 'bedtime',
            'dim_end': '25:99', 'dim_brightness': 500,
        })

        assert saved['dim_start'] == '22:00'   # default
        assert saved['dim_end'] == '07:00'     # default
        assert saved['dim_brightness'] == 100  # clamped


# ============================================================================
# Scoreboard status heartbeat
# ============================================================================

class TestStatusHeartbeat:
    def test_write_status_heartbeat(self, tmp_path, monkeypatch) -> None:
        import main

        status_file = tmp_path / 'status.json'
        monkeypatch.setattr(main, 'STATUS_FILE', str(status_file))

        main.write_status_heartbeat('In Progress', 'Cubs vs Brewers')

        data = json.loads(status_file.read_text())
        assert data['state'] == 'In Progress'
        assert data['detail'] == 'Cubs vs Brewers'
        assert data['timestamp'] > 0

    def test_heartbeat_write_never_raises(self, monkeypatch) -> None:
        import main

        monkeypatch.setattr(
            main, 'STATUS_FILE', '/nonexistent/dir/status.json')
        main.write_status_heartbeat('In Progress')  # must not raise

    def test_route_by_status_writes_heartbeat(self, monkeypatch) -> None:
        from tests.test_bugfixes import _make_scoreboard
        import main

        writes = []
        monkeypatch.setattr(
            main, 'write_status_heartbeat',
            lambda state, detail='': writes.append(state))

        sb = _make_scoreboard()
        with patch('main.time.sleep'):
            sb.route_by_status([{'game_type': 'R'}], 12345, 'In Progress')

        assert writes == ['In Progress']


class TestScoreboardStatusRoute:
    def _get_status(self, tmp_path, monkeypatch, heartbeat=None):
        import wifi_config_server as wcs

        status_file = tmp_path / 'status.json'
        if heartbeat is not None:
            status_file.write_text(json.dumps(heartbeat))
        monkeypatch.setattr(wcs, 'STATUS_FILE', str(status_file))
        client = wcs.app.test_client()
        resp = client.get('/scoreboard_status')
        assert resp.status_code == 200
        return resp.get_json()

    def test_returns_fresh_heartbeat(self, tmp_path, monkeypatch) -> None:
        data = self._get_status(tmp_path, monkeypatch, {
            'timestamp': time.time(), 'state': 'In Progress',
            'detail': 'Cubs vs Brewers',
        })

        assert data['available'] is True
        assert data['state'] == 'In Progress'
        assert data['stale'] is False

    def test_flags_stale_heartbeat(self, tmp_path, monkeypatch) -> None:
        data = self._get_status(tmp_path, monkeypatch, {
            'timestamp': time.time() - 600, 'state': 'In Progress',
            'detail': '',
        })

        assert data['available'] is True
        assert data['stale'] is True

    def test_handles_missing_heartbeat_file(
        self, tmp_path, monkeypatch
    ) -> None:
        data = self._get_status(tmp_path, monkeypatch, heartbeat=None)

        assert data['available'] is False

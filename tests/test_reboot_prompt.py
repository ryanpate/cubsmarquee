"""Reboot prompt: which saved changes need a reboot, and scheduling one"""

import json

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    import wifi_config_server as wcs
    monkeypatch.setattr(wcs, 'CONFIG_PATH', str(tmp_path / 'config.json'))
    wcs.app.config['TESTING'] = True
    return wcs.app.test_client()


class TestKeyClassification:
    def test_every_default_key_is_classified(self):
        """Adding a config key must force a reboot/live decision.

        Without this, a new key silently defaults to "applies live" and the
        prompt quietly stops being trustworthy.
        """
        import wifi_config_server as wcs
        unclassified = (set(wcs.load_config())
                        - wcs.REBOOT_REQUIRED_KEYS
                        - wcs.APPLIES_LIVE_KEYS)
        assert unclassified == set(), (
            f"unclassified config keys: {sorted(unclassified)}")

    def test_no_key_is_in_both_sets(self):
        import wifi_config_server as wcs
        assert wcs.REBOOT_REQUIRED_KEYS & wcs.APPLIES_LIVE_KEYS == set()

    def test_team_packs_need_a_reboot(self):
        # Handlers cache the pack (colors, logos, pre-generated
        # backgrounds) in __init__, so a live re-read is not enough.
        import wifi_config_server as wcs
        assert 'team' in wcs.REBOOT_REQUIRED_KEYS
        assert 'nfl_team' in wcs.REBOOT_REQUIRED_KEYS

    def test_matrix_hardware_keys_need_a_reboot(self):
        # Applied once when the RGBMatrix is constructed. These are per-Pi
        # keys that never appear in the admin defaults, so they are
        # classified explicitly rather than via load_config().
        import wifi_config_server as wcs
        for key in ('panel_version', 'hardware_mapping', 'gpio_slowdown',
                    'limit_refresh_rate_hz'):
            assert key in wcs.REBOOT_REQUIRED_KEYS

    def test_rotation_toggles_apply_live(self):
        # off_season_handler reloads config every rotation iteration.
        import wifi_config_server as wcs
        for key in ('enable_bears', 'display_mode', 'custom_message',
                    'nfl_preempt_mlb', 'scroll_speed_bears'):
            assert key in wcs.APPLIES_LIVE_KEYS


class TestSaveReportsRebootNeed:
    def test_changing_a_live_key_needs_no_reboot(self, client):
        body = client.post('/save_config',
                           json={'enable_bears': False}).get_json()
        assert body['success']
        assert body['reboot_required'] is False
        assert body['reboot_keys'] == []

    def test_changing_the_team_needs_a_reboot(self, client):
        body = client.post('/save_config',
                           json={'team': 'cardinals'}).get_json()
        assert body['success']
        assert body['reboot_required'] is True
        assert body['reboot_keys'] == ['team']

    def test_saving_the_same_value_needs_no_reboot(self, client):
        # Re-saving an unchanged value must not nag.
        client.post('/save_config', json={'team': 'cardinals'})
        body = client.post('/save_config',
                           json={'team': 'cardinals'}).get_json()
        assert body['reboot_required'] is False

    def test_reports_every_changed_reboot_key(self, client):
        body = client.post('/save_config', json={
            'team': 'cardinals', 'nfl_team': 'chiefs'}).get_json()
        assert body['reboot_required'] is True
        assert body['reboot_keys'] == ['nfl_team', 'team']

    def test_config_is_still_written(self, client, tmp_path):
        client.post('/save_config', json={'team': 'cardinals'})
        saved = json.loads((tmp_path / 'config.json').read_text())
        assert saved['team'] == 'cardinals'


class TestScheduleReboot:
    def test_schedules_a_one_shot_timer(self, client, monkeypatch):
        import wifi_config_server as wcs
        calls = []
        monkeypatch.setattr(wcs.subprocess, 'run',
                            lambda *a, **k: calls.append(a[0]) or _ok())
        body = client.post('/schedule_reboot').get_json()
        assert body['success'] is True
        scheduled = [c for c in calls if 'systemd-run' in c]
        assert scheduled, f"no systemd-run call in {calls}"
        assert any('04:00' in str(part) for part in scheduled[0])

    def test_cancels_a_previously_scheduled_reboot(self, client, monkeypatch):
        # Repeated saves must not stack timers.
        import wifi_config_server as wcs
        calls = []
        monkeypatch.setattr(wcs.subprocess, 'run',
                            lambda *a, **k: calls.append(a[0]) or _ok())
        client.post('/schedule_reboot')
        assert any('stop' in c for c in calls), (
            f"no cancel of a prior timer in {calls}")

    def test_failure_is_reported_not_swallowed(self, client, monkeypatch):
        # A silently-failed schedule is the worst outcome: the user
        # believes the reboot is booked and it never happens.
        import wifi_config_server as wcs

        def boom(*a, **k):
            raise OSError('systemd-run missing')

        monkeypatch.setattr(wcs.subprocess, 'run', boom)
        body = client.post('/schedule_reboot').get_json()
        assert body['success'] is False
        assert 'systemd-run missing' in body['message']


class TestAdminPageWiring:
    def test_page_exposes_the_prompt_and_schedule_call(self, client):
        html = client.get('/admin').data.decode()
        assert 'reboot-prompt' in html
        assert '/schedule_reboot' in html
        assert 'reboot_required' in html


def _ok():
    class _R:
        returncode = 0
        stdout = ''
        stderr = ''
    return _R()

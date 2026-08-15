"""A partial POST to /save_config must not reset settings it omits"""

import json

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    import wifi_config_server as wcs
    monkeypatch.setattr(wcs, 'CONFIG_PATH', str(tmp_path / 'config.json'))
    wcs.app.config['TESTING'] = True
    return wcs.app.test_client()


def _saved(tmp_path):
    return json.loads((tmp_path / 'config.json').read_text())


def _seed(client, **values):
    """Write a starting config through the endpoint itself."""
    client.post('/save_config', json=values)


class TestPartialSavePreservesOmittedKeys:
    def test_toggles_survive_a_post_that_omits_them(self, client, tmp_path):
        _seed(client, enable_bears=False, enable_pga=False,
              enable_clock=False)
        # A caller touching one unrelated field must not re-enable these.
        client.post('/save_config', json={'custom_message': 'HELLO'})
        saved = _saved(tmp_path)
        assert saved['enable_bears'] is False
        assert saved['enable_pga'] is False
        assert saved['enable_clock'] is False
        assert saved['custom_message'] == 'HELLO'

    def test_zip_code_is_not_wiped(self, client, tmp_path):
        # The worst case of this bug: weather silently stops working
        # because the ZIP was blanked by an unrelated save.
        _seed(client, zip_code='62563')
        client.post('/save_config', json={'enable_clock': False})
        assert _saved(tmp_path)['zip_code'] == '62563'

    def test_scroll_speeds_survive(self, client, tmp_path):
        _seed(client, scroll_speed_bears=9, scroll_speed_usatoday=8)
        client.post('/save_config', json={'enable_clock': False})
        saved = _saved(tmp_path)
        assert saved['scroll_speed_bears'] == 9
        assert saved['scroll_speed_usatoday'] == 8

    def test_flight_coordinates_survive(self, client, tmp_path):
        _seed(client, flight_tracking_latitude=39.7495,
              flight_tracking_longitude=-89.5318,
              flight_tracking_address='Rochester IL')
        client.post('/save_config', json={'enable_clock': False})
        saved = _saved(tmp_path)
        assert saved['flight_tracking_latitude'] == 39.7495
        assert saved['flight_tracking_longitude'] == -89.5318
        assert saved['flight_tracking_address'] == 'Rochester IL'

    def test_brightness_and_dim_settings_survive(self, client, tmp_path):
        _seed(client, brightness=40, dim_enabled=True, dim_start='23:30',
              dim_end='06:15', dim_brightness=10)
        client.post('/save_config', json={'enable_clock': False})
        saved = _saved(tmp_path)
        assert saved['brightness'] == 40
        assert saved['dim_enabled'] is True
        assert saved['dim_start'] == '23:30'
        assert saved['dim_end'] == '06:15'
        assert saved['dim_brightness'] == 10

    def test_api_keys_and_urls_survive(self, client, tmp_path):
        _seed(client, weather_api_key='abc123', airlabs_api_key='def456',
              adsb_receiver_url='http://pi:8080', flight_source='piaware',
              flight_max_range_nm=25)
        client.post('/save_config', json={'enable_clock': False})
        saved = _saved(tmp_path)
        assert saved['weather_api_key'] == 'abc123'
        assert saved['airlabs_api_key'] == 'def456'
        assert saved['adsb_receiver_url'] == 'http://pi:8080'
        assert saved['flight_source'] == 'piaware'
        assert saved['flight_max_range_nm'] == 25

    def test_empty_post_changes_nothing(self, client, tmp_path):
        _seed(client, enable_bears=False, zip_code='62563', brightness=40,
              scroll_speed_bears=9, display_mode='no_games')
        before = _saved(tmp_path)
        client.post('/save_config', json={})
        assert _saved(tmp_path) == before


class TestExplicitValuesStillWin:
    def test_an_explicit_false_is_honored(self, client, tmp_path):
        # Preserving omitted keys must not swallow a deliberate False.
        _seed(client, enable_bears=True)
        client.post('/save_config', json={'enable_bears': False})
        assert _saved(tmp_path)['enable_bears'] is False

    def test_an_explicit_empty_string_is_honored(self, client, tmp_path):
        # Clearing a field is a real intent and must not be treated as
        # "omitted" and reverted.
        _seed(client, zip_code='62563')
        client.post('/save_config', json={'zip_code': ''})
        assert _saved(tmp_path)['zip_code'] == ''

    def test_an_explicit_zero_is_honored(self, client, tmp_path):
        _seed(client, scroll_speed_bears=9)
        client.post('/save_config', json={'scroll_speed_bears': 0})
        assert _saved(tmp_path)['scroll_speed_bears'] == 0

    def test_invalid_values_still_fall_back_safely(self, client, tmp_path):
        _seed(client, brightness=40, dim_start='23:30')
        client.post('/save_config',
                    json={'brightness': 'nonsense', 'dim_start': '99:99'})
        saved = _saved(tmp_path)
        # Bad input must not save garbage, and must not block the save.
        assert isinstance(saved['brightness'], int)
        assert saved['dim_start'] == '23:30'


class TestRebootDetectionStillWorks:
    def test_partial_save_does_not_report_a_phantom_reboot(self, client):
        # Preserving the team on a partial POST must not read as a change.
        _seed(client, team='cardinals')
        body = client.post('/save_config',
                           json={'enable_clock': False}).get_json()
        assert body['reboot_required'] is False

    def test_a_real_team_change_still_reports(self, client):
        _seed(client, team='cubs')
        body = client.post('/save_config',
                           json={'team': 'cardinals'}).get_json()
        assert body['reboot_required'] is True
        assert body['reboot_keys'] == ['team']

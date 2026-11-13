"""Admin panel team selection round-trip tests"""

import json

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    import wifi_config_server as wcs
    monkeypatch.setattr(wcs, 'CONFIG_PATH', str(tmp_path / 'config.json'))
    wcs.app.config['TESTING'] = True
    return wcs.app.test_client()


def test_admin_page_offers_team_choices(client):
    html = client.get('/admin').data.decode()
    assert 'name="team"' in html
    assert 'value="cubs"' in html
    assert 'value="cardinals"' in html
    assert '<details' in html


def test_save_config_round_trips_team(client, tmp_path, monkeypatch):
    import wifi_config_server as wcs
    resp = client.post('/save_config', json={'team': 'cardinals'})
    assert resp.get_json()['success']
    saved = json.loads((tmp_path / 'config.json').read_text())
    assert saved['team'] == 'cardinals'


def test_load_config_defaults_team_to_cubs(client, monkeypatch):
    import wifi_config_server as wcs
    assert wcs.load_config()['team'] == 'cubs'


def test_load_config_cardinals_keeps_bears_by_default(
        client, tmp_path, monkeypatch):
    import wifi_config_server as wcs
    (tmp_path / 'config.json').write_text(json.dumps({'team': 'cardinals'}))
    cfg = wcs.load_config()
    assert cfg['enable_bears'] is True
    assert cfg['enable_clock'] is False


def test_team_logo_route(client):
    resp = client.get('/team_logo/cardinals')
    assert resp.status_code == 200
    assert resp.mimetype == 'image/png'
    assert client.get('/team_logo/mets').status_code == 404


def test_admin_page_wires_team_change_listener(client):
    html = client.get('/admin').data.decode()
    # The team-default-message map is injected from teams.py so the page
    # JS can never drift from apply_team_defaults().
    assert 'TEAM_DEFAULT_MESSAGES' in html
    assert 'GO CUBS GO! SEE YOU NEXT SEASON!' in html
    assert 'GO CARDINALS GO! SEE YOU NEXT SEASON!' in html
    assert 'NON_DEFAULT_OFF_KEYS' in html
    # A change listener is wired on the team radios.
    assert "input[name=\"team\"]" in html
    assert "addEventListener('change'" in html


def test_save_config_without_team_key_preserves_existing_team(
        client, tmp_path):
    (tmp_path / 'config.json').write_text(json.dumps({'team': 'cardinals'}))
    resp = client.post('/save_config', json={})
    assert resp.get_json()['success']
    saved = json.loads((tmp_path / 'config.json').read_text())
    assert saved['team'] == 'cardinals'


def test_admin_page_offers_nfl_team_choices(client):
    html = client.get('/admin').data.decode()
    assert 'name="nfl_team"' in html
    assert 'value="bears"' in html
    assert 'value="chiefs"' in html
    assert '/nfl_logo/chiefs' in html


def test_admin_page_non_default_off_keys_is_clock_only(client):
    html = client.get('/admin').data.decode()
    assert 'const NON_DEFAULT_OFF_KEYS = ["enable_clock"];' in html


def test_nfl_logo_route(client):
    resp = client.get('/nfl_logo/chiefs')
    assert resp.status_code == 200
    assert resp.mimetype == 'image/png'
    assert client.get('/nfl_logo/packers').status_code == 404


def test_save_config_round_trips_nfl_team(client):
    resp = client.post('/save_config', json={'nfl_team': 'chiefs'})
    assert resp.status_code == 200
    import wifi_config_server as wcs
    assert wcs.load_config()['nfl_team'] == 'chiefs'


def test_load_config_defaults_nfl_team_to_bears(client):
    import wifi_config_server as wcs
    assert wcs.load_config()['nfl_team'] == 'bears'


def test_save_config_without_nfl_key_preserves_existing(client):
    client.post('/save_config', json={'nfl_team': 'chiefs'})
    resp = client.post('/save_config', json={'custom_message': 'HI'})
    assert resp.status_code == 200
    import wifi_config_server as wcs
    assert wcs.load_config()['nfl_team'] == 'chiefs'


def test_admin_page_relabels_bears_controls(client):
    html = client.get('/admin').data.decode()
    assert 'Enable NFL team game display' in html
    assert 'Enable NFL breaking news display' in html
    assert 'Enable Chicago Bears display' not in html


SAMPLE_IWLIST = '''
          Cell 01 - Address: AA:BB:CC:DD:EE:01
                    Quality=60/70  Signal level=-50 dBm
                    ESSID:"HomeNet"
          Cell 02 - Address: AA:BB:CC:DD:EE:02
                    Quality=35/70  Signal level=-75 dBm
                    ESSID:"Neighbor5G"
          Cell 03 - Address: AA:BB:CC:DD:EE:03
                    Quality=60/70  Signal level=-50 dBm
                    ESSID:"HomeNet"
'''


def test_parse_iwlist_extracts_unique_networks():
    import wifi_config_server as wcs
    networks = wcs._parse_iwlist(SAMPLE_IWLIST)
    assert [n['ssid'] for n in networks] == ['HomeNet', 'Neighbor5G']
    assert '85%' in networks[0]['signal']


def test_scan_falls_back_to_cache_in_hotspot_mode(
        client, tmp_path, monkeypatch):
    """hostapd owns the radio in AP mode - live scans return nothing, so
    the endpoint must serve the scan wifi_manager.sh cached beforehand"""
    import subprocess
    import wifi_config_server as wcs

    cache = tmp_path / 'wifi_scan_cache.txt'
    cache.write_text(SAMPLE_IWLIST)
    monkeypatch.setattr(wcs, 'SCAN_CACHE_PATH', str(cache))

    def busy_scan(*args, **kwargs):
        return subprocess.CompletedProcess(
            args, 240, stdout='', stderr='wlan0    Device or resource busy')

    monkeypatch.setattr(wcs.subprocess, 'run', busy_scan)

    data = client.get('/scan_networks').get_json()
    assert data['success'] and data['cached']
    assert [n['ssid'] for n in data['networks']] == ['HomeNet', 'Neighbor5G']


def test_scan_prefers_live_results(client, tmp_path, monkeypatch):
    import subprocess
    import wifi_config_server as wcs

    cache = tmp_path / 'wifi_scan_cache.txt'
    cache.write_text(SAMPLE_IWLIST)
    monkeypatch.setattr(wcs, 'SCAN_CACHE_PATH', str(cache))

    live = SAMPLE_IWLIST.replace('HomeNet', 'LiveNet')

    def live_scan(*args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout=live, stderr='')

    monkeypatch.setattr(wcs.subprocess, 'run', live_scan)

    data = client.get('/scan_networks').get_json()
    assert data['success'] and not data['cached']
    assert [n['ssid'] for n in data['networks']] == ['LiveNet', 'Neighbor5G']


def test_load_config_defaults_usatoday(client, monkeypatch):
    import wifi_config_server as wcs
    cfg = wcs.load_config()
    assert cfg['enable_usatoday'] is True
    assert cfg['scroll_speed_usatoday'] == 5


def test_admin_page_has_usatoday_controls(client):
    resp = client.get('/admin')
    assert b'enable_usatoday' in resp.data
    assert b'scroll_speed_usatoday' in resp.data


def test_save_config_round_trips_usatoday(client, tmp_path, monkeypatch):
    import json
    resp = client.post('/save_config', json={
        'enable_usatoday': False, 'scroll_speed_usatoday': 8})
    assert resp.get_json()['success']
    saved = json.loads((tmp_path / 'config.json').read_text())
    assert saved['enable_usatoday'] is False
    assert saved['scroll_speed_usatoday'] == 8


def test_admin_page_offers_nfl_preempt_toggle(client):
    html = client.get('/admin').data.decode()
    assert 'id="nfl_preempt_mlb"' in html


def test_save_config_round_trips_nfl_preempt(client, tmp_path):
    resp = client.post('/save_config', json={'nfl_preempt_mlb': True})
    assert resp.get_json()['success']
    saved = json.loads((tmp_path / 'config.json').read_text())
    assert saved['nfl_preempt_mlb'] is True


def test_nfl_preempt_defaults_to_off(client):
    import wifi_config_server as wcs
    assert wcs.load_config()['nfl_preempt_mlb'] is False


def _nm_run(up_returncode):
    """Fake subprocess.run for _connect_wifi_nm; records each nmcli call."""
    from unittest.mock import MagicMock
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        rc = up_returncode if ('up' in cmd and 'marquee-hotspot' not in cmd) else 0
        return MagicMock(returncode=rc, stdout='', stderr='Secrets were required')
    return run, calls


def test_nm_connect_failure_brings_the_hotspot_back(client, monkeypatch):
    # A mistyped password must not strand the unit with no hotspot and no WiFi
    import wifi_config_server as wcs
    run, calls = _nm_run(up_returncode=4)
    monkeypatch.setattr(wcs.subprocess, 'run', run)
    with wcs.app.test_request_context():
        wcs._connect_wifi_nm('Home', 'wrongpass')
    assert calls[-1][-2:] == ['up', 'marquee-hotspot']


def test_nm_connect_success_leaves_the_hotspot_down(client, monkeypatch):
    import wifi_config_server as wcs
    run, calls = _nm_run(up_returncode=0)
    monkeypatch.setattr(wcs.subprocess, 'run', run)
    with wcs.app.test_request_context():
        wcs._connect_wifi_nm('Home', 'rightpass')
    assert not any(c[-2:] == ['up', 'marquee-hotspot'] for c in calls)


def test_admin_page_offers_college_basketball_controls(client):
    html = client.get('/admin').get_data(as_text=True)
    assert 'name="ncaab_team"' in html
    assert 'value="illini"' in html
    assert '/ncaab_logo/illini' in html
    for key in ('enable_ncaab', 'enable_ncaab_rankings',
                'enable_ncaab_standings', 'enable_ncaab_news',
                'enable_ncaab_facts', 'scroll_speed_ncaab_news',
                'scroll_speed_ncaab_facts'):
        assert f'id="{key}"' in html, key


def test_ncaab_logo_route(client):
    resp = client.get('/ncaab_logo/illini')
    assert resp.status_code == 200
    assert resp.mimetype == 'image/png'
    assert client.get('/ncaab_logo/duke').status_code == 404


def test_college_basketball_settings_default_on_and_round_trip(client):
    import wifi_config_server as wcs
    cfg = wcs.load_config()
    assert cfg['ncaab_team'] == 'illini'
    assert cfg['enable_ncaab'] is True
    assert cfg['enable_ncaab_rankings'] is True

    resp = client.post('/save_config', json={
        'enable_ncaab_facts': False, 'scroll_speed_ncaab_news': 8})
    assert resp.get_json()['success'] is True
    saved = wcs.load_config()
    assert saved['enable_ncaab_facts'] is False
    assert saved['scroll_speed_ncaab_news'] == 8
    assert saved['enable_ncaab'] is True  # untouched keys keep their value

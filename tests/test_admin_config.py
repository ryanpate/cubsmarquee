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

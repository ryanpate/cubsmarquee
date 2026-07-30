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

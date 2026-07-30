"""Open-Meteo weather source: WMO mapping and OWM-shape adaptation"""

from __future__ import annotations

import pendulum


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _install_fake_openmeteo(monkeypatch, current_code=61):
    import weather_display as wd
    now = pendulum.now('UTC').start_of('hour')
    geo_payload = {'results': [
        {'latitude': 39.75, 'longitude': -89.53, 'name': 'Rochester'}]}
    forecast_payload = {
        'current': {'temperature_2m': 82.1, 'apparent_temperature': 85.0,
                    'relative_humidity_2m': 50, 'weather_code': current_code},
        'daily': {'sunrise': [now.int_timestamp],
                  'sunset': [now.add(hours=14).int_timestamp]},
        'hourly': {
            'time': [now.add(hours=i).int_timestamp for i in range(120)],
            'temperature_2m': [60 + (i % 24) for i in range(120)],
            'weather_code': [0] * 120,
        },
    }
    calls = []

    def fake_request(url, timeout=10):
        calls.append(url)
        return FakeResponse(
            geo_payload if 'geocoding' in url else forecast_payload)

    monkeypatch.setattr(wd, 'retry_http_request', fake_request)
    return calls


def _make_display(config):
    import weather_display as wd
    d = wd.WeatherDisplay.__new__(wd.WeatherDisplay)
    d._geo = None
    d.weather_data = None
    d.forecast_data = None
    d.last_update = None
    d._load_config = lambda: config
    return d


class TestWmoMapping:
    def test_known_codes(self):
        from weather_display import wmo_to_condition
        assert wmo_to_condition(0)[0] == 'Clear'
        assert wmo_to_condition(3)[0] == 'Clouds'
        assert wmo_to_condition(45)[0] == 'Mist'
        assert wmo_to_condition(55)[0] == 'Drizzle'
        assert wmo_to_condition(65)[0] == 'Rain'
        assert wmo_to_condition(75)[0] == 'Snow'
        assert wmo_to_condition(85)[0] == 'Snow'
        assert wmo_to_condition(95)[0] == 'Thunderstorm'

    def test_unknown_code_degrades_to_clouds(self):
        from weather_display import wmo_to_condition
        condition, description = wmo_to_condition(42)
        assert condition == 'Clouds'
        assert '42' in description


class TestOpenMeteoFetch:
    def test_fetch_requires_only_zip_no_api_key(self, monkeypatch):
        calls = _install_fake_openmeteo(monkeypatch)
        d = _make_display({'zip_code': '62563'})
        assert d._fetch_weather() is True
        assert 'geocoding-api.open-meteo.com' in calls[0]
        assert 'api.open-meteo.com' in calls[1]
        assert 'appid' not in calls[1]

    def test_unconfigured_without_zip(self, monkeypatch):
        _install_fake_openmeteo(monkeypatch)
        d = _make_display({'weather_api_key': 'abc123'})
        assert d._fetch_weather() is False

    def test_adapted_shapes_feed_the_drawing_code(self, monkeypatch):
        _install_fake_openmeteo(monkeypatch, current_code=61)
        d = _make_display({'zip_code': '62563'})
        assert d._fetch_weather() is True

        w = d.weather_data
        assert w['name'] == 'Rochester'
        assert w['weather'][0]['main'] == 'Rain'
        assert w['main']['temp'] == 82.1
        assert w['main']['feels_like'] == 85.0
        assert w['main']['humidity'] == 50
        assert w['sys']['sunrise'] < w['sys']['sunset']

        item = d.forecast_data['list'][0]
        assert set(item) == {'dt_txt', 'main', 'weather'}

        # the real daily aggregator consumes the adapted list
        forecasts = d._build_daily_forecasts()
        assert len(forecasts) == 3
        for f in forecasts:
            assert f['condition'] == 'Clear'
            assert f['temp_high'] >= f['temp_low']

    def test_geocode_cached_across_fetches(self, monkeypatch):
        calls = _install_fake_openmeteo(monkeypatch)
        d = _make_display({'zip_code': '62563'})
        assert d._fetch_weather() is True
        assert d._fetch_weather() is True
        geocode_calls = [c for c in calls if 'geocoding' in c]
        assert len(geocode_calls) == 1

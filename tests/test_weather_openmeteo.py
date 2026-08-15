"""Open-Meteo weather source: WMO mapping and OWM-shape adaptation"""

from __future__ import annotations

import pendulum


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _radar_tile(color):
    """A 256x256 PNG whose every pixel is `color`, as RainViewer serves."""
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGBA', (256, 256), color).save(buf, format='PNG')
    return buf.getvalue()


class FakeBytesResponse:
    def __init__(self, payload):
        self.content = payload


def _install_fake_openmeteo(monkeypatch, current_code=61, present_weather=(),
                            alerts=(), station='KSPI', nws_down=False,
                            radar=(0, 0, 0, 0), radar_down=False,
                            thunder_at=()):
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

    def fake_request(url, timeout=10, headers=None):
        calls.append(url)
        if 'geocoding' in url:
            return FakeResponse(geo_payload)
        if 'open-meteo' in url:
            return FakeResponse(forecast_payload)
        if nws_down:
            raise RuntimeError('api.weather.gov unreachable')
        if '/points/' in url:
            return FakeResponse({'properties': {
                'observationStations':
                    'https://api.weather.gov/gridpoints/ILX/52,54/stations'}})
        if url.endswith('/stations'):
            # nearest station first, then any thunder stations placed at a
            # given distance due east (0.0182 deg lon ~= 1 mile here)
            features = [{'properties': {'stationIdentifier': station},
                         'geometry': {'coordinates': [-89.53, 39.75]}}]
            for i, miles in enumerate(thunder_at):
                features.append({
                    'properties': {'stationIdentifier': f'KT{i}'},
                    'geometry': {'coordinates': [-89.53 + miles / 53.3, 39.75]}})
            return FakeResponse({'features': features})
        if 'observations' in url:
            if '/KT' in url:
                return FakeResponse({'properties': {
                    'presentWeather': _metar('thunderstorms')}})
            return FakeResponse({'properties': {
                'presentWeather': list(present_weather)}})
        if 'alerts' in url:
            return FakeResponse({'features': [
                {'properties': {'event': e}} for e in alerts]})
        # order matters: the tile host is itself a rainviewer.com domain
        if 'tilecache' in url:
            return FakeBytesResponse(_radar_tile(radar))
        if 'rainviewer' in url:
            if radar_down:
                raise RuntimeError('rainviewer unreachable')
            return FakeResponse({'host': 'https://tilecache.rainviewer.com',
                                 'radar': {'past': [
                                     {'time': 1, 'path': '/v2/radar/abc'}]}})
        raise AssertionError(f'unexpected request: {url}')

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
    d._station = None
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


def _metar(*tokens):
    return [{'intensity': None, 'modifier': None, 'weather': t,
             'rawString': t} for t in tokens]


class TestMetarMapping:
    def test_precipitation_outranks_obscuration(self):
        from weather_display import metar_to_condition
        # KDEC 151215Z reported "+RA BR" -- rain matters, mist doesn't
        assert metar_to_condition(_metar('rain', 'fog_mist'))[0] == 'Rain'

    def test_thunderstorm_outranks_its_own_rain(self):
        from weather_display import metar_to_condition
        assert metar_to_condition(
            _metar('thunderstorms', 'rain', 'fog_mist'))[0] == 'Thunderstorm'

    def test_maps_to_the_vocabulary_the_drawing_code_knows(self):
        from weather_display import metar_to_condition
        assert metar_to_condition(_metar('drizzle'))[0] == 'Drizzle'
        assert metar_to_condition(_metar('snow'))[0] == 'Snow'
        assert metar_to_condition(_metar('freezing_rain'))[0] == 'Rain'
        assert metar_to_condition(_metar('fog_mist'))[0] == 'Mist'
        assert metar_to_condition(_metar('haze'))[0] == 'Haze'

    def test_no_present_weather_is_not_a_condition(self):
        from weather_display import metar_to_condition
        # A clear or merely cloudy sky reports no present weather at all;
        # the sky-cover question is left to the forecast source.
        assert metar_to_condition([]) is None

    def test_unrecognized_token_is_not_a_condition(self):
        from weather_display import metar_to_condition
        assert metar_to_condition(_metar('volcanic_ash')) is None


class TestObservedConditionOverride:
    def test_observation_overrides_a_model_that_missed_the_storm(
            self, monkeypatch):
        # The reported bug: Open-Meteo said code 3 (overcast) while the
        # nearest station was reporting a thunderstorm.
        _install_fake_openmeteo(
            monkeypatch, current_code=3,
            present_weather=_metar('thunderstorms', 'rain'))
        d = _make_display({'zip_code': '62563'})
        assert d._fetch_weather() is True
        assert d.weather_data['weather'][0]['main'] == 'Thunderstorm'

    def test_temperature_still_comes_from_open_meteo(self, monkeypatch):
        _install_fake_openmeteo(monkeypatch, current_code=3,
                                present_weather=_metar('rain'))
        d = _make_display({'zip_code': '62563'})
        assert d._fetch_weather() is True
        assert d.weather_data['main']['temp'] == 82.1
        assert d.weather_data['main']['feels_like'] == 85.0

    def test_quiet_observation_leaves_the_forecast_condition_alone(
            self, monkeypatch):
        _install_fake_openmeteo(monkeypatch, current_code=3,
                                present_weather=[])
        d = _make_display({'zip_code': '62563'})
        assert d._fetch_weather() is True
        assert d.weather_data['weather'][0]['main'] == 'Clouds'

    def test_unreachable_nws_falls_back_to_open_meteo(self, monkeypatch):
        _install_fake_openmeteo(monkeypatch, current_code=61, nws_down=True)
        d = _make_display({'zip_code': '62563'})
        assert d._fetch_weather() is True
        assert d.weather_data['weather'][0]['main'] == 'Rain'

    def test_station_lookup_cached_across_fetches(self, monkeypatch):
        calls = _install_fake_openmeteo(monkeypatch,
                                        present_weather=_metar('rain'))
        d = _make_display({'zip_code': '62563'})
        assert d._fetch_weather() is True
        assert d._fetch_weather() is True
        assert len([c for c in calls if '/points/' in c]) == 1


class TestSevereAlertOverride:
    def test_warning_forces_a_storm_the_station_cannot_see(self, monkeypatch):
        # Rochester sits between stations; a warning covering the point is
        # better evidence than a calm ob 8 miles away.
        _install_fake_openmeteo(monkeypatch, current_code=3,
                                present_weather=[],
                                alerts=['Severe Thunderstorm Warning'])
        d = _make_display({'zip_code': '62563'})
        assert d._fetch_weather() is True
        assert d.weather_data['weather'][0]['main'] == 'Thunderstorm'

    def test_watch_does_not_force_a_storm(self, monkeypatch):
        # A watch means conditions are favorable, not that it is storming.
        _install_fake_openmeteo(monkeypatch, current_code=3,
                                present_weather=[],
                                alerts=['Severe Thunderstorm Watch'])
        d = _make_display({'zip_code': '62563'})
        assert d._fetch_weather() is True
        assert d.weather_data['weather'][0]['main'] == 'Clouds'

    def test_unrelated_warning_does_not_force_a_storm(self, monkeypatch):
        _install_fake_openmeteo(monkeypatch, current_code=3,
                                present_weather=[],
                                alerts=['Heat Advisory', 'Flood Warning'])
        d = _make_display({'zip_code': '62563'})
        assert d._fetch_weather() is True
        assert d.weather_data['weather'][0]['main'] == 'Clouds'


class TestRadarTileMath:
    def test_rochester_lands_on_the_verified_tile_and_pixel(self):
        from weather_display import radar_tile_xy
        # Verified against live RainViewer tiles on 2026-08-15: this tile
        # and pixel is the one showing the cell over the house.
        assert radar_tile_xy(39.7495, -89.5318, 7) == (32, 48, 42, 146)

    def test_zoom_changes_the_tile(self):
        from weather_display import radar_tile_xy
        assert radar_tile_xy(39.7495, -89.5318, 5)[:2] == (8, 12)


class TestRadarPalette:
    def test_no_echo_is_no_opinion(self):
        from weather_display import radar_pixel_to_condition
        assert radar_pixel_to_condition((0, 0, 0, 0)) is None

    def test_faint_smoothing_halo_is_not_rain(self):
        from weather_display import radar_pixel_to_condition
        # RainViewer feathers a cell's edge with low-alpha pixels; counting
        # those as rain would report precipitation next to every shower.
        assert radar_pixel_to_condition((99, 97, 89, 20)) is None

    def test_blue_ramp_is_light_precipitation(self):
        from weather_display import radar_pixel_to_condition
        assert radar_pixel_to_condition((0, 71, 104, 255))[0] == 'Drizzle'
        assert radar_pixel_to_condition((136, 221, 238, 255))[0] == 'Drizzle'

    def test_yellow_through_red_is_rain(self):
        from weather_display import radar_pixel_to_condition
        assert radar_pixel_to_condition((255, 238, 0, 255))[0] == 'Rain'
        # the exact orange measured over the house during the storm
        assert radar_pixel_to_condition((255, 149, 0, 255))[0] == 'Rain'
        assert radar_pixel_to_condition((255, 68, 0, 255))[0] == 'Rain'
        assert radar_pixel_to_condition((93, 0, 0, 255))[0] == 'Rain'

    def test_magenta_is_snow(self):
        from weather_display import radar_pixel_to_condition
        assert radar_pixel_to_condition((255, 139, 255, 255))[0] == 'Snow'


class TestRadarOverride:
    def test_radar_beats_a_station_that_cannot_see_the_cell(
            self, monkeypatch):
        # The reported bug: KSPI 10 miles west read "Cloudy" while the
        # radar pixel over the house was orange.
        _install_fake_openmeteo(monkeypatch, current_code=3,
                                present_weather=[],
                                radar=(255, 149, 0, 255))
        d = _make_display({'zip_code': '62563'})
        assert d._fetch_weather() is True
        assert d.weather_data['weather'][0]['main'] == 'Rain'

    def test_clear_radar_leaves_the_station_report_alone(self, monkeypatch):
        # Radar cannot see fog, so a dry pixel must not erase it.
        _install_fake_openmeteo(monkeypatch, current_code=3,
                                present_weather=_metar('fog_mist'),
                                radar=(0, 0, 0, 0))
        d = _make_display({'zip_code': '62563'})
        assert d._fetch_weather() is True
        assert d.weather_data['weather'][0]['main'] == 'Mist'

    def test_unreachable_radar_falls_back_to_the_station(self, monkeypatch):
        _install_fake_openmeteo(monkeypatch, current_code=3,
                                present_weather=_metar('rain'),
                                radar_down=True)
        d = _make_display({'zip_code': '62563'})
        assert d._fetch_weather() is True
        assert d.weather_data['weather'][0]['main'] == 'Rain'


class TestThunderNearby:
    def test_thunder_within_range_upgrades_rain_to_storm(self, monkeypatch):
        # KSPI silent, but KAAA at 30mi reported thunderstorms.
        _install_fake_openmeteo(monkeypatch, current_code=3,
                                present_weather=[],
                                radar=(255, 149, 0, 255),
                                thunder_at=(30.0,))
        d = _make_display({'zip_code': '62563'})
        assert d._fetch_weather() is True
        assert d.weather_data['weather'][0]['main'] == 'Thunderstorm'

    def test_distant_thunder_is_ignored(self, monkeypatch):
        _install_fake_openmeteo(monkeypatch, current_code=3,
                                present_weather=[],
                                radar=(255, 149, 0, 255),
                                thunder_at=(120.0,))
        d = _make_display({'zip_code': '62563'})
        assert d._fetch_weather() is True
        assert d.weather_data['weather'][0]['main'] == 'Rain'

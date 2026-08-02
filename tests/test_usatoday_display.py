"""USA Today display: feed formatting, caching guards, timeout usage"""

from __future__ import annotations

import types
from unittest.mock import Mock


def _display():
    import usatoday_display as ud
    return ud.UsaTodayDisplay.__new__(ud.UsaTodayDisplay)


def _entry(title, summary=''):
    e = types.SimpleNamespace()
    e.title = title
    if summary:
        e.summary = summary
    return e


def _patch_feed(monkeypatch, entries, bozo=False):
    import usatoday_display as ud
    feed = types.SimpleNamespace(bozo=bozo, entries=entries)
    calls = {}

    def fake_fetch(url):
        calls['url'] = url
        return feed

    monkeypatch.setattr(ud, 'fetch_feed', fake_fetch)
    return calls


class TestUsaTodayFetch:
    def test_headlines_uppercased(self, monkeypatch):
        _patch_feed(monkeypatch, [_entry('Storm slams Florida coast')])
        items = _display()._fetch_usatoday_rss()
        assert items == ['STORM SLAMS FLORIDA COAST']

    def test_fetches_google_news_usatoday_feed(self, monkeypatch):
        calls = _patch_feed(monkeypatch, [_entry('A headline')])
        _display()._fetch_usatoday_rss()
        assert calls['url'] == (
            'https://news.google.com/rss/search?q=site:usatoday.com+when:1d'
            '&hl=en-US&gl=US&ceid=US:en')

    def test_google_news_source_suffix_stripped(self, monkeypatch):
        _patch_feed(monkeypatch, [
            _entry('Storm slams Florida coast - USA Today')])
        items = _display()._fetch_usatoday_rss()
        assert items == ['STORM SLAMS FLORIDA COAST']

    def test_google_news_sports_suffix_stripped(self, monkeypatch):
        _patch_feed(monkeypatch, [_entry('Bears win opener - USA TODAY Sports')])
        items = _display()._fetch_usatoday_rss()
        assert items == ['BEARS WIN OPENER']

    def test_summary_ignored(self, monkeypatch):
        _patch_feed(monkeypatch, [_entry(
            'Court rules - USA Today',
            '<a href="https://example.com/a">Related story</a>'
            '<a href="https://example.com/b">Another related link</a>')])
        items = _display()._fetch_usatoday_rss()
        assert items == ['COURT RULES']

    def test_duplicate_headlines_dropped(self, monkeypatch):
        _patch_feed(monkeypatch, [
            _entry('Same breaking story about the election tonight'),
            _entry('Same breaking story about the election tonight'),
        ])
        assert len(_display()._fetch_usatoday_rss()) == 1

    def test_capped_at_twelve_items(self, monkeypatch):
        _patch_feed(monkeypatch, [
            _entry(f'Unique headline number {i} with words') for i in range(20)])
        assert len(_display()._fetch_usatoday_rss()) == 12

    def test_bozo_feed_with_no_entries_returns_empty(self, monkeypatch):
        _patch_feed(monkeypatch, [], bozo=True)
        assert _display()._fetch_usatoday_rss() == []


class TestUsaTodayCache:
    def test_empty_cache_triggers_update(self):
        d = _display()
        d.usatoday_news = None
        d.last_news_update = None
        assert d._should_update_news() is True

    def test_fresh_cache_skips_update(self, monkeypatch):
        import time
        d = _display()
        d.usatoday_news = ['SOMETHING']
        d.news_update_interval = 1800
        d.last_news_update = time.time()
        assert d._should_update_news() is False


def test_usatoday_fetch_uses_timeout(monkeypatch):
    """Network goes through rss_fetch (timeout-enforced), like Newsmax"""
    import requests

    seen = {}
    real_get = requests.get

    def spy_get(url, *args, **kwargs):
        seen[url] = kwargs.get('timeout')
        raise requests.exceptions.ConnectionError('offline test')

    monkeypatch.setattr(requests, 'get', spy_get)
    import usatoday_display as ud
    display = ud.UsaTodayDisplay.__new__(ud.UsaTodayDisplay)

    result = display._fetch_usatoday_rss()

    assert result == []
    assert seen, 'expected RSS fetches to go through rss_fetch'
    assert all(t and t > 0 for t in seen.values())


def test_logo_asset_fits_header():
    """usatoday.png must fit the 96px header band (Newsmax-style layout)"""
    import os
    from PIL import Image
    path = os.path.join(os.path.dirname(__file__), '..', 'usatoday.png')
    assert os.path.exists(path), 'run tools/gen_usatoday_logo.py'
    img = Image.open(path)
    assert img.mode == 'RGBA'
    assert img.height == 14
    assert img.width <= 88


class TestRotationIntegration:
    def test_off_season_handler_defaults_enable_usatoday(self):
        import off_season_handler as osh
        import inspect
        src = inspect.getsource(osh.OffSeasonHandler._load_config)
        assert "'enable_usatoday': True" in src

    def test_rotation_schedule_has_usatoday_slot(self):
        import off_season_handler as osh
        import inspect
        src = inspect.getsource(osh.OffSeasonHandler.__init__)
        assert "'usatoday'" in src

    def test_rotation_calls_usatoday_display(self):
        import off_season_handler as osh
        import inspect
        src = inspect.getsource(osh.OffSeasonHandler)
        assert 'display_usatoday_news' in src
        assert "self.config.get('enable_usatoday', True)" in src

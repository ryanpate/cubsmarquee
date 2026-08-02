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
    def test_headlines_prefixed_and_uppercased(self, monkeypatch):
        _patch_feed(monkeypatch, [_entry('Storm slams Florida coast')])
        items = _display()._fetch_usatoday_rss()
        assert items == ['USA TODAY: STORM SLAMS FLORIDA COAST']

    def test_fetches_top_stories_feed(self, monkeypatch):
        calls = _patch_feed(monkeypatch, [_entry('A headline')])
        _display()._fetch_usatoday_rss()
        assert calls['url'] == (
            'http://rssfeeds.usatoday.com/usatoday-NewsTopStories')

    def test_summary_appended_when_it_adds_information(self, monkeypatch):
        _patch_feed(monkeypatch, [_entry(
            'Fed holds rates',
            'Central bank officials voted to keep interest rates steady '
            'citing cooling inflation data across sectors. More text here.')])
        items = _display()._fetch_usatoday_rss()
        assert len(items) == 1
        assert items[0].startswith('USA TODAY: FED HOLDS RATES - ')
        assert 'COOLING INFLATION' in items[0]

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

    def test_html_stripped_from_summaries(self, monkeypatch):
        _patch_feed(monkeypatch, [_entry(
            'Court rules',
            '<p>The&nbsp;justices issued a <b>major</b> opinion on the '
            'landmark case that reshapes federal policy nationwide.</p>')])
        items = _display()._fetch_usatoday_rss()
        assert '<' not in items[0] and '&NBSP;' not in items[0]

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
        d.usatoday_news = ['USA TODAY: SOMETHING']
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

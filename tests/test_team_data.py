"""Schema tests for per-team data files"""

import json
import re

import pytest

from teams import TEAMS


def _load(path):
    with open(path) as f:
        return json.load(f)


@pytest.mark.parametrize('slug', sorted(TEAMS))
class TestFactsFiles:
    def test_facts_parse_and_schema(self, slug):
        data = _load(f'./{TEAMS[slug].facts_basename}')
        assert isinstance(data['facts'], list)
        assert len(data['facts']) >= 150
        for fact in data['facts']:
            assert isinstance(fact, str) and fact.strip()

    def test_facts_display_safe(self, slug):
        # LED fonts are uppercase-friendly ASCII; keep facts scrollable.
        # The degree sign (°) is a real exception already present in the
        # Cubs data (weather-flavored facts) and supported by the BDF fonts.
        for fact in _load(f'./{TEAMS[slug].facts_basename}')['facts']:
            assert fact == fact.upper()
            assert all(ord(c) < 128 or c == '\N{DEGREE SIGN}' for c in fact)


@pytest.mark.parametrize('slug', sorted(TEAMS))
class TestHistoryFiles:
    def test_history_parse_and_schema(self, slug):
        data = _load(f'./{TEAMS[slug].history_basename}')
        assert len(data) >= 25
        for date_key, entries in data.items():
            assert re.fullmatch(r'\d{2}-\d{2}', date_key)
            month, day = int(date_key[:2]), int(date_key[3:])
            assert 1 <= month <= 12 and 1 <= day <= 31
            for entry in entries:
                assert isinstance(entry['year'], int)
                assert 1876 <= entry['year'] <= 2026
                assert entry['text'] == entry['text'].upper()
                assert all(ord(c) < 128 for c in entry['text'])


class TestNflNewsTheming:
    def _make_handler(self, nfl_slug):
        import off_season_handler as osh
        from teams import get_active_nfl_team
        handler = osh.OffSeasonHandler.__new__(osh.OffSeasonHandler)
        handler.nfl_team = get_active_nfl_team({'nfl_team': nfl_slug})
        return handler

    def test_chiefs_news_uses_pack_feed_and_prefix(self, monkeypatch):
        import off_season_handler as osh

        fetched = []

        class FakeFeed:
            bozo = False

            class Entry:
                title = 'Patrick Mahomes throws for 300 yards'

            entries = [Entry()]

            def get(self, *args):
                return None

        def fake_fetch(url):
            fetched.append(url)
            return FakeFeed()

        monkeypatch.setattr(osh, 'fetch_feed', fake_fetch)
        handler = self._make_handler('chiefs')
        headlines = handler._fetch_bears_news_rss()

        assert fetched[0] == 'https://www.chiefs.com/rss/news'
        assert headlines
        assert headlines[0].startswith('CHIEFS NEWS - ')

    def test_bears_news_prefix_unchanged(self, monkeypatch):
        import off_season_handler as osh

        class FakeFeed:
            bozo = False

            class Entry:
                title = 'Caleb Williams named starter'

            entries = [Entry()]

            def get(self, *args):
                return None

        monkeypatch.setattr(osh, 'fetch_feed', lambda url: FakeFeed())
        handler = self._make_handler('bears')
        headlines = handler._fetch_bears_news_rss()
        assert headlines[0] == 'BEARS NEWS - CALEB WILLIAMS NAMED STARTER'


class TestEnglishOnlyTicker:
    def test_is_probably_english_accepts_real_headlines(self):
        from rss_fetch import is_probably_english
        for headline in (
                "FIVE OBSERVATIONS FROM THURSDAY'S PRACTICE | CHIEFS",
                'CHRIS JONES LANDS AT NO. 43 IN "NFL TOP 100" RANKINGS',
                'KANSAS CITY CHIEFS ANNOUNCE 2026 SEASON KICKOFF',
                'VON MILLER VISITS DES MOINES YOUTH CAMP',
                'BEARS SIGN CALEB WILLIAMS TO EXTENSION'):
            assert is_probably_english(headline), headline

    def test_is_probably_english_rejects_foreign_headlines(self):
        from rss_fetch import is_probably_english
        for headline in (
                'EIN NEU GEDACHTES VERMÄCHTNIS: DIE KANSAS CITY CHIEFS',
                'DIE KANSAS CITY CHIEFS UND EQUIP SPORT BRINGEN KOSTENLOSE',
                'UN LEGADO REIMAGINADO: KANSAS CITY CHIEFS PUBLICAN RENOVACIÓN',
                'UN LEGADO REIMAGINADO: KANSAS CITY CHIEFS'):
            assert not is_probably_english(headline), headline

    def test_nfl_ticker_drops_foreign_headlines(self, monkeypatch):
        import off_season_handler as osh
        from teams import get_active_nfl_team

        class FakeFeed:
            bozo = False

            class E1:
                title = 'Chiefs announce 2026 season kickoff'

            class E2:
                title = 'Die Kansas City Chiefs und Equip Sport bringen'

            entries = [E1(), E2()]

            def get(self, *args):
                return None

        monkeypatch.setattr(osh, 'fetch_feed', lambda url: FakeFeed())
        handler = osh.OffSeasonHandler.__new__(osh.OffSeasonHandler)
        handler.nfl_team = get_active_nfl_team({'nfl_team': 'chiefs'})
        headlines = handler._fetch_bears_news_rss()
        assert any('KICKOFF' in h for h in headlines)
        assert not any('EQUIP SPORT' in h for h in headlines)

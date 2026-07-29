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

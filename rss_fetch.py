"""Timeout-aware RSS feed fetching.

feedparser.parse(url) performs its own HTTP fetch with no socket timeout,
which can block the display thread indefinitely on a stalled host. Fetch
with requests (which enforces a timeout) and hand the bytes to feedparser.
"""

from __future__ import annotations

import re

import feedparser
import requests

FEED_TIMEOUT = 10  # seconds

# Official team feeds (e.g. chiefs.com) mix in localized posts. Function
# words only - content words risk English collisions (PUBLICAN, CON,
# LOS as in Los Angeles are all real English/NFL ticker text).
_NON_ENGLISH_HINT_WORDS = frozenset({
    # German (VON excluded: Von Miller; DIE excluded: English verb)
    'UND', 'DER', 'EIN', 'EINE', 'MIT', 'NEUE', 'NICHT',
    # Spanish
    'UN', 'UNA', 'DEL', 'PARA', 'POR',
    # French (DES excluded: Des Moines)
    'LES', 'POUR', 'AVEC', 'DANS',
})


def is_probably_english(headline: str) -> bool:
    """Cheap English check for ticker headlines.

    Rejects accented/non-ASCII letters (VERMÄCHTNIS, RENOVACIÓN) and
    all-ASCII foreign text via common function words (UN LEGADO ...).
    Headlines with rare English borrowings (CAFÉ) are sacrificed - an
    LED ticker prefers a false reject over a foreign headline.
    """
    if any(ord(ch) > 127 and ch.isalpha() for ch in headline):
        return False
    words = set(re.findall(r"[A-Z']+", headline.upper()))
    return not (words & _NON_ENGLISH_HINT_WORDS)


def fetch_feed(url: str, timeout: int = FEED_TIMEOUT):
    """Fetch an RSS feed URL with a timeout and parse it with feedparser.

    Never raises: on any network error, returns an empty parsed feed
    (feed.entries == [] and feed.bozo set), matching how callers already
    handle unparseable feeds.
    """
    try:
        # Some hosts (e.g. espn.com) reject the default python-requests
        # User-Agent with a 403 but accept feedparser's.
        response = requests.get(
            url, timeout=timeout,
            headers={'User-Agent': feedparser.USER_AGENT},
        )
        response.raise_for_status()
        return feedparser.parse(response.content)
    except requests.RequestException:
        return feedparser.parse(b'')

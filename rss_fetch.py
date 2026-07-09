"""Timeout-aware RSS feed fetching.

feedparser.parse(url) performs its own HTTP fetch with no socket timeout,
which can block the display thread indefinitely on a stalled host. Fetch
with requests (which enforces a timeout) and hand the bytes to feedparser.
"""

from __future__ import annotations

import feedparser
import requests

FEED_TIMEOUT = 10  # seconds


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

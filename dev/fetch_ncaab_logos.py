"""Fetch every Division I men's basketball logo from ESPN for the LED matrix.

The team list comes from ESPN's own teams endpoint, so realignment and new
D-I programs are picked up by re-running. Each logo is the "dark" variant
(drawn for dark backgrounds, which every pack's primary color is), resized
to 20x20 (LANCZOS, RGBA preserved) and written to logos/ncaab/{id}.png.

Files are keyed by ESPN team id rather than abbreviation: abbreviations are
not unique across ~365 schools, ids are. Rerunnable; this script is the
source of truth for regenerating the committed logo files.

Usage (from the repo root): python3 dev/fetch_ncaab_logos.py
"""

from __future__ import annotations

import io
import os
from concurrent.futures import ThreadPoolExecutor

import requests
from PIL import Image

TEAMS_URL = ('https://site.api.espn.com/apis/site/v2/sports/basketball/'
             'mens-college-basketball/teams?limit=1000')
OUT_DIR = './logos/ncaab'
SIZE = (20, 20)


def logo_url(team: dict) -> str | None:
    """The dark-background logo when ESPN has one, else the default"""
    logos = team.get('logos') or []
    for logo in logos:
        if 'dark' in (logo.get('rel') or []):
            return logo.get('href')
    return logos[0].get('href') if logos else None


def fetch_one(team: dict) -> str:
    url = logo_url(team)
    if not url:
        return f"{team['id']} {team.get('abbreviation')}: no logo listed"
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    img = Image.open(io.BytesIO(response.content)).convert('RGBA')
    img.resize(SIZE, Image.LANCZOS).save(f"{OUT_DIR}/{team['id']}.png")
    return ''


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    data = requests.get(TEAMS_URL, timeout=20).json()
    teams = [entry['team'] for entry in
             data['sports'][0]['leagues'][0]['teams']]

    def safe(team: dict) -> str:
        try:
            return fetch_one(team)
        except Exception as e:
            return f"{team['id']} {team.get('abbreviation')}: {e}"

    with ThreadPoolExecutor(max_workers=8) as pool:
        problems = [p for p in pool.map(safe, teams) if p]

    for problem in problems:
        print(f'SKIPPED {problem}')
    print(f'Done: {len(teams) - len(problems)} of {len(teams)} logos '
          f'in {OUT_DIR}')


if __name__ == '__main__':
    main()

"""Fetch all 32 NFL team logos from ESPN's CDN for the LED matrix.

Downloads https://a.espncdn.com/i/teamlogos/nfl/500/{slug}.png for every
team, resizes to 20x20 (LANCZOS, RGBA preserved), and writes
logos/nfl/{ABBREV}.png. Rerunnable; this script is the source of truth
for regenerating the committed logo files.

Usage (from the repo root): python3 dev/fetch_nfl_logos.py
"""

from __future__ import annotations

import io
import os

import requests
from PIL import Image

# ESPN CDN slug for each team; output filename is slug.upper() which
# matches the abbreviation ESPN's API uses for competitors.
CDN_SLUGS = [
    'ari', 'atl', 'bal', 'buf', 'car', 'chi', 'cin', 'cle',
    'dal', 'den', 'det', 'gb', 'hou', 'ind', 'jax', 'kc',
    'lac', 'lar', 'lv', 'mia', 'min', 'ne', 'no', 'nyg',
    'nyj', 'phi', 'pit', 'sea', 'sf', 'tb', 'ten', 'wsh',
]

OUT_DIR = './logos/nfl'
SIZE = (20, 20)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    for slug in CDN_SLUGS:
        url = f'https://a.espncdn.com/i/teamlogos/nfl/500/{slug}.png'
        out_path = f'{OUT_DIR}/{slug.upper()}.png'
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        img = Image.open(io.BytesIO(response.content)).convert('RGBA')
        img = img.resize(SIZE, Image.LANCZOS)
        img.save(out_path)
        print(f'{out_path} written ({len(response.content)} bytes source)')
    print(f'Done: {len(CDN_SLUGS)} logos in {OUT_DIR}')


if __name__ == '__main__':
    main()

"""Generate land_mask.png - the 1-bit equirectangular land mask behind
the ISS globe view.

Source: NASA Visible Earth "land_shallow_topo_2048" (public domain).
Run from the repo root:  python3 dev/generate_land_mask.py
"""

import io

import requests
from PIL import Image

SOURCE_URL = ('https://eoimages.gsfc.nasa.gov/images/imagerecords/'
              '57000/57752/land_shallow_topo_2048.jpg')
MASK_SIZE = (384, 192)  # ~1 degree per pixel, plenty for a 44px globe


def make_land_mask():
    response = requests.get(SOURCE_URL, timeout=30)
    response.raise_for_status()
    src = Image.open(io.BytesIO(response.content)).convert('RGB')
    src = src.resize(MASK_SIZE, Image.LANCZOS)

    mask = Image.new('1', MASK_SIZE, 0)
    for y in range(MASK_SIZE[1]):
        for x in range(MASK_SIZE[0]):
            r, g, b = src.getpixel((x, y))
            # ocean in the source is blue-dominant; everything else is land
            if not (b > r + 8 and b > g + 4):
                mask.putpixel((x, y), 1)
    mask.save('land_mask.png')


if __name__ == '__main__':
    make_land_mask()
    print('Wrote land_mask.png')

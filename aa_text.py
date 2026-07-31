"""Anti-aliased TrueType text rendering for the LED matrix.

Strings are rasterized at SCALE-times the target size and downsampled
with LANCZOS, so edge pixels come out as intermediate gray levels. Drawn
onto the matrix as partial LED brightness, those soft edges read as
smooth curves at viewing distance.
"""

from __future__ import annotations

import os
from typing import Sequence

from PIL import Image, ImageDraw, ImageFont

# Supersampling factor: render at 4x, downsample to 1x
SCALE: int = 4


def find_ttf(candidates: Sequence[str]) -> str | None:
    """First existing path from candidates, or None if there is none"""
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


class AATextRenderer:
    """Renders strings to cached 1x-scale grayscale bitmaps"""

    def __init__(self, ttf_path: str, size: int) -> None:
        self._font = ImageFont.truetype(ttf_path, size * SCALE)
        ascent, descent = self._font.getmetrics()
        self.ascent: int = max(1, round(ascent / SCALE))
        self._height_4x = ascent + descent
        self._height = max(1, round(self._height_4x / SCALE))
        self._cache: dict[str, Image.Image] = {}

    def render(self, text: str) -> Image.Image:
        """Grayscale ('L') image of text at 1x scale; cached per string"""
        img = self._cache.get(text)
        if img is None:
            width_4x = max(1, int(self._font.getlength(text)))
            big = Image.new('L', (width_4x, self._height_4x), 0)
            ImageDraw.Draw(big).text((0, 0), text, font=self._font, fill=255)
            img = big.resize(
                (max(1, round(width_4x / SCALE)), self._height),
                Image.LANCZOS)
            self._cache[text] = img
        return img

    def measure(self, text: str) -> int:
        """Rendered width of text in 1x pixels"""
        return self.render(text).width

    def fit(self, text: str, max_width: int) -> str:
        """Trim trailing characters until text fits in max_width pixels"""
        if max_width <= 0:
            return ''
        while text and self.measure(text) > max_width:
            text = text[:-1].rstrip()
        return text

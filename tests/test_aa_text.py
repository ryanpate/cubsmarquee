"""Anti-aliased TTF text rendering for the flight screens"""

from __future__ import annotations

import os


class TestConfig:
    def test_bundled_ttf_and_constants(self) -> None:
        from scoreboard_config import Fonts

        assert Fonts.AA_TEXT_SIZE == 9
        assert Fonts.AA_TTF_CANDIDATES[0] == './fonts/DejaVuSans-Bold.ttf'
        assert os.path.exists(Fonts.AA_TTF_CANDIDATES[0])

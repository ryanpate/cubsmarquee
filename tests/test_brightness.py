"""Tests for ScoreboardManager._load_brightness() helper."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from scoreboard_manager import ScoreboardManager


class TestLoadBrightness:
    def test_returns_default_when_config_missing(self, tmp_path):
        missing = tmp_path / "config.json"
        with patch("scoreboard_manager.BRIGHTNESS_CONFIG_PATH", str(missing)):
            result = ScoreboardManager._load_brightness(MagicMock())
        assert result == 100

    def test_returns_value_from_config(self, tmp_path):
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"brightness": 50}))
        with patch("scoreboard_manager.BRIGHTNESS_CONFIG_PATH", str(cfg)):
            result = ScoreboardManager._load_brightness(MagicMock())
        assert result == 50

    def test_clamps_below_minimum(self, tmp_path):
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"brightness": 3}))
        with patch("scoreboard_manager.BRIGHTNESS_CONFIG_PATH", str(cfg)):
            result = ScoreboardManager._load_brightness(MagicMock())
        assert result == 10

    def test_clamps_above_maximum(self, tmp_path):
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"brightness": 500}))
        with patch("scoreboard_manager.BRIGHTNESS_CONFIG_PATH", str(cfg)):
            result = ScoreboardManager._load_brightness(MagicMock())
        assert result == 100

    def test_returns_default_when_key_missing(self, tmp_path):
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"zip_code": "60613"}))
        with patch("scoreboard_manager.BRIGHTNESS_CONFIG_PATH", str(cfg)):
            result = ScoreboardManager._load_brightness(MagicMock())
        assert result == 100

    def test_returns_default_when_value_not_numeric(self, tmp_path):
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"brightness": "bright"}))
        with patch("scoreboard_manager.BRIGHTNESS_CONFIG_PATH", str(cfg)):
            result = ScoreboardManager._load_brightness(MagicMock())
        assert result == 100

    def test_returns_default_when_config_malformed(self, tmp_path):
        cfg = tmp_path / "config.json"
        cfg.write_text("{not valid json")
        with patch("scoreboard_manager.BRIGHTNESS_CONFIG_PATH", str(cfg)):
            result = ScoreboardManager._load_brightness(MagicMock())
        assert result == 100

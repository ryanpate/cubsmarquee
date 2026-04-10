"""Tests for setup_display module."""
from __future__ import annotations

from unittest.mock import patch, MagicMock
import pytest

from setup_display import needs_setup


class TestNeedsSetup:
    def test_returns_true_when_config_missing(self, tmp_path):
        missing = tmp_path / "config.json"
        with patch("setup_display.CONFIG_PATH", str(missing)):
            assert needs_setup() is True

    def test_returns_true_when_wifi_not_connected(self, tmp_path):
        cfg = tmp_path / "config.json"
        cfg.write_text("{}")
        with patch("setup_display.CONFIG_PATH", str(cfg)):
            mock_result = MagicMock()
            mock_result.stdout = "\n"
            with patch("setup_display.subprocess.run", return_value=mock_result):
                assert needs_setup() is True

    def test_returns_false_when_config_present_and_wifi_connected(self, tmp_path):
        cfg = tmp_path / "config.json"
        cfg.write_text("{}")
        with patch("setup_display.CONFIG_PATH", str(cfg)):
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "MyHomeWiFi\n"
            with patch("setup_display.subprocess.run", return_value=mock_result):
                assert needs_setup() is False

    def test_returns_true_when_iwgetid_raises(self, tmp_path):
        cfg = tmp_path / "config.json"
        cfg.write_text("{}")
        with patch("setup_display.CONFIG_PATH", str(cfg)):
            with patch("setup_display.subprocess.run", side_effect=FileNotFoundError):
                assert needs_setup() is True

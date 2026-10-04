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


class TestRenderFrame:
    def test_shows_starting_message_until_hotspot_flag_exists(self, tmp_path):
        from setup_display import SetupDisplay

        missing_flag = tmp_path / "setup_hotspot_active"
        display = SetupDisplay(MagicMock())
        start_x = display.scroll_x
        with patch("setup_display.HOTSPOT_FLAG_PATH", str(missing_flag)):
            img = display._render_frame()

        # Static notice: scroll position must not advance
        assert display.scroll_x == start_x
        assert img.size == (96, 48)

    def test_scrolls_connect_instructions_once_hotspot_up(self, tmp_path):
        from setup_display import SetupDisplay

        flag = tmp_path / "setup_hotspot_active"
        flag.write_text("")
        display = SetupDisplay(MagicMock())
        start_x = display.scroll_x
        with patch("setup_display.HOTSPOT_FLAG_PATH", str(flag)):
            display._render_frame()

        assert display.scroll_x == start_x - 1


class TestSetupDisplayRunLoop:
    def test_run_until_configured_exits_when_setup_complete(self):
        from setup_display import SetupDisplay

        mock_manager = MagicMock()
        display = SetupDisplay(mock_manager, poll_interval=0.01)

        call_count = {"n": 0}

        def fake_needs_setup():
            call_count["n"] += 1
            return call_count["n"] < 3

        with patch("setup_display.needs_setup", side_effect=fake_needs_setup):
            with patch("setup_display.is_shutdown_requested", return_value=False):
                display.run_until_configured()

        assert call_count["n"] >= 3
        assert mock_manager.swap_canvas.called

    def test_run_until_configured_exits_on_shutdown(self):
        from setup_display import SetupDisplay

        mock_manager = MagicMock()
        display = SetupDisplay(mock_manager, poll_interval=0.01)

        with patch("setup_display.needs_setup", return_value=True):
            with patch("setup_display.is_shutdown_requested", return_value=True):
                display.run_until_configured()


class TestHotspotContract:
    """The on-screen instructions must match what the AP scripts actually do."""

    SCRIPTS = ("wifi_manager.sh", "wifi_manager_nm.sh")

    def _read(self, name):
        from pathlib import Path
        return (Path(__file__).resolve().parent.parent / name).read_text()

    @pytest.mark.parametrize("script", SCRIPTS)
    def test_every_ap_script_raises_the_flag_the_display_waits_for(self, script):
        from setup_display import HOTSPOT_FLAG_PATH
        src = self._read(script)
        assert HOTSPOT_FLAG_PATH in src
        assert "touch" in src

    @pytest.mark.parametrize("script", SCRIPTS)
    def test_message_names_the_ssid_password_and_ip_the_script_uses(self, script):
        import re
        from setup_display import SETUP_MESSAGE
        src = self._read(script)
        for var in ("AP_SSID", "AP_PASSWORD", "AP_IP"):
            value = re.search(rf'^{var}="([^"]+)"', src, re.M).group(1)
            assert value in SETUP_MESSAGE, f"{var}={value} missing from screen"

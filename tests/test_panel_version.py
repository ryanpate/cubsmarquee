"""Tests for ScoreboardManager._apply_panel_options() panel-revision handling."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from scoreboard_manager import ScoreboardManager


def apply(config: dict) -> SimpleNamespace:
    """Run _apply_panel_options against a bare options object."""
    options = SimpleNamespace()
    with patch("scoreboard_manager.load_user_config", return_value=config):
        ScoreboardManager._apply_panel_options(MagicMock(), options)
    return options


class TestPanelVersion:
    def test_missing_key_leaves_v1_options_untouched(self):
        options = apply({"brightness": 100})
        assert not hasattr(options, "row_address_type")
        assert not hasattr(options, "led_rgb_sequence")
        assert not hasattr(options, "gpio_slowdown")

    def test_explicit_v1_leaves_options_untouched(self):
        options = apply({"panel_version": "v1"})
        assert not hasattr(options, "row_address_type")
        assert not hasattr(options, "gpio_slowdown")

    def test_v2_sets_shift_register_addressing_and_bgr(self):
        options = apply({"panel_version": "v2"})
        assert options.row_address_type == 5
        assert options.led_rgb_sequence == "BGR"
        assert options.gpio_slowdown == 4

    def test_v2_accepts_surrounding_whitespace_and_case(self):
        options = apply({"panel_version": " V2 "})
        assert options.row_address_type == 5

    def test_v2_slowdown_override(self):
        options = apply({"panel_version": "v2", "gpio_slowdown": 2})
        assert options.gpio_slowdown == 2
        assert options.row_address_type == 5

    def test_v1_slowdown_override_without_v2_profile(self):
        options = apply({"panel_version": "v1", "gpio_slowdown": 3})
        assert options.gpio_slowdown == 3
        assert not hasattr(options, "row_address_type")

    def test_invalid_slowdown_leaves_library_default(self):
        options = apply({"panel_version": "v2", "gpio_slowdown": "fast"})
        assert not hasattr(options, "gpio_slowdown")
        assert options.row_address_type == 5

    def test_unknown_version_falls_back_to_v1(self):
        options = apply({"panel_version": "v3"})
        assert not hasattr(options, "row_address_type")

    def test_empty_config_leaves_options_untouched(self):
        options = apply({})
        assert not hasattr(options, "row_address_type")

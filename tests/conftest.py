"""Pytest configuration and shared fixtures"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

# Mock the rgbmatrix module before any imports that depend on it
# This allows tests to run on systems without the Raspberry Pi hardware
sys.modules['rgbmatrix'] = MagicMock()
sys.modules['rgbmatrix.graphics'] = MagicMock()

# Create mock classes for rgbmatrix
mock_rgbmatrix = sys.modules['rgbmatrix']
mock_rgbmatrix.RGBMatrix = MagicMock()
mock_rgbmatrix.RGBMatrixOptions = MagicMock()

mock_graphics = sys.modules['rgbmatrix.graphics']
mock_graphics.Font = MagicMock()
mock_graphics.Color = MagicMock()
mock_graphics.DrawText = MagicMock()

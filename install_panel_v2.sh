#!/bin/bash
# Switch a Pi to a Waveshare V2 96x48 panel (SM5368 row-select shift register).
# Run this once on each V2 build. V1 Pis must NOT run this.
#
# V2 panels are still HUB75 on the same 16-pin ribbon, but they select rows by
# clocking a bit through an SM5368 shift register instead of putting a binary
# row number on A/B/C. The upstream rgbmatrix library has no support for that,
# so this installs Waveshare's build over it and flips panel_version in
# config.json. The scoreboard code itself is identical on V1 and V2.

set -euo pipefail

SRC_DIR="/home/pi/RGB-Matrix-Px-xx"
PI_DIR="$SRC_DIR/example/Rasberry-Pi"
CONFIG="/home/pi/config.json"

echo "Installing Waveshare V2 panel support..."

# The bindings need Python 3.11+ (pyproject requires-python). Bullseye ships
# 3.9, so stop here rather than failing halfway through a pip build.
PY_OK=$(python3 -c 'import sys; print(1 if sys.version_info >= (3, 11) else 0)')
if [ "$PY_OK" != "1" ]; then
    echo "ERROR: need Python 3.11+, found $(python3 -V). Reimage with Bookworm." >&2
    exit 1
fi

echo "==> Installing build dependencies"
sudo apt-get update
sudo apt-get install -y git build-essential cmake pkg-config python3-dev cython3

echo "==> Fetching Waveshare library"
if [ -d "$SRC_DIR/.git" ]; then
    git -C "$SRC_DIR" fetch --depth 1 origin main
    git -C "$SRC_DIR" reset --hard origin/main
else
    git clone --depth 1 --filter=blob:none --sparse \
        https://github.com/waveshareteam/RGB-Matrix-Px-xx.git "$SRC_DIR"
    git -C "$SRC_DIR" sparse-checkout set example/Rasberry-Pi
fi

# Install system-wide, not into a venv: the service runs main.py as root via
# launch_scoreboard.sh and rgbmatrix drops privileges after init, so the
# module has to be readable by the unprivileged user it drops to.
echo "==> Building and installing rgbmatrix (replaces the existing module)"
sudo pip3 install --break-system-packages --force-reinstall -v "$PI_DIR"

echo "==> Setting panel_version=v2 in $CONFIG"
sudo cp "$CONFIG" "$CONFIG.bak-$(date +%Y%m%d%H%M%S)"
sudo python3 - "$CONFIG" <<'EOF'
import json, sys
path = sys.argv[1]
with open(path) as f:
    config = json.load(f)
config['panel_version'] = 'v2'
with open(path, 'w') as f:
    json.dump(config, f, indent=2)
EOF

echo ""
echo "V2 panel support installed."
echo ""
echo "If the panel flickers, raise the slowdown by adding to $CONFIG:"
echo '    "gpio_slowdown": 2   (Pi 5)   or   4   (Pi 4 / earlier, the default)'
echo ""
echo "Reboot now to pick it up:  sudo reboot"

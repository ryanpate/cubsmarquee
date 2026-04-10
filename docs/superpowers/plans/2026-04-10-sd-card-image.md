# SD Card Image Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the tooling and runtime changes needed to mass-produce Cubs Marquee units from a single flashable SD card image.

**Architecture:** Golden-master clone workflow. A `prepare_for_image.sh` script strips per-unit state from a working Pi and installs a `first-boot.service` that regenerates identity on each new unit. A `setup_display.py` mode shows on-matrix instructions until the buyer configures WiFi and API keys via the existing admin panel. A `capture_image.sh` script reads the prepared SD card on a Mac to a `.img` file ready for Pi Imager.

**Tech Stack:** Bash, systemd, Python 3.9+ (Pillow, rgbmatrix), pytest. Target host: Raspberry Pi OS Lite (Bookworm), capture host: macOS.

**Reference spec:** `docs/superpowers/specs/2026-04-10-sd-card-image-design.md`

---

## File Structure

**Created:**
- `prepare_for_image.sh` — Bash, run on golden master Pi as root
- `capture_image.sh` — Bash, run on Mac
- `first_boot.sh` — Bash, installed by `prepare_for_image.sh` to `/usr/local/sbin/first_boot.sh`
- `first-boot.service` — Systemd unit, installed to `/etc/systemd/system/first-boot.service`
- `setup_display.py` — Python display handler, sibling of `weather_display.py`
- `tests/test_setup_display.py` — Pytest unit tests for setup-state detection
- `docs/IMAGING.md` — Project owner documentation for imaging workflow

**Modified:**
- `main.py` — Add `needs_setup()` check at startup before normal cycle

---

## Task 1: `setup_display.py` — module skeleton and `needs_setup()` helper

**Files:**
- Create: `setup_display.py`
- Create: `tests/test_setup_display.py`

- [ ] **Step 1: Write the failing test for `needs_setup()`**

Create `tests/test_setup_display.py`:

```python
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
            mock_result.stdout = "MyHomeWiFi\n"
            with patch("setup_display.subprocess.run", return_value=mock_result):
                assert needs_setup() is False

    def test_returns_true_when_iwgetid_raises(self, tmp_path):
        cfg = tmp_path / "config.json"
        cfg.write_text("{}")
        with patch("setup_display.CONFIG_PATH", str(cfg)):
            with patch("setup_display.subprocess.run", side_effect=FileNotFoundError):
                assert needs_setup() is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_setup_display.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'setup_display'`

- [ ] **Step 3: Create `setup_display.py` with `needs_setup()` only**

```python
"""Setup-mode display: shows on-matrix instructions until first-time configuration is complete."""
from __future__ import annotations

import os
import subprocess

CONFIG_PATH = "/home/pi/config.json"


def needs_setup() -> bool:
    """Return True if the unit has not yet been configured.

    A unit needs setup when either the user config file is missing,
    or the Pi is not currently associated with a WiFi network.
    """
    if not os.path.exists(CONFIG_PATH):
        return True
    try:
        result = subprocess.run(
            ["iwgetid", "-r"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return not result.stdout.strip()
    except Exception:
        return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_setup_display.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add setup_display.py tests/test_setup_display.py
git commit -m "Add setup_display module with needs_setup() detection"
```

---

## Task 2: `setup_display.py` — `SetupDisplay` class with run loop

**Files:**
- Modify: `setup_display.py`
- Modify: `tests/test_setup_display.py`

- [ ] **Step 1: Write failing test for `SetupDisplay.run_until_configured` polling behavior**

Append to `tests/test_setup_display.py`:

```python
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
        assert mock_manager.matrix.SwapOnVSync.called

    def test_run_until_configured_exits_on_shutdown(self):
        from setup_display import SetupDisplay

        mock_manager = MagicMock()
        display = SetupDisplay(mock_manager, poll_interval=0.01)

        with patch("setup_display.needs_setup", return_value=True):
            with patch("setup_display.is_shutdown_requested", return_value=True):
                display.run_until_configured()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_setup_display.py::TestSetupDisplayRunLoop -v`
Expected: FAIL with `ImportError: cannot import name 'SetupDisplay'`

- [ ] **Step 3: Add `SetupDisplay` class to `setup_display.py`**

Append to `setup_display.py`:

```python
import time
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont

from scoreboard_config import Colors, DisplayConfig
from logger import get_logger

if TYPE_CHECKING:
    from scoreboard_manager import ScoreboardManager


def is_shutdown_requested() -> bool:
    """Lazy import to avoid circular dependency with main.py."""
    try:
        from main import is_shutdown_requested as _check
        return _check()
    except Exception:
        return False


logger = get_logger("setup_display")

SETUP_MESSAGE = "Connect phone to WiFi: CubsMarquee-Setup    Open: cubsmarquee.local/admin"
HEADER_TEXT = "SETUP"


class SetupDisplay:
    """Shows scrolling setup instructions on the LED matrix until WiFi and config are present."""

    def __init__(self, manager: "ScoreboardManager", poll_interval: float = 10.0) -> None:
        self.manager = manager
        self.poll_interval = poll_interval
        self.scroll_x: int = DisplayConfig.MATRIX_COLS
        try:
            self.font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 8
            )
        except Exception:
            self.font = ImageFont.load_default()

    def _render_frame(self) -> Image.Image:
        img = Image.new("RGB", (DisplayConfig.MATRIX_COLS, DisplayConfig.MATRIX_ROWS), Colors.BLACK)
        draw = ImageDraw.Draw(img)

        # Header bar
        draw.rectangle([(0, 0), (DisplayConfig.MATRIX_COLS - 1, 9)], fill=Colors.CUBS_BLUE)
        bbox = draw.textbbox((0, 0), HEADER_TEXT, font=self.font)
        text_w = bbox[2] - bbox[0]
        draw.text(
            ((DisplayConfig.MATRIX_COLS - text_w) // 2, 0),
            HEADER_TEXT,
            font=self.font,
            fill=Colors.YELLOW,
        )

        # Scrolling body
        draw.text((self.scroll_x, 18), SETUP_MESSAGE, font=self.font, fill=Colors.YELLOW)
        bbox = draw.textbbox((0, 0), SETUP_MESSAGE, font=self.font)
        msg_w = bbox[2] - bbox[0]

        self.scroll_x -= 1
        if self.scroll_x < -msg_w:
            self.scroll_x = DisplayConfig.MATRIX_COLS

        return img

    def run_until_configured(self) -> None:
        """Block until both config.json exists and WiFi is connected, then return."""
        logger.info("Entering setup display mode")
        last_check = 0.0
        while True:
            if is_shutdown_requested():
                logger.info("Shutdown requested during setup display")
                return

            now = time.time()
            if now - last_check >= self.poll_interval:
                if not needs_setup():
                    logger.info("Setup complete - exiting setup display")
                    return
                last_check = now

            img = self._render_frame()
            self.manager.matrix.SetImage(img)
            self.manager.matrix.SwapOnVSync(self.manager.matrix)
            time.sleep(0.03)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_setup_display.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add setup_display.py tests/test_setup_display.py
git commit -m "Add SetupDisplay class with scrolling instructions and poll loop"
```

---

## Task 3: Wire `SetupDisplay` into `main.py` startup

**Files:**
- Modify: `main.py` (add import and check inside `CubsScoreboard.run`)

- [ ] **Step 1: Find the run loop entry point in `main.py`**

Run: `grep -n "def run" main.py`
Expected: a method like `def run(self)` on `CubsScoreboard`. Note the line number.

- [ ] **Step 2: Add the import**

Edit `main.py`. After the existing handler imports (around line 18), add:

```python
from setup_display import SetupDisplay, needs_setup
```

- [ ] **Step 3: Add the setup gate at the top of `CubsScoreboard.run`**

Inside `CubsScoreboard.run` (or whichever method is the main entry called from `if __name__ == "__main__"`), insert as the very first action inside the method body:

```python
if needs_setup():
    logger.info("First-boot or unconfigured state detected - showing setup display")
    SetupDisplay(self.manager).run_until_configured()
    if is_shutdown_requested():
        return
```

- [ ] **Step 4: Smoke-test the import path**

Run: `python3 -c "import main"`
Expected: no `ImportError`. (Will likely fail on `rgbmatrix` import on Mac — that's fine; verify the failure is `rgbmatrix`, not `setup_display`.)

- [ ] **Step 5: Run full pytest suite**

Run: `pytest tests/ -v`
Expected: all tests pass, no regressions.

- [ ] **Step 6: Commit**

```bash
git add main.py
git commit -m "Run SetupDisplay at startup when unit is unconfigured"
```

---

## Task 4: `first-boot.service` and `first_boot.sh`

**Files:**
- Create: `first-boot.service`
- Create: `first_boot.sh`

- [ ] **Step 1: Create `first-boot.service`**

```ini
[Unit]
Description=Cubs Marquee first-boot identity reset
DefaultDependencies=no
After=local-fs.target
Before=cubs-scoreboard.service wifi-manager.service network-pre.target
ConditionPathExists=!/home/pi/.first-boot-complete

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/first_boot.sh
RemainAfterExit=no
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Create `first_boot.sh`**

```bash
#!/bin/bash
# first_boot.sh - regenerates per-unit identity on the first boot of a flashed image.
# Idempotent guard: marker file at /home/pi/.first-boot-complete prevents re-running.

set -euo pipefail

MARKER=/home/pi/.first-boot-complete
LOG=/var/log/cubsmarquee-first-boot.log

log() {
    echo "[first-boot] $(date -Iseconds) $*" | tee -a "$LOG"
}

if [ -f "$MARKER" ]; then
    log "Marker present, skipping first-boot setup"
    exit 0
fi

log "Starting first-boot setup"

log "Regenerating SSH host keys"
rm -f /etc/ssh/ssh_host_*
ssh-keygen -A

log "Expanding root filesystem"
if command -v raspi-config >/dev/null 2>&1; then
    raspi-config nonint do_expand_rootfs || log "WARN: do_expand_rootfs returned non-zero"
else
    log "WARN: raspi-config not available, skipping rootfs expand"
fi

log "Touching marker file"
touch "$MARKER"
chown pi:pi "$MARKER"

log "Disabling first-boot.service"
systemctl disable first-boot.service || true

log "Rebooting to apply changes"
sync
sleep 2
systemctl reboot
```

- [ ] **Step 3: Lint the shell script**

Run: `bash -n first_boot.sh`
Expected: no output (syntax OK).

If `shellcheck` is installed: `shellcheck first_boot.sh`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add first-boot.service first_boot.sh
git commit -m "Add first-boot systemd service and identity-reset script"
```

---

## Task 5: `prepare_for_image.sh`

**Files:**
- Create: `prepare_for_image.sh`

- [ ] **Step 1: Create `prepare_for_image.sh`**

```bash
#!/bin/bash
# prepare_for_image.sh - strips per-unit state from the golden master Pi
# in preparation for SD card capture. Run as root on the Pi as the very last
# step before shutdown. The Pi will power off when this script completes.
#
# Run with:  sudo ./prepare_for_image.sh

set -euo pipefail

if [ "$EUID" -ne 0 ]; then
    echo "ERROR: must be run as root (use sudo)" >&2
    exit 1
fi

REPO_DIR=$(cd "$(dirname "$0")" && pwd)

echo "==> Cubs Marquee: preparing golden master for image capture"
echo "==> Repo dir: $REPO_DIR"

echo "==> Confirming intent (this will WIPE configs, keys, logs, and SHUT DOWN the Pi)"
read -r -p "Type YES to continue: " CONFIRM
if [ "$CONFIRM" != "YES" ]; then
    echo "Aborted."
    exit 1
fi

echo "==> Stopping services"
systemctl stop cubs-scoreboard.service 2>/dev/null || true
systemctl stop wifi-manager.service 2>/dev/null || true
systemctl stop wifi-web-config.service 2>/dev/null || true

echo "==> Clearing logs"
rm -rf /home/pi/scoreboard_logs/* 2>/dev/null || true
rm -rf /var/log/cubs-scoreboard/* 2>/dev/null || true
journalctl --rotate || true
journalctl --vacuum-time=1s || true
truncate -s 0 /var/log/*.log 2>/dev/null || true

echo "==> Removing SSH host keys (regenerated on first boot)"
rm -f /etc/ssh/ssh_host_*

echo "==> Removing user config"
rm -f /home/pi/config.json

echo "==> Removing WiFi credentials"
rm -f /etc/NetworkManager/system-connections/* 2>/dev/null || true
rm -f /etc/wpa_supplicant/wpa_supplicant.conf 2>/dev/null || true

echo "==> Resetting hostname to 'cubsmarquee'"
echo "cubsmarquee" > /etc/hostname
sed -i 's/127\.0\.1\.1\s.*/127.0.1.1\tcubsmarquee/' /etc/hosts || true

echo "==> Clearing bash history and SSH client state"
rm -f /home/pi/.bash_history /root/.bash_history
rm -rf /home/pi/.ssh /root/.ssh

echo "==> Clearing git credentials"
rm -f /home/pi/.git-credentials
rm -rf /home/pi/.config/git

echo "==> Clearing apt and tmp caches"
apt-get clean
rm -f /var/cache/apt/archives/*.deb
rm -rf /tmp/* /var/tmp/* 2>/dev/null || true

echo "==> Installing first-boot service"
install -m 0755 "$REPO_DIR/first_boot.sh" /usr/local/sbin/first_boot.sh
install -m 0644 "$REPO_DIR/first-boot.service" /etc/systemd/system/first-boot.service
systemctl daemon-reload
systemctl enable first-boot.service
rm -f /home/pi/.first-boot-complete

echo "==> Writing image version stamp"
VERSION="v$(date +%Y-%m-%d)"
echo "$VERSION" > /etc/cubsmarquee-version

echo "==> Final sync and shutdown"
sync
echo "==> Done. Pi will shut down in 5 seconds."
echo "==> After shutdown, move the SD card to your Mac and run capture_image.sh"
sleep 5
shutdown -h now
```

- [ ] **Step 2: Lint the shell script**

Run: `bash -n prepare_for_image.sh`
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add prepare_for_image.sh
git commit -m "Add prepare_for_image script to strip golden master state"
```

---

## Task 6: `capture_image.sh`

**Files:**
- Create: `capture_image.sh`

- [ ] **Step 1: Create `capture_image.sh`**

```bash
#!/bin/bash
# capture_image.sh - reads a prepared SD card to a .img file on macOS.
# Run on your Mac after running prepare_for_image.sh on the golden Pi
# and moving the SD card to a USB reader.

set -euo pipefail

if [[ "$(uname)" != "Darwin" ]]; then
    echo "ERROR: this script is for macOS. On Linux, use dd directly." >&2
    exit 1
fi

echo "==> Cubs Marquee SD card capture"
echo "==> Current disks:"
diskutil list

echo
read -r -p "Enter the disk identifier of the SD card (e.g., disk4): " DISK

if [[ ! "$DISK" =~ ^disk[0-9]+$ ]]; then
    echo "ERROR: invalid disk identifier '$DISK' (expected format: disk4)" >&2
    exit 1
fi

if [[ "$DISK" == "disk0" || "$DISK" == "disk1" ]]; then
    echo "ERROR: refusing to read $DISK (likely the system disk)" >&2
    exit 1
fi

echo
echo "==> Disk info for /dev/$DISK:"
diskutil info "/dev/$DISK" | grep -E "Device / Media Name|Disk Size|Protocol|Removable Media"

echo
echo "==> WARNING: about to read /dev/$DISK to a .img file."
read -r -p "Type YES to confirm: " CONFIRM
if [ "$CONFIRM" != "YES" ]; then
    echo "Aborted."
    exit 1
fi

OUT="cubsmarquee-v$(date +%Y-%m-%d).img"
if [ -e "$OUT" ]; then
    echo "ERROR: $OUT already exists. Move or rename it first." >&2
    exit 1
fi

echo "==> Unmounting /dev/$DISK"
diskutil unmountDisk "/dev/$DISK"

echo "==> Reading /dev/r$DISK -> $OUT (this can take 10-30 minutes)"
sudo dd if="/dev/r$DISK" of="$OUT" bs=4m status=progress

echo "==> Computing SHA-256"
shasum -a 256 "$OUT"

SIZE=$(ls -lh "$OUT" | awk '{print $5}')
echo "==> Done. Image: $OUT ($SIZE)"
echo "==> Flash with Raspberry Pi Imager: Use Custom -> select $OUT"
```

- [ ] **Step 2: Lint the shell script**

Run: `bash -n capture_image.sh`
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add capture_image.sh
git commit -m "Add capture_image script for macOS SD card imaging"
```

---

## Task 7: `docs/IMAGING.md` — owner-facing documentation

**Files:**
- Create: `docs/IMAGING.md`

- [ ] **Step 1: Write the doc**

```markdown
# Cubs Marquee — SD Card Imaging Workflow

This document describes how to produce flashable SD card images for new Cubs Marquee units.

## One-time setup of the golden master Pi

1. Flash a fresh Raspberry Pi OS Lite image to a small SD card (8 or 16 GB recommended — the smaller the source card, the smaller the resulting `.img` file).
2. Boot the Pi, complete normal setup, install the Cubs Marquee project under `/home/pi/cubsmarquee/`.
3. Verify the scoreboard runs end to end.
4. Verify `wifi-manager.service` and `wifi-web-config.service` are installed and enabled.

## Producing a new image

### On the golden master Pi

```bash
cd /home/pi/cubsmarquee
git pull
sudo ./prepare_for_image.sh
```

Type `YES` to confirm. The script will strip per-unit state, install the first-boot service, and shut the Pi down.

### On your Mac

1. Move the SD card from the Pi to a USB reader and plug it into your Mac.
2. From the project directory:

```bash
./capture_image.sh
```

3. Enter the disk identifier when prompted (run `diskutil list` first if needed).
4. Type `YES` to confirm.
5. Wait for `dd` to finish (10–30 minutes).

The output will be `cubsmarquee-vYYYY-MM-DD.img` with a SHA-256 checksum.

## Buyer setup card text

Print this on a card to ship with each unit:

```
Cubs Marquee Setup
1. Plug in power. Wait ~60 seconds.
2. The display will show: SETUP REQUIRED
3. On your phone, connect to WiFi: CubsMarquee-Setup
4. Open a browser and go to: cubsmarquee.local/admin
5. Enter your home WiFi name and password.
6. Done! The scoreboard will reboot and start.
```

## Troubleshooting

### Setup display never appears
- Confirm power and ribbon cable to the LED matrix.
- SSH in via ethernet and check `journalctl -u cubs-scoreboard`.

### `CubsMarquee-Setup` WiFi network does not appear
- Wait two full minutes after power-on (first boot includes a reboot).
- Check `journalctl -u wifi-manager`.

### `cubsmarquee.local/admin` does not load
- Some phones do not resolve `.local` mDNS. Try connecting from a laptop, or use the IP address shown on the AP gateway (typically `192.168.4.1`).

### Image is huge
- Capture from the smallest possible SD card. The image is the full size of the source card; Pi Imager will compress on flash.

## Image version stamp

Each prepared Pi has `/etc/cubsmarquee-version` written by `prepare_for_image.sh`. Run `cat /etc/cubsmarquee-version` on a unit to find out which image it was flashed from.
```

- [ ] **Step 2: Commit**

```bash
git add docs/IMAGING.md
git commit -m "Add IMAGING.md owner workflow documentation"
```

---

## Task 8: End-to-end manual verification (no code, hardware required)

**Files:** none

- [ ] **Step 1: On the golden master Pi**

Pull the new code: `cd /home/pi/cubsmarquee && git pull`

- [ ] **Step 2: Run prepare script**

Run: `sudo ./prepare_for_image.sh`
Type `YES`. Wait for shutdown.

- [ ] **Step 3: Capture image on Mac**

Move the SD card to the Mac. Run: `./capture_image.sh`. Confirm with `YES`. Wait for completion.

- [ ] **Step 4: Flash a fresh SD card**

Use Raspberry Pi Imager: Operating System → Use Custom → select the new `.img`. Flash to a different SD card.

- [ ] **Step 5: Boot the test Pi**

Insert the new SD card into a different Pi with an LED matrix attached. Power on. Wait ~90 seconds (the first boot includes a reboot for filesystem expansion and SSH key regeneration).

- [ ] **Step 6: Verify setup display**

Confirm the LED matrix shows the scrolling `SETUP REQUIRED → Connect to WiFi: CubsMarquee-Setup → Open: cubsmarquee.local/admin` message.

- [ ] **Step 7: Verify AP mode**

On a phone or laptop, scan for WiFi. Confirm `CubsMarquee-Setup` (or whatever name `wifi-manager` advertises) appears. Connect to it.

- [ ] **Step 8: Verify admin panel**

Open `http://cubsmarquee.local/admin` (or `http://192.168.4.1/admin`). Confirm the page loads. Submit your real WiFi credentials.

- [ ] **Step 9: Verify reconnect and normal scoreboard**

Wait for the Pi to reboot onto your home WiFi. Confirm the LED matrix exits setup mode and starts showing normal scoreboard content.

- [ ] **Step 10: Verify identity is unique**

SSH into the new unit: `ssh pi@cubsmarquee.local` (accept the new host key).

Run: `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`
Compare with the same command on the golden master. Expected: different fingerprints.

Run: `cat /etc/cubsmarquee-version`
Expected: `vYYYY-MM-DD` matching the date you ran `prepare_for_image.sh`.

Run: `cat /etc/hostname`
Expected: not `cubsmarquee` anymore (the user picked a name in admin) OR still `cubsmarquee` if they didn't change it. Either way, it should not be `raspberrypi`.

- [ ] **Step 11: Document any deviations**

If anything failed, file the issue against the spec and fix before declaring the workflow ready for mass production.

---

## Self-Review Notes

- **Spec coverage:** Tasks 1–3 cover the `setup_display.py` and `main.py` changes. Task 4 covers `first-boot.service` and `first_boot.sh`. Task 5 covers `prepare_for_image.sh`. Task 6 covers `capture_image.sh`. Task 7 covers `docs/IMAGING.md`. Task 8 covers the manual end-to-end test from the spec's Testing section. All spec sections are represented.
- **Placeholder scan:** No TBDs. Each shell step contains the literal script body. Each Python step contains the literal code.
- **Type consistency:** `needs_setup` is the same name in `setup_display.py`, the test file, and the `main.py` import. `SetupDisplay.run_until_configured` is the same name in the class and the call site.
- **Known footguns called out:** Task 4 Step 2 explicitly warns about the `}` vs `fi` rendering issue in the heredoc — the implementer must use `fi`.

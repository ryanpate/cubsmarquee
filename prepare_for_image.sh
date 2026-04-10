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

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

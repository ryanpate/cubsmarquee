#!/bin/bash
# Applies WiFi credentials dropped onto the FAT boot partition.
#
# The boot partition is the only part of the SD card a Mac or Windows machine
# can write, so this is the offline recovery path when a Pi can't get on the
# network. Drop a file at /boot/firmware/wifi-recovery.conf containing:
#
#     ssid=YourNetwork
#     psk=YourPassword
#
# then boot. The profile is created and the file renamed to .applied so it
# only runs once.
#
# NetworkManager only (Bookworm/Trixie). Exits quietly on the older
# wpa_supplicant Pis, where boot-partition credentials are handled elsewhere.

set -u

CONF=/boot/firmware/wifi-recovery.conf
[ -f "$CONF" ] || CONF=/boot/wifi-recovery.conf
[ -f "$CONF" ] || exit 0

command -v nmcli >/dev/null 2>&1 || exit 0

log() { echo "[wifi-recovery] $*"; }

value_of() {
    # First matching key, everything after the '=' (passwords may contain '=')
    grep -E "^$1=" "$CONF" | head -1 | cut -d= -f2- | sed -e 's/[[:space:]]*$//'
}

SSID=$(value_of ssid)
PSK=$(value_of psk)
COUNTRY=$(value_of country)

if [ -z "$SSID" ]; then
    log "no ssid= in $CONF, nothing to do"
    exit 0
fi

log "applying credentials for SSID '$SSID'"

[ -n "$COUNTRY" ] && iw reg set "$COUNTRY" 2>/dev/null

# Replace any previous recovery profile so repeat drops stay idempotent.
nmcli connection delete wifi-recovery >/dev/null 2>&1

# Build the profile rather than `nmcli device wifi connect`, which needs the
# network in range at that instant. This way it autoconnects whenever it sees it.
if [ -n "$PSK" ]; then
    nmcli connection add type wifi con-name wifi-recovery ifname wlan0 \
        ssid "$SSID" \
        wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PSK" \
        connection.autoconnect yes connection.autoconnect-priority 100
else
    nmcli connection add type wifi con-name wifi-recovery ifname wlan0 \
        ssid "$SSID" \
        connection.autoconnect yes connection.autoconnect-priority 100
fi

if [ $? -ne 0 ]; then
    log "ERROR: could not create profile; leaving $CONF in place to retry"
    exit 1
fi

nmcli connection up wifi-recovery >/dev/null 2>&1 || \
    log "profile created but not up yet; will autoconnect when in range"

# Rename rather than delete so the credentials stay visible on the SD card.
mv "$CONF" "$CONF.applied" 2>/dev/null && log "renamed $CONF to .applied"

log "done"
exit 0

#!/bin/bash
# AP fallback for NetworkManager images (Bookworm/Trixie).
#
# The Bullseye path (wifi_manager.sh) drives wpa_supplicant + hostapd + dnsmasq
# directly. None of that applies here: NetworkManager owns wlan0 and provides
# hotspot mode itself, which also avoids hostapd and wpa_supplicant fighting
# over the radio -- the failure mode that broke the old AP.
#
# Waits for a normal WiFi connection; if none appears, starts a hotspot so the
# admin page on :80 can be used to enter credentials.

set -u

AP_SSID="CubsMarquee-Setup"
AP_PASSWORD="gocubsgo2024"
AP_IP="10.0.0.1"
AP_CON="marquee-hotspot"
WAIT_SECS=180          # matches the Bullseye behaviour; deliberate, not a guess
SCAN_CACHE=/var/tmp/wifi_scan_cache_nm.txt

log() { echo "[wifi-manager-nm] $*"; }

command -v nmcli >/dev/null 2>&1 || { log "no nmcli, not a NetworkManager image"; exit 0; }

is_connected() {
    # "connected" means wlan0 has a NM connection that isn't our own hotspot
    local con
    con=$(nmcli -t -f DEVICE,STATE,CONNECTION dev status 2>/dev/null \
          | awk -F: '$1=="wlan0" && $2=="connected" {print $3}')
    [ -n "$con" ] && [ "$con" != "$AP_CON" ]
}

log "waiting up to ${WAIT_SECS}s for a WiFi connection"
for i in $(seq 1 "$WAIT_SECS"); do
    if is_connected; then
        log "connected to '$(nmcli -t -f DEVICE,CONNECTION dev status | awk -F: '$1=="wlan0"{print $2}')' after ${i}s; no hotspot needed"
        exit 0
    fi
    sleep 1
done

log "no connection after ${WAIT_SECS}s, starting hotspot"

# Cache a scan while the radio is still in client mode. Once it is hosting an
# AP it cannot scan, so the setup page serves this list instead.
if nmcli -t -f SSID,SIGNAL dev wifi list --rescan yes > "$SCAN_CACHE" 2>/dev/null; then
    log "cached $(grep -c . "$SCAN_CACHE") scan results to $SCAN_CACHE"
else
    log "WARN: scan cache failed; the setup page will show an empty network list"
fi

# Rebuild the profile each time so edits to the constants above take effect.
nmcli connection delete "$AP_CON" >/dev/null 2>&1

nmcli connection add type wifi ifname wlan0 con-name "$AP_CON" \
    autoconnect no ssid "$AP_SSID" \
    802-11-wireless.mode ap 802-11-wireless.band bg \
    wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$AP_PASSWORD" \
    ipv4.method shared ipv4.addresses "${AP_IP}/24" \
    || { log "ERROR: could not create hotspot profile"; exit 1; }

if nmcli connection up "$AP_CON"; then
    log "hotspot up: SSID=${AP_SSID} password=${AP_PASSWORD}"
    log "connect to it, then open http://${AP_IP}/admin"
else
    log "ERROR: hotspot failed to start"
    exit 1
fi

#!/bin/bash
# WiFi Manager - Switches between client mode and AP mode
# Automatically creates hotspot if WiFi connection fails

SCRIPT_DIR="/home/pi"
HOSTNAME=$(hostname)
AP_SSID="CubsScoreboard-Setup"
AP_PASSWORD="gocubsgo2024"
AP_IP="10.0.0.1"
MAX_WIFI_ATTEMPTS=60
CHECK_INTERVAL=2
WPA_SUPPLICANT_CONF="/etc/wpa_supplicant/wpa_supplicant.conf"

log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a /var/log/wifi_manager.log
}

has_configured_network() {
    # Check if wpa_supplicant.conf has any configured network
    if [ -f "$WPA_SUPPLICANT_CONF" ]; then
        if grep -q "^network={" "$WPA_SUPPLICANT_CONF"; then
            return 0  # Has configured network
        fi
    fi
    return 1  # No configured network
}

restart_avahi() {
    log_message "Restarting Avahi (mDNS) service..."
    sudo systemctl restart avahi-daemon
    sleep 2
    log_message "Avahi restarted - hostname should now be reachable as ${HOSTNAME}.local"
}

check_wifi_connection() {
    # Check if wlan0 has an IP address and internet connectivity
    if ip addr show wlan0 2>/dev/null | grep -q "inet "; then
        # Get the IP to make sure it's not the AP IP
        local current_ip=$(ip addr show wlan0 | grep "inet " | awk '{print $2}' | cut -d'/' -f1)
        if [ "$current_ip" != "$AP_IP" ]; then
            if ping -c 1 -W 2 8.8.8.8 &>/dev/null; then
                return 0  # Connected
            fi
        fi
    fi
    return 1  # Not connected
}

stop_access_point() {
    log_message "Stopping Access Point mode..."
    
    # Stop services
    sudo systemctl stop hostapd 2>/dev/null
    sudo systemctl stop dnsmasq 2>/dev/null
    
    # Remove static IP configuration
    sudo ip addr flush dev wlan0 2>/dev/null
    
    # Restart networking services in proper order
    log_message "Restarting network services..."
    sudo systemctl restart dhcpcd
    sleep 2
    sudo wpa_cli -i wlan0 reconfigure 2>/dev/null
    sleep 2
    
    # Critical: Restart Avahi so hostname.local works on the new network
    restart_avahi
    
    log_message "Access Point stopped, returned to client mode"
}

start_access_point() {
    log_message "Starting Access Point mode..."
    
    # Stop any existing services first
    sudo systemctl stop hostapd 2>/dev/null
    sudo systemctl stop dnsmasq 2>/dev/null
    
    # Wait for wlan0 to be available
    for i in {1..10}; do
        if ip link show wlan0 &>/dev/null; then
            break
        fi
        log_message "Waiting for wlan0 interface... ($i/10)"
        sleep 1
    done
    
    # Configure static IP for wlan0
    sudo ip addr flush dev wlan0
    sudo ip addr add ${AP_IP}/24 dev wlan0
    sudo ip link set wlan0 up
    
    # Create hostapd configuration
    cat > /tmp/hostapd.conf << EOF
interface=wlan0
driver=nl80211
ssid=${AP_SSID}
hw_mode=g
channel=6
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=${AP_PASSWORD}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
EOF
    
    sudo mv /tmp/hostapd.conf /etc/hostapd/hostapd.conf
    
    # Create dnsmasq configuration
    cat > /tmp/dnsmasq.conf << EOF
interface=wlan0
dhcp-range=10.0.0.10,10.0.0.50,255.255.255.0,24h
domain=local
address=/cubsscoreboard.local/${AP_IP}
address=/${HOSTNAME}.local/${AP_IP}
EOF
    
    sudo mv /tmp/dnsmasq.conf /etc/dnsmasq.conf
    
    # Restart Avahi for AP mode
    restart_avahi
    
    # Start services
    sudo systemctl unmask hostapd
    sudo systemctl start dnsmasq
    sudo systemctl start hostapd
    
    log_message "Access Point started: SSID=${AP_SSID}, Password=${AP_PASSWORD}"
    log_message "Connect to the AP and visit http://${AP_IP} or http://${HOSTNAME}.local/admin"
    
    # Keep AP mode running until WiFi is configured
    while true; do
        sleep 30
        # Check if we now have a proper WiFi connection
        if check_wifi_connection; then
            log_message "WiFi connection established, stopping AP mode..."
            stop_access_point
            log_message "WiFi Manager exiting - connection successful"
            exit 0
        fi
    done
}

# Cleanup function to ensure AP is stopped on exit
cleanup() {
    log_message "Cleanup triggered..."
    # Check if we're in AP mode (hostapd running)
    if systemctl is-active --quiet hostapd; then
        # Only stop AP if we have a working WiFi connection
        if check_wifi_connection; then
            stop_access_point
        fi
    fi
}

# Register cleanup function
trap cleanup EXIT SIGTERM SIGINT

# Main logic
log_message "WiFi Manager starting..."
log_message "Hostname: ${HOSTNAME}"

# Wait for wlan0 interface to be available (up to 30 seconds)
log_message "Waiting for wlan0 interface to be available..."
WLAN_WAIT=0
while [ $WLAN_WAIT -lt 30 ]; do
    if ip link show wlan0 &>/dev/null; then
        log_message "wlan0 interface is available"
        break
    fi
    sleep 1
    WLAN_WAIT=$((WLAN_WAIT + 1))
done

if [ $WLAN_WAIT -eq 30 ]; then
    log_message "ERROR: wlan0 interface never became available after 30 seconds"
    log_message "Waiting an additional 10 seconds as fallback..."
    sleep 10
fi

# First, ensure AP services are stopped if WiFi is already connected
if check_wifi_connection; then
    log_message "WiFi already connected on startup"
    if systemctl is-active --quiet hostapd || systemctl is-active --quiet dnsmasq; then
        log_message "Stopping leftover AP services..."
        stop_access_point
    else
        # Even if AP isn't running, restart Avahi to ensure hostname is advertised
        restart_avahi
    fi
    log_message "WiFi connection verified, exiting normally"
    exit 0
fi

# Check if we have a configured network
if has_configured_network; then
    log_message "Found configured WiFi network in wpa_supplicant.conf"
    log_message "Giving wpa_supplicant time to connect naturally (up to 3 minutes)..."

    # For configured networks, wait longer with less frequent checks
    # This allows wpa_supplicant to do its job without interference
    MAX_ATTEMPTS=36  # 36 attempts * 5 seconds = 180 seconds = 3 minutes
    CHECK_INTERVAL=5

    attempt=0
    while [ $attempt -lt $MAX_ATTEMPTS ]; do
        if check_wifi_connection; then
            log_message "Successfully connected to configured WiFi network"
            # Make sure AP services are stopped
            if systemctl is-active --quiet hostapd || systemctl is-active --quiet dnsmasq; then
                log_message "Stopping AP services after successful connection..."
                stop_access_point
            else
                # Ensure Avahi is restarted even if AP wasn't running
                restart_avahi
            fi
            log_message "WiFi connection established, wifi_manager exiting"
            exit 0
        fi

        # Only log every 4th attempt to reduce log spam
        if [ $((attempt % 4)) -eq 0 ]; then
            elapsed_time=$((attempt * CHECK_INTERVAL))
            max_time=$((MAX_ATTEMPTS * CHECK_INTERVAL))
            log_message "Waiting for WiFi connection... (${elapsed_time}/${max_time} seconds)"
        fi
        sleep $CHECK_INTERVAL
        attempt=$((attempt + 1))
    done

    log_message "WiFi connection failed after 3 minutes"
    log_message "Configured network may be out of range or credentials incorrect"
else
    log_message "No configured WiFi network found in wpa_supplicant.conf"
    log_message "Skipping connection attempts, going directly to AP mode"
fi

# If we get here, either:
# 1. No network was configured, or
# 2. Connection to configured network failed after 3 minutes
log_message "Switching to Access Point mode for configuration..."

start_access_point

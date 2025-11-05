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

log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a /var/log/wifi_manager.log
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
    
    # Restart normal networking
    sudo systemctl restart dhcpcd
    sudo wpa_cli -i wlan0 reconfigure 2>/dev/null
    
    log_message "Access Point stopped, returning to client mode"
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
    fi
    log_message "WiFi connection verified, exiting normally"
    exit 0
fi

# Try to connect to configured WiFi
log_message "Attempting to connect to configured WiFi network..."

attempt=0
while [ $attempt -lt $MAX_WIFI_ATTEMPTS ]; do
    if check_wifi_connection; then
        log_message "Successfully connected to WiFi"
        # Make sure AP services are stopped
        if systemctl is-active --quiet hostapd || systemctl is-active --quiet dnsmasq; then
            log_message "Stopping AP services after successful connection..."
            stop_access_point
        fi
        exit 0
    fi
    
    log_message "WiFi connection attempt $((attempt + 1))/${MAX_WIFI_ATTEMPTS}..."
    sleep $CHECK_INTERVAL
    attempt=$((attempt + 1))
done

# If we get here, WiFi connection failed
log_message "WiFi connection failed after ${MAX_WIFI_ATTEMPTS} attempts"
log_message "Switching to Access Point mode for configuration..."

start_access_point

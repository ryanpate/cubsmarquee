#!/bin/bash
# WiFi Manager - Switches between client mode and AP mode
# Automatically creates hotspot if WiFi connection fails

SCRIPT_DIR="/home/pi"
AP_SSID="CubsScoreboard-Setup"
AP_PASSWORD="gocubsgo2024"
AP_IP="10.0.0.1"
MAX_WIFI_ATTEMPTS=30
CHECK_INTERVAL=2

log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a /var/log/wifi_manager.log
}

check_wifi_connection() {
    # Check if wlan0 has an IP address and internet connectivity
    if ip addr show wlan0 | grep -q "inet "; then
        if ping -c 1 -W 2 8.8.8.8 &>/dev/null; then
            return 0  # Connected
        fi
    fi
    return 1  # Not connected
}

start_access_point() {
    log_message "Starting Access Point mode..."
    
    # Stop any existing services
    sudo systemctl stop hostapd 2>/dev/null
    sudo systemctl stop dnsmasq 2>/dev/null
    
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
EOF
    
    sudo mv /tmp/dnsmasq.conf /etc/dnsmasq.conf
    
    # Start services
    sudo systemctl unmask hostapd
    sudo systemctl start dnsmasq
    sudo systemctl start hostapd
    
    log_message "Access Point started: SSID=${AP_SSID}, Password=${AP_PASSWORD}"
    log_message "Connect to the AP and visit http://${AP_IP} or http://cubsscoreboard.local"
    
    # Keep AP mode running until WiFi is configured
    while true; do
        sleep 30
        # Check if we now have a proper WiFi connection
        if check_wifi_connection; then
            log_message "WiFi connection established, stopping AP mode..."
            stop_access_point
            return 0
        fi
    done
}

stop_access_point() {
    log_message "Stopping Access Point mode..."
    
    # Stop services
    sudo systemctl stop hostapd
    sudo systemctl stop dnsmasq
    
    # Restart normal networking
    sudo systemctl restart dhcpcd
    sudo wpa_cli -i wlan0 reconfigure
    
    log_message "Access Point stopped, returning to client mode"
}

# Main logic
log_message "WiFi Manager starting..."

# Try to connect to configured WiFi
log_message "Attempting to connect to configured WiFi network..."

attempt=0
while [ $attempt -lt $MAX_WIFI_ATTEMPTS ]; do
    if check_wifi_connection; then
        log_message "Successfully connected to WiFi"
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
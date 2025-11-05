#!/bin/bash
# Offline connectivity fix - works without internet
# Fixes Avahi/mDNS and SSH configuration using existing packages

set -e

echo "======================================"
echo "Cubs Scoreboard Connectivity Fix (Offline Mode)"
echo "======================================"
echo ""
echo "This version works without internet connection"
echo "It will configure existing services only"
echo ""

# Must run as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (use sudo)"
    exit 1
fi

echo "Step 1: Checking for required services..."
# Check if services exist
if ! systemctl list-unit-files | grep -q avahi-daemon; then
    echo "WARNING: Avahi not installed. This fix requires avahi-daemon."
    echo "You'll need internet to install it with: sudo apt-get install avahi-daemon"
else
    echo "✓ Avahi daemon found"
fi

if ! systemctl list-unit-files | grep -q ssh; then
    echo "WARNING: SSH service not found"
else
    echo "✓ SSH service found"
fi

echo ""
echo "Step 2: Configuring Avahi daemon..."
# Enable and start Avahi (if installed)
if systemctl list-unit-files | grep -q avahi-daemon; then
    systemctl enable avahi-daemon 2>/dev/null || true

    # Check if config exists, create minimal one if not
    if [ ! -f /etc/avahi/avahi-daemon.conf ]; then
        echo "Creating Avahi configuration..."
        mkdir -p /etc/avahi
        cat > /etc/avahi/avahi-daemon.conf << 'EOF'
[server]
use-ipv4=yes
use-ipv6=yes
enable-dbus=yes
ratelimit-interval-usec=1000000
ratelimit-burst=1000

[wide-area]
enable-wide-area=yes

[publish]
publish-addresses=yes
publish-hinfo=yes
publish-workstation=yes
publish-domain=yes

[reflector]
enable-reflector=no

[rlimits]
EOF
    fi

    systemctl start avahi-daemon 2>/dev/null || systemctl restart avahi-daemon 2>/dev/null || true
    echo "✓ Avahi configured"
else
    echo "⚠ Skipping Avahi configuration (not installed)"
fi

echo ""
echo "Step 3: Configuring SSH service..."
# Enable SSH
if systemctl list-unit-files | grep -q ssh; then
    systemctl enable ssh 2>/dev/null || true

    # Add network dependency to SSH service
    mkdir -p /etc/systemd/system/ssh.service.d/
    cat > /etc/systemd/system/ssh.service.d/network-dependency.conf << 'EOF'
[Unit]
After=network-online.target avahi-daemon.service
Wants=network-online.target
EOF
    echo "✓ SSH network dependency configured"
else
    echo "⚠ Skipping SSH configuration (not installed)"
fi

echo ""
echo "Step 4: Updating WiFi manager service..."
# Update wifi-manager service if it exists in home directory
if [ -f /home/pi/wifi-manager.service ]; then
    cp /home/pi/wifi-manager.service /etc/systemd/system/wifi-manager.service
    echo "✓ Updated wifi-manager.service"
else
    echo "⚠ wifi-manager.service not found in /home/pi"
fi

if [ -f /home/pi/wifi-web-config.service ]; then
    cp /home/pi/wifi-web-config.service /etc/systemd/system/wifi-web-config.service
    echo "✓ Updated wifi-web-config.service"
fi

echo ""
echo "Step 5: Fixing dhcpcd configuration..."
# Remove problematic denyinterfaces that breaks client mode
if [ -f /etc/dhcpcd.conf ]; then
    if grep -q "denyinterfaces wlan0" /etc/dhcpcd.conf; then
        echo "Removing denyinterfaces wlan0 from dhcpcd.conf..."
        sed -i '/denyinterfaces wlan0/d' /etc/dhcpcd.conf
        sed -i '/Allow manual wlan0 configuration for AP mode/d' /etc/dhcpcd.conf
        echo "✓ Fixed dhcpcd.conf"
    else
        echo "✓ dhcpcd.conf looks good"
    fi
fi

echo ""
echo "Step 6: Ensuring wpa_supplicant is configured..."
systemctl enable wpa_supplicant 2>/dev/null || true

echo ""
echo "Step 7: Reloading systemd and restarting services..."
systemctl daemon-reload

# Restart services (only if they're installed)
if systemctl list-unit-files | grep -q avahi-daemon; then
    systemctl restart avahi-daemon 2>/dev/null || true
    sleep 2
fi

if systemctl list-unit-files | grep -q ssh; then
    systemctl restart ssh 2>/dev/null || true
fi

echo ""
echo "Step 8: Testing configuration..."
HOSTNAME=$(hostname)
IP=$(hostname -I | awk '{print $1}')

echo "✓ Hostname: $HOSTNAME"
echo "✓ IP Address: $IP"
echo ""

if systemctl is-active --quiet avahi-daemon 2>/dev/null; then
    echo "✓ Avahi daemon is running"
else
    echo "⚠ Avahi daemon is not running (may need to install it)"
fi

if systemctl is-active --quiet ssh 2>/dev/null; then
    echo "✓ SSH service is running"
else
    echo "⚠ SSH service is not running"
fi

echo ""
echo "======================================"
echo "✓ Offline fix completed!"
echo "======================================"
echo ""
echo "Next steps:"
echo "1. Configure your WiFi network via the web interface:"
echo "   http://10.0.0.1/admin"
echo ""
echo "2. After connecting to WiFi, you should be able to access via:"
echo "   ssh pi@${HOSTNAME}.local"
echo ""
echo "NOTE: If avahi-daemon wasn't installed, you'll need to:"
echo "  - Connect via ethernet for internet access"
echo "  - Run: sudo apt-get install avahi-daemon avahi-utils libnss-mdns"
echo "  - Then run this script again"
echo ""

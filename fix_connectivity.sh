#!/bin/bash
# Fix connectivity issues on Cubs Scoreboard Pi
# This script ensures Avahi, SSH, and network services start properly on boot

set -e

echo "======================================"
echo "Cubs Scoreboard Connectivity Fix"
echo "======================================"
echo ""

# Must run as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (use sudo)"
    exit 1
fi

echo "Step 1: Installing required packages..."
apt-get update -qq
apt-get install -y avahi-daemon avahi-utils libnss-mdns openssh-server

echo ""
echo "Step 2: Configuring Avahi daemon..."
# Enable and start Avahi
systemctl enable avahi-daemon
systemctl start avahi-daemon || systemctl restart avahi-daemon

# Check Avahi configuration
if [ ! -f /etc/avahi/avahi-daemon.conf ]; then
    echo "Creating default Avahi configuration..."
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
    systemctl restart avahi-daemon
fi

echo ""
echo "Step 3: Configuring SSH service..."
# Enable SSH
systemctl enable ssh
systemctl start ssh || systemctl restart ssh

# Ensure SSH starts after network is online
SSH_SERVICE="/lib/systemd/system/ssh.service"
if [ -f "$SSH_SERVICE" ]; then
    if ! grep -q "After=network-online.target" "$SSH_SERVICE"; then
        echo "Adding network dependency to SSH service..."
        # Create override directory
        mkdir -p /etc/systemd/system/ssh.service.d/
        cat > /etc/systemd/system/ssh.service.d/network-dependency.conf << 'EOF'
[Unit]
After=network-online.target
Wants=network-online.target
EOF
    fi
fi

echo ""
echo "Step 4: Updating WiFi manager service files..."
# Copy updated service files from /home/pi if they exist
if [ -f /home/pi/wifi-manager.service ]; then
    cp /home/pi/wifi-manager.service /etc/systemd/system/wifi-manager.service
    echo "✓ Updated wifi-manager.service"
fi

if [ -f /home/pi/wifi-web-config.service ]; then
    cp /home/pi/wifi-web-config.service /etc/systemd/system/wifi-web-config.service
    echo "✓ Updated wifi-web-config.service"
fi

echo ""
echo "Step 5: Reloading systemd and restarting services..."
systemctl daemon-reload

# Restart Avahi to ensure it's advertising the hostname
systemctl restart avahi-daemon
sleep 2

# Restart SSH
systemctl restart ssh

echo ""
echo "Step 6: Testing connectivity..."
echo ""

HOSTNAME=$(hostname)
IP=$(hostname -I | awk '{print $1}')

echo "✓ Hostname: $HOSTNAME"
echo "✓ IP Address: $IP"
echo ""

if systemctl is-active --quiet avahi-daemon; then
    echo "✓ Avahi daemon is running"
else
    echo "✗ WARNING: Avahi daemon is not running!"
fi

if systemctl is-active --quiet ssh; then
    echo "✓ SSH service is running"
else
    echo "✗ WARNING: SSH service is not running!"
fi

echo ""
echo "======================================"
echo "Fix applied successfully!"
echo "======================================"
echo ""
echo "You should now be able to access the Pi via:"
echo "  - ssh pi@${HOSTNAME}.local"
echo "  - http://${HOSTNAME}.local/admin"
echo "  - Direct IP: ${IP}"
echo ""
echo "If you still have issues after reboot, run:"
echo "  sudo bash diagnose_connectivity.sh"
echo ""

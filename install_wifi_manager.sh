#!/bin/bash
# Installation script for Cubs Scoreboard WiFi Manager
# This script fixes WiFi persistence and mDNS issues

set -e  # Exit on any error

echo "================================================"
echo "Cubs Scoreboard WiFi Manager Installation"
echo "================================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Error: This script must be run as root (use sudo)${NC}"
    exit 1
fi

echo -e "${GREEN}Step 1: Installing required packages...${NC}"
apt-get update
apt-get install -y \
    hostapd \
    dnsmasq \
    avahi-daemon \
    wireless-tools \
    wpasupplicant \
    python3-flask

echo ""
echo -e "${GREEN}Step 2: Configuring Avahi (mDNS) for hostname.local access...${NC}"

# Enable Avahi service
systemctl enable avahi-daemon
systemctl start avahi-daemon

# Ensure Avahi configuration is correct
if [ ! -f /etc/avahi/avahi-daemon.conf.backup ]; then
    cp /etc/avahi/avahi-daemon.conf /etc/avahi/avahi-daemon.conf.backup
fi

cat > /etc/avahi/avahi-daemon.conf << 'EOF'
[server]
use-ipv4=yes
use-ipv6=yes
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

echo ""
echo -e "${GREEN}Step 3: Configuring network services...${NC}"

# Enable and configure dhcpcd
systemctl enable dhcpcd
systemctl start dhcpcd

# Ensure wpa_supplicant is enabled for WiFi persistence
systemctl enable wpa_supplicant

# Create default wpa_supplicant.conf if it doesn't exist
if [ ! -f /etc/wpa_supplicant/wpa_supplicant.conf ]; then
    echo -e "${YELLOW}Creating default wpa_supplicant configuration...${NC}"
    cat > /etc/wpa_supplicant/wpa_supplicant.conf << 'EOF'
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=US

EOF
    chmod 600 /etc/wpa_supplicant/wpa_supplicant.conf
fi

# Remove any old denyinterfaces configuration that would break client mode
if grep -q "denyinterfaces wlan0" /etc/dhcpcd.conf; then
    echo -e "${YELLOW}Removing old denyinterfaces configuration from dhcpcd...${NC}"
    sed -i '/denyinterfaces wlan0/d' /etc/dhcpcd.conf
    sed -i '/Allow manual wlan0 configuration for AP mode/d' /etc/dhcpcd.conf
fi

echo ""
echo -e "${GREEN}Step 4: Installing WiFi Manager files...${NC}"

# Copy WiFi manager script
cp wifi_manager.sh /home/pi/wifi_manager.sh
chmod +x /home/pi/wifi_manager.sh
chown pi:pi /home/pi/wifi_manager.sh

# Copy web config server
cp wifi_config_server.py /home/pi/wifi_config_server.py
chmod +x /home/pi/wifi_config_server.py
chown pi:pi /home/pi/wifi_config_server.py

# Create log directory if it doesn't exist
mkdir -p /var/log
touch /var/log/wifi_manager.log
chmod 666 /var/log/wifi_manager.log

echo ""
echo -e "${GREEN}Step 5: Installing systemd services...${NC}"

# Install WiFi manager service
cp wifi-manager.service /etc/systemd/system/wifi-manager.service
chmod 644 /etc/systemd/system/wifi-manager.service

# Install web config service
cp wifi-web-config.service /etc/systemd/system/wifi-web-config.service
chmod 644 /etc/systemd/system/wifi-web-config.service

# Reload systemd
systemctl daemon-reload

# Enable services
systemctl enable wifi-manager.service
systemctl enable wifi-web-config.service

echo ""
echo -e "${GREEN}Step 6: Configuring hostapd and dnsmasq defaults...${NC}"

# Configure hostapd defaults
if [ ! -f /etc/default/hostapd ]; then
    echo 'DAEMON_CONF="/etc/hostapd/hostapd.conf"' > /etc/default/hostapd
fi

# Disable hostapd from starting automatically (WiFi manager controls it)
systemctl disable hostapd 2>/dev/null || true
systemctl disable dnsmasq 2>/dev/null || true

# Stop any running AP services
systemctl stop hostapd 2>/dev/null || true
systemctl stop dnsmasq 2>/dev/null || true

echo ""
echo -e "${GREEN}Step 7: Configuring SSH service...${NC}"

# Ensure SSH is installed and enabled
apt-get install -y openssh-server avahi-utils libnss-mdns

# Enable SSH to start on boot
systemctl enable ssh

# Add network dependency to SSH service
mkdir -p /etc/systemd/system/ssh.service.d/
cat > /etc/systemd/system/ssh.service.d/network-dependency.conf << 'EOF'
[Unit]
After=network-online.target avahi-daemon.service
Wants=network-online.target
EOF

systemctl daemon-reload
systemctl restart ssh

echo ""
echo -e "${GREEN}Step 8: Setting up hostname configuration...${NC}"

# Get current hostname
HOSTNAME=$(hostname)
echo "Current hostname: $HOSTNAME"

# Ensure hostname is properly set in all locations
echo "$HOSTNAME" > /etc/hostname
sed -i "s/127.0.1.1.*/127.0.1.1\t$HOSTNAME/" /etc/hosts

# Make sure avahi is aware of the hostname
hostnamectl set-hostname "$HOSTNAME"

echo ""
echo -e "${GREEN}Step 9: Testing Avahi mDNS...${NC}"

# Test Avahi
avahi-browse -a -t | head -n 5

echo ""
echo -e "${GREEN}Step 10: Starting services...${NC}"

# Start the services
systemctl restart avahi-daemon
systemctl start wifi-web-config.service

# Start WiFi manager (it will handle AP mode if no WiFi configured)
systemctl start wifi-manager.service

echo ""
echo "================================================"
echo -e "${GREEN}Installation Complete!${NC}"
echo "================================================"
echo ""
echo "Your Cubs Scoreboard WiFi Manager is now installed."
echo ""
echo "Access the admin interface:"
echo "  - Via hostname: http://${HOSTNAME}.local/admin"
echo "  - Via IP: http://$(hostname -I | awk '{print $1}')/admin"
echo ""
echo "If not connected to WiFi, the system will automatically"
echo "create an access point:"
echo "  - SSID: CubsScoreboard-Setup"
echo "  - Password: gocubsgo2024"
echo "  - Access: http://10.0.0.1/admin"
echo ""
echo -e "${YELLOW}Important: The mDNS hostname (${HOSTNAME}.local) will work${NC}"
echo -e "${YELLOW}after connecting to WiFi. Avahi has been configured to${NC}"
echo -e "${YELLOW}restart automatically when switching networks.${NC}"
echo ""
echo "To check service status:"
echo "  sudo systemctl status wifi-manager"
echo "  sudo systemctl status wifi-web-config"
echo "  sudo systemctl status avahi-daemon"
echo ""
echo "To view logs:"
echo "  sudo journalctl -u wifi-manager -f"
echo "  sudo journalctl -u wifi-web-config -f"
echo "  cat /var/log/wifi_manager.log"
echo ""

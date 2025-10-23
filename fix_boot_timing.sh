#!/bin/bash
# Updated Fix Script - Addresses Boot Timing Issue
# This fixes the "wlan0 does not exist" problem

echo "=== Cubs Scoreboard WiFi Manager - Boot Timing Fix ==="
echo ""
echo "This update fixes the issue where WiFi doesn't connect on first boot"
echo "because the wlan0 interface isn't ready yet."
echo ""

# Stop services first
echo "1. Stopping WiFi manager service..."
sudo systemctl stop wifi-manager
echo "   ✓ Service stopped"
echo ""

# Backup old files
echo "2. Backing up old files..."
if [ -f /home/pi/wifi_manager.sh ]; then
    sudo cp /home/pi/wifi_manager.sh /home/pi/wifi_manager.sh.backup.$(date +%Y%m%d_%H%M%S)
    echo "   ✓ wifi_manager.sh backed up"
fi

if [ -f /etc/systemd/system/wifi-manager.service ]; then
    sudo cp /etc/systemd/system/wifi-manager.service /etc/systemd/system/wifi-manager.service.backup.$(date +%Y%m%d_%H%M%S)
    echo "   ✓ wifi-manager.service backed up"
fi
echo ""

# Deploy new files
echo "3. Deploying updated files..."
if [ -f ./wifi_manager.sh ]; then
    sudo cp ./wifi_manager.sh /home/pi/wifi_manager.sh
    sudo chmod +x /home/pi/wifi_manager.sh
    sudo chown pi:pi /home/pi/wifi_manager.sh
    echo "   ✓ wifi_manager.sh updated (now waits up to 30 seconds for wlan0)"
else
    echo "   ⚠ wifi_manager.sh not found in current directory"
fi

if [ -f ./wifi-manager.service ]; then
    sudo cp ./wifi-manager.service /etc/systemd/system/wifi-manager.service
    echo "   ✓ wifi-manager.service updated (now waits for network-online.target)"
else
    echo "   ⚠ wifi-manager.service not found in current directory"
fi
echo ""

# Reload systemd
echo "4. Reloading systemd configuration..."
sudo systemctl daemon-reload
echo "   ✓ Systemd reloaded"
echo ""

# Restart the service
echo "5. Restarting WiFi manager service..."
sudo systemctl restart wifi-manager
echo "   ✓ Service restarted"
echo ""

# Check status
echo "6. Checking service status..."
sleep 3
STATUS=$(systemctl is-active wifi-manager)
echo "   Service status: $STATUS"
echo ""

# Get current connection info
echo "7. Current WiFi status:"
CURRENT_SSID=$(iwgetid -r)
CURRENT_IP=$(hostname -I | awk '{print $1}')
HOSTNAME=$(hostname)

if [ -n "$CURRENT_SSID" ]; then
    echo "   ✓ Connected to: $CURRENT_SSID"
    echo "   ✓ IP Address: $CURRENT_IP"
    echo "   ✓ Access admin at: http://${HOSTNAME}.local/admin"
else
    echo "   ⚠ Not currently connected to WiFi"
    echo "   ℹ If in AP mode, connect to 'CubsScoreboard-Setup' and configure WiFi"
fi
echo ""

echo "=== Update Complete! ==="
echo ""
echo "Changes made:"
echo "  • wifi_manager.sh now waits up to 30 seconds for wlan0 interface"
echo "  • wifi-manager.service now depends on network-online.target"
echo "  • Timeout increased from 120s to 180s"
echo ""
echo "Next steps:"
echo "  1. Test with a reboot: sudo reboot"
echo "  2. After reboot, check: journalctl -u wifi-manager -n 50"
echo "  3. Verify it connects to WiFi without entering AP mode"
echo ""
echo "If it still enters AP mode on boot:"
echo "  • Your WiFi may be slow to come online"
echo "  • Check your router is broadcasting on boot"
echo "  • Consider increasing MAX_WIFI_ATTEMPTS in wifi_manager.sh"
echo ""

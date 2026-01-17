#!/bin/bash
# Install script for Cubs Marquee auto-update feature
# Run this once on each Raspberry Pi

echo "Installing Cubs Marquee Auto-Update..."

# Copy the update script
sudo cp /home/pi/auto_update.sh /home/pi/auto_update.sh
sudo chmod +x /home/pi/auto_update.sh

# Install the systemd service and timer
sudo cp /home/pi/marquee-update.service /etc/systemd/system/
sudo cp /home/pi/marquee-update.timer /etc/systemd/system/

# Reload systemd and enable the timer
sudo systemctl daemon-reload
sudo systemctl enable marquee-update.timer
sudo systemctl start marquee-update.timer

echo ""
echo "Auto-update installed successfully!"
echo ""
echo "Status:"
sudo systemctl status marquee-update.timer --no-pager
echo ""
echo "Next scheduled update check:"
sudo systemctl list-timers marquee-update.timer --no-pager
echo ""
echo "To manually trigger an update check:"
echo "  sudo systemctl start marquee-update.service"
echo ""
echo "To view update logs:"
echo "  tail -f /var/log/cubs-scoreboard/auto_update.log"

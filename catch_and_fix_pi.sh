#!/bin/bash
# Script to catch the Pi during boot and apply fixes automatically

PI_USER="pi"
NETWORK="192.168.1.0/24"
MAX_ATTEMPTS=60
ATTEMPT=0

echo "==========================================="
echo "Catching Cubs Scoreboard Pi During Boot"
echo "==========================================="
echo ""
echo "This script will:"
echo "1. Scan for the Pi on your network"
echo "2. Automatically connect when found"
echo "3. Transfer and apply the connectivity fix"
echo ""
echo "Make sure you've restarted the Pi before running this!"
echo ""
echo "Scanning network $NETWORK..."
echo "Press Ctrl+C to cancel"
echo ""

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    ATTEMPT=$((ATTEMPT + 1))
    echo -n "Attempt $ATTEMPT/$MAX_ATTEMPTS: "

    # Scan for Pi - look for cubsmarquee or raspberrypi or common Pi MAC addresses
    PI_IP=$(nmap -sn $NETWORK 2>/dev/null | grep -B 2 -i "raspberry\|b8:27:eb\|dc:a6:32\|e4:5f:01" | grep -oE "192\.168\.[0-9]+\.[0-9]+" | head -1)

    # Also try to ping cubsmarquee.local directly
    if [ -z "$PI_IP" ]; then
        PI_IP=$(ping -c 1 -W 1 cubsmarquee.local 2>/dev/null | grep -oE "192\.168\.[0-9]+\.[0-9]+" | head -1)
    fi

    if [ -n "$PI_IP" ]; then
        echo "✓ FOUND Pi at $PI_IP!"
        echo ""

        # Test if SSH is accessible
        echo "Testing SSH connection..."
        if ssh -o ConnectTimeout=3 -o StrictHostKeyChecking=no -o PasswordAuthentication=no ${PI_USER}@${PI_IP} "echo connected" 2>/dev/null | grep -q "connected"; then
            echo "✓ SSH is accessible!"
            echo ""

            echo "Transferring fix files..."
            scp -o ConnectTimeout=10 fix_connectivity.sh diagnose_connectivity.sh wifi-manager.service ${PI_USER}@${PI_IP}:~/ 2>/dev/null

            if [ $? -eq 0 ]; then
                echo "✓ Files transferred!"
                echo ""
                echo "Running fix script on Pi..."
                ssh -t ${PI_USER}@${PI_IP} "chmod +x fix_connectivity.sh && sudo ./fix_connectivity.sh"

                echo ""
                echo "==========================================="
                echo "✓ Fix applied successfully!"
                echo "==========================================="
                echo ""
                echo "The Pi will now reboot. Wait 2 minutes, then try:"
                echo "  ssh pi@cubsmarquee.local"
                echo ""
                exit 0
            else
                echo "✗ File transfer failed (authentication required?)"
                echo ""
                echo "Manually connect with: ssh pi@${PI_IP}"
                echo "Then run:"
                echo "  cd /Users/ryanpate/cubsmarquee"
                echo "  scp fix_connectivity.sh diagnose_connectivity.sh wifi-manager.service pi@${PI_IP}:~/"
                exit 1
            fi
        else
            echo "SSH not ready yet, will keep trying..."
        fi
    else
        echo "Pi not found yet, waiting..."
    fi

    sleep 2
done

echo ""
echo "==========================================="
echo "Could not find Pi after $MAX_ATTEMPTS attempts"
echo "==========================================="
echo ""
echo "Suggestions:"
echo "1. Make sure the Pi is powered on and restarting"
echo "2. Check that it's connected to your network via WiFi or ethernet"
echo "3. Try running this script again"
echo "4. Check your router's admin page for connected devices"
echo ""

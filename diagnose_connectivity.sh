#!/bin/bash
# Connectivity Diagnostic Script for Cubs Scoreboard
# Run this on the Pi to diagnose network/SSH connectivity issues

echo "======================================"
echo "Cubs Scoreboard Connectivity Diagnostic"
echo "======================================"
echo ""

# Check network interface
echo "=== Network Interface Status ==="
ip addr show wlan0
echo ""

# Check WiFi connection
echo "=== WiFi Connection ==="
iwgetid -r
echo ""

# Check if we have internet
echo "=== Internet Connectivity ==="
if ping -c 2 8.8.8.8 &>/dev/null; then
    echo "✓ Internet connection working"
else
    echo "✗ No internet connection"
fi
echo ""

# Check Avahi daemon
echo "=== Avahi Daemon (mDNS/.local hostname) ==="
if systemctl is-active --quiet avahi-daemon; then
    echo "✓ Avahi daemon is running"
else
    echo "✗ Avahi daemon is NOT running"
fi

if systemctl is-enabled --quiet avahi-daemon; then
    echo "✓ Avahi daemon is enabled (will start on boot)"
else
    echo "✗ Avahi daemon is NOT enabled (won't start on boot)"
fi
echo ""

# Check SSH service
echo "=== SSH Service ==="
if systemctl is-active --quiet ssh; then
    echo "✓ SSH service is running"
else
    echo "✗ SSH service is NOT running"
fi

if systemctl is-enabled --quiet ssh; then
    echo "✓ SSH service is enabled (will start on boot)"
else
    echo "✗ SSH service is NOT enabled (won't start on boot)"
fi
echo ""

# Check hostname
echo "=== Hostname Configuration ==="
echo "Hostname: $(hostname)"
echo "Should be accessible at: $(hostname).local"
echo ""

# Test mDNS resolution locally
echo "=== Testing mDNS Resolution ==="
if command -v avahi-resolve &>/dev/null; then
    avahi-resolve -n $(hostname).local
else
    echo "avahi-resolve command not available"
fi
echo ""

# Check service dependencies
echo "=== Service Status ==="
echo "WiFi Manager:"
systemctl status wifi-manager --no-pager | head -5
echo ""
echo "WiFi Web Config:"
systemctl status wifi-web-config --no-pager | head -5
echo ""

# Check recent journal errors
echo "=== Recent System Errors ==="
journalctl -p err -n 20 --no-pager --since "5 minutes ago"
echo ""

echo "======================================"
echo "Diagnostic complete!"
echo "======================================"

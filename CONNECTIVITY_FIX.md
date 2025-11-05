# Fix for SSH/mDNS Connectivity Issues After Reboot

## Problem
After rebooting the Raspberry Pi, you can't reach it via `ssh pi@cubsmarquee.local` or FTP.

## Root Causes Identified

1. **Avahi daemon (mDNS) not starting properly on boot** - This service provides the `.local` hostname resolution
2. **SSH service not waiting for network to be ready** - SSH may try to start before network is available
3. **Service dependency issues** - WiFi manager wasn't explicitly requiring Avahi to run
4. **Potential dhcpcd misconfiguration** - Old configuration may have blocked wlan0 management

## Solutions Provided

### Quick Fix (If you can access the Pi now)

1. **Transfer the files to your Pi:**
   ```bash
   # From your Mac, copy the files to the Pi (replace with your Pi's current IP)
   scp fix_connectivity.sh diagnose_connectivity.sh wifi-manager.service pi@<PI_IP_ADDRESS>:~/
   ```

2. **Run the fix script on the Pi:**
   ```bash
   ssh pi@<PI_IP_ADDRESS>
   chmod +x fix_connectivity.sh diagnose_connectivity.sh
   sudo ./fix_connectivity.sh
   ```

3. **Reboot and test:**
   ```bash
   sudo reboot
   ```

   After reboot (wait 2 minutes), try:
   ```bash
   ssh pi@cubsmarquee.local
   ```

### Complete Reinstall (Recommended)

If you have access to the Pi, run the updated installation script:

1. **Transfer all files to the Pi:**
   ```bash
   # From your Mac
   scp wifi-manager.service wifi-web-config.service wifi_manager.sh \
       wifi_config_server.py install_wifi_manager.sh \
       diagnose_connectivity.sh fix_connectivity.sh pi@<PI_IP_ADDRESS>:~/
   ```

2. **Run the installation script:**
   ```bash
   ssh pi@<PI_IP_ADDRESS>
   cd ~
   chmod +x install_wifi_manager.sh
   sudo ./install_wifi_manager.sh
   ```

3. **Reboot and test:**
   ```bash
   sudo reboot
   ```

### If You Can't Access the Pi At All

1. **Connect a monitor and keyboard to the Pi**
2. **Login directly** (user: pi)
3. **Check your IP address:**
   ```bash
   hostname -I
   ```
4. **Use that IP to SSH in and follow the Quick Fix steps above**

### Alternative: Find the Pi's IP on Your Network

If you can't connect via hostname but the Pi is on your network:

```bash
# On your Mac, scan your network (replace 192.168.1 with your network prefix)
nmap -sn 192.168.1.0/24 | grep -B 2 "Raspberry Pi"

# Or use arp
arp -a | grep -i "b8:27:eb\|dc:a6:32\|e4:5f:01"
```

Then SSH using the IP address you find.

## What Was Fixed

### 1. Updated wifi-manager.service
- Added `Requires=avahi-daemon.service` to ensure Avahi always runs
- Added `After=avahi-daemon.service` for proper startup order
- Added `Wants=avahi-daemon.service` to declare the dependency

### 2. SSH Service Configuration
- Added network dependency so SSH waits for network to be ready
- Ensured SSH is enabled to start on boot
- Added Avahi dependency to SSH service

### 3. Fixed dhcpcd Configuration
- Removed problematic `denyinterfaces wlan0` that prevented WiFi client mode
- dhcpcd now properly manages wlan0 in client mode

### 4. Added Diagnostic Tools
- `diagnose_connectivity.sh` - Run this to check what's wrong
- `fix_connectivity.sh` - Quick fix script for common issues

## Verification Steps

After applying the fix and rebooting, verify everything works:

1. **Check services are running:**
   ```bash
   sudo systemctl status avahi-daemon
   sudo systemctl status ssh
   sudo systemctl status wifi-manager
   ```

2. **Test mDNS resolution:**
   ```bash
   avahi-resolve -n cubsmarquee.local
   ```

3. **Test from another machine:**
   ```bash
   ping cubsmarquee.local
   ssh pi@cubsmarquee.local
   ```

## Troubleshooting

If you still have issues after applying the fix:

1. **Run the diagnostic script:**
   ```bash
   sudo bash ~/diagnose_connectivity.sh
   ```

2. **Check WiFi connection:**
   ```bash
   iwgetid -r  # Should show your WiFi network name
   ip addr show wlan0  # Should show an IP address
   ```

3. **Check Avahi is advertising:**
   ```bash
   avahi-browse -a -t | grep cubsmarquee
   ```

4. **View service logs:**
   ```bash
   sudo journalctl -u avahi-daemon -n 50
   sudo journalctl -u wifi-manager -n 50
   sudo journalctl -u ssh -n 50
   ```

## Files Modified/Created

- ✅ `wifi-manager.service` - Updated with Avahi dependencies
- ✅ `install_wifi_manager.sh` - Updated to configure SSH and fix dhcpcd
- ✅ `fix_connectivity.sh` - New quick fix script
- ✅ `diagnose_connectivity.sh` - New diagnostic script

## Prevention

These fixes ensure that on every boot:
1. Avahi daemon starts and is healthy before WiFi manager runs
2. SSH service waits for network to be ready
3. The hostname `cubsmarquee.local` is properly advertised on the network
4. Services have proper dependencies to start in the correct order

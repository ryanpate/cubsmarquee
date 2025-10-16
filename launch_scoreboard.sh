#!/bin/bash
# Cubs LED Scoreboard Launch Script

# Configuration - CORRECTED PATHS
SCOREBOARD_DIR="/home/pi"  # Your files are here
LOG_DIR="/home/pi/scoreboard_logs"
PYTHON_PATH="/usr/bin/python3"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Set up logging with timestamp
LOG_FILE="$LOG_DIR/scoreboard_$(date +%Y%m%d_%H%M%S).log"
ERROR_LOG="$LOG_DIR/scoreboard_error_$(date +%Y%m%d_%H%M%S).log"

echo "Starting Cubs LED Scoreboard at $(date)" | tee "$LOG_FILE"

# Change to scoreboard directory
cd "$SCOREBOARD_DIR" || {
    echo "Error: Cannot access scoreboard directory: $SCOREBOARD_DIR" | tee -a "$ERROR_LOG"
    exit 1
}

echo "Working directory: $(pwd)" >> "$LOG_FILE"
echo "Python files found:" >> "$LOG_FILE"
ls -la *.py >> "$LOG_FILE"

# Wait for network to be available
echo "Waiting for network..." | tee -a "$LOG_FILE"

# First, wait for WiFi manager to complete its process
echo "Waiting for WiFi manager to establish connection..." | tee -a "$LOG_FILE"
wifi_counter=0
while [ $wifi_counter -lt 90 ]; do
    # Check if we have a WiFi connection
    if iwgetid -r &>/dev/null; then
        echo "WiFi connected to: $(iwgetid -r)" | tee -a "$LOG_FILE"
        break
    fi
    
    # If wifi-manager service failed, it means we're in AP mode
    if ! systemctl is-active --quiet wifi-manager 2>/dev/null; then
        echo "WiFi manager is in AP mode - waiting for configuration..." | tee -a "$LOG_FILE"
        echo "Connect to 'CubsScoreboard-Setup' and visit 10.0.0.1/admin to configure WiFi" | tee -a "$LOG_FILE"
        sleep 10
        wifi_counter=$((wifi_counter + 10))
        continue
    fi
    
    sleep 2
    wifi_counter=$((wifi_counter + 2))
done

if [ $wifi_counter -ge 90 ]; then
    echo "WiFi connection timeout - network may need configuration" | tee -a "$LOG_FILE"
fi

# Now wait for actual internet connectivity
echo "Verifying internet connectivity..." | tee -a "$LOG_FILE"
counter=0
while ! ping -c 1 8.8.8.8 &>/dev/null; do
    echo "Internet not ready, waiting..." | tee -a "$LOG_FILE"
    sleep 2
    counter=$((counter + 1))
    if [ $counter -gt 30 ]; then
        echo "Internet timeout, proceeding anyway..." | tee -a "$LOG_FILE"
        break
    fi
done

# Verify we can reach MLB API
echo "Testing MLB API connectivity..." | tee -a "$LOG_FILE"
api_counter=0
while ! ping -c 1 statsapi.mlb.com &>/dev/null; do
    echo "MLB API not reachable, waiting..." | tee -a "$LOG_FILE"
    sleep 3
    api_counter=$((api_counter + 1))
    if [ $api_counter -gt 20 ]; then
        echo "MLB API timeout - scoreboard may not function properly" | tee -a "$LOG_FILE"
        break
    fi
done

echo "Network check complete" | tee -a "$LOG_FILE"

# Launch the scoreboard with proper permissions for GPIO access
echo "Launching scoreboard application..." | tee -a "$LOG_FILE"
sudo -E "$PYTHON_PATH" main.py >> "$LOG_FILE" 2>> "$ERROR_LOG"

# If the scoreboard exits, log the event
echo "Scoreboard exited at $(date)" | tee -a "$LOG_FILE"
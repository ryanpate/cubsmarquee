#!/bin/bash
# Cubs LED Scoreboard Launch Script

# Configuration - CORRECTED PATHS
SCOREBOARD_DIR="/home/pi"  # Your files are here
LOG_DIR="/home/pi/scoreboard_logs"
PYTHON_PATH="/usr/bin/python3"

# Log rotation settings
MAX_LOG_FILES=5  # Keep only the last 5 log files
MAX_LOG_SIZE_MB=10  # Rotate logs larger than 10MB

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Function to rotate old logs
rotate_logs() {
    echo "Checking for old logs to rotate..."
    
    # Count number of regular log files
    log_count=$(ls -1 "$LOG_DIR"/scoreboard_[0-9]*.log 2>/dev/null | wc -l)
    
    # If we have more than MAX_LOG_FILES, delete the oldest ones
    if [ $log_count -gt $MAX_LOG_FILES ]; then
        files_to_delete=$((log_count - MAX_LOG_FILES))
        echo "Found $log_count log files. Removing $files_to_delete oldest files..."
        ls -1t "$LOG_DIR"/scoreboard_[0-9]*.log | tail -n $files_to_delete | xargs rm -f
    fi
    
    # Count number of error log files
    error_log_count=$(ls -1 "$LOG_DIR"/scoreboard_error_*.log 2>/dev/null | wc -l)
    
    # If we have more than MAX_LOG_FILES error logs, delete the oldest ones
    if [ $error_log_count -gt $MAX_LOG_FILES ]; then
        files_to_delete=$((error_log_count - MAX_LOG_FILES))
        echo "Found $error_log_count error log files. Removing $files_to_delete oldest files..."
        ls -1t "$LOG_DIR"/scoreboard_error_*.log | tail -n $files_to_delete | xargs rm -f
    fi
    
    # Check for large log files and compress them
    find "$LOG_DIR" -name "scoreboard*.log" -size +${MAX_LOG_SIZE_MB}M -exec gzip {} \;
    
    # Remove compressed logs older than 7 days
    find "$LOG_DIR" -name "scoreboard*.log.gz" -mtime +7 -delete
    
    echo "Log rotation complete."
}

# Rotate old logs before starting
rotate_logs

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

# Set capability on Python to avoid realtime priority warning
# Get the actual Python binary path (not just symlink)
echo "Setting Python capabilities..." | tee -a "$LOG_FILE"
PYTHON_REAL_PATH=$(readlink -f "$PYTHON_PATH")
echo "Python path: $PYTHON_PATH -> $PYTHON_REAL_PATH" | tee -a "$LOG_FILE"

# Set capabilities on both the symlink and real binary
sudo setcap 'cap_sys_nice+eip' "$PYTHON_PATH" 2>/dev/null
sudo setcap 'cap_sys_nice+eip' "$PYTHON_REAL_PATH" 2>/dev/null
sudo setcap 'cap_sys_nice+eip' /usr/bin/python3.9 2>/dev/null

if [ $? -eq 0 ]; then
    echo "✓ Python capabilities set successfully" | tee -a "$LOG_FILE"
else
    echo "⚠ Warning: Could not set Python capabilities (will still work with sudo)" | tee -a "$LOG_FILE"
fi

# Launch the scoreboard with proper permissions for GPIO access
echo "Launching scoreboard application..." | tee -a "$LOG_FILE"
sudo -E "$PYTHON_PATH" main.py >> "$LOG_FILE" 2>> "$ERROR_LOG"

# If the scoreboard exits, log the event and rotate logs
echo "Scoreboard exited at $(date)" | tee -a "$LOG_FILE"
rotate_logs
#!/bin/bash
# Auto-update script for Cubs Marquee
# Checks GitHub for updates, pulls changes, and reboots if needed

REPO_DIR="/home/pi"
LOG_FILE="/var/log/cubs-scoreboard/auto_update.log"
LOCK_FILE="/tmp/marquee_update.lock"

# Ensure only one instance runs
if [ -f "$LOCK_FILE" ]; then
    echo "$(date): Update already in progress, exiting" >> "$LOG_FILE"
    exit 0
fi
touch "$LOCK_FILE"
trap "rm -f $LOCK_FILE" EXIT

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S'): $1" >> "$LOG_FILE"
}

log "Starting update check..."

cd "$REPO_DIR" || { log "ERROR: Cannot cd to $REPO_DIR"; exit 1; }

# Fetch latest from remote without merging
git fetch origin main 2>> "$LOG_FILE"

# Check if there are updates
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
    log "Already up to date (commit: ${LOCAL:0:7})"
    exit 0
fi

log "Updates available! Local: ${LOCAL:0:7}, Remote: ${REMOTE:0:7}"

# Stop the scoreboard service before updating
log "Stopping cubs-scoreboard service..."
sudo systemctl stop cubs-scoreboard 2>> "$LOG_FILE"

# Pull the latest changes
log "Pulling updates..."
git pull origin main 2>> "$LOG_FILE"

if [ $? -eq 0 ]; then
    log "Pull successful! New commit: $(git rev-parse --short HEAD)"

    # Check if requirements.txt changed and install new dependencies
    if git diff --name-only "$LOCAL" "$REMOTE" | grep -q "requirements.txt"; then
        log "requirements.txt changed, installing dependencies..."
        pip3 install -r requirements.txt 2>> "$LOG_FILE"
    fi

    log "Rebooting to apply updates..."
    sudo reboot
else
    log "ERROR: Git pull failed!"
    # Restart the service even if pull failed
    sudo systemctl start cubs-scoreboard
    exit 1
fi

#!/bin/bash
# Nightly self-update for the Cubs Marquee (run by marquee-update.timer at 4 AM).
#
# Keeps a private clone of the GitHub repo at CLONE_DIR, and when a new
# commit lands on main: syntax-checks the Python, syncs all git-tracked
# files into /home/pi (the live deploy root), records the deployed commit,
# and reboots. Untracked files in /home/pi (config.json, logs, caches)
# are never touched. Replaced files are kept in BACKUP_DIR for rollback.
#
# Manual run: sudo /home/pi/auto_update.sh

REPO_URL="https://github.com/ryanpate/cubsmarquee.git"
CLONE_DIR="/home/pi/.marquee-repo"
DEPLOY_DIR="/home/pi"
MARKER_FILE="/home/pi/.deployed_commit"
BACKUP_DIR="/home/pi/.update_backup"
LOG_FILE="/var/log/cubs-scoreboard/auto_update.log"
LOCK_FILE="/tmp/marquee_update.lock"

mkdir -p "$(dirname "$LOG_FILE")"

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

# Get (or create) the private clone used as the sync source
if [ ! -d "$CLONE_DIR/.git" ]; then
    log "No clone at $CLONE_DIR, cloning..."
    rm -rf "$CLONE_DIR"
    if ! git clone --branch main "$REPO_URL" "$CLONE_DIR" 2>> "$LOG_FILE"; then
        log "Clone failed (offline?), will retry tomorrow"
        exit 0
    fi
fi

cd "$CLONE_DIR" || { log "ERROR: Cannot cd to $CLONE_DIR"; exit 1; }

if ! git fetch origin main 2>> "$LOG_FILE"; then
    log "Fetch failed (offline?), will retry tomorrow"
    exit 0
fi

REMOTE=$(git rev-parse origin/main)
DEPLOYED=$(cat "$MARKER_FILE" 2>/dev/null || echo "none")

if [ "$REMOTE" = "$DEPLOYED" ]; then
    log "Already up to date (commit: ${REMOTE:0:7})"
    exit 0
fi

log "Update available! Deployed: ${DEPLOYED:0:7}, Remote: ${REMOTE:0:7}"

git reset --hard "$REMOTE" >> "$LOG_FILE" 2>&1 || { log "ERROR: git reset failed"; exit 1; }

# Refuse to deploy code that doesn't compile
if ! git ls-files -z -- '*.py' | xargs -0 python3 -m py_compile 2>> "$LOG_FILE"; then
    log "ERROR: py_compile failed on ${REMOTE:0:7}, NOT deploying"
    exit 1
fi

# Install new dependencies if requirements.txt changed
if [ "$DEPLOYED" != "none" ] && git cat-file -e "$DEPLOYED" 2>/dev/null; then
    if git diff --name-only "$DEPLOYED" "$REMOTE" | grep -qx "requirements.txt"; then
        log "requirements.txt changed, installing dependencies..."
        pip3 install -r requirements.txt >> "$LOG_FILE" 2>&1
    fi
fi

log "Stopping cubs-scoreboard and syncing files..."
systemctl stop cubs-scoreboard 2>> "$LOG_FILE"

# Sync every git-tracked file into the deploy root. rsync preserves the
# exec bits git tracks (wifi_manager.sh must stay 0755) and creates any
# new directories; replaced versions land in BACKUP_DIR.
rm -rf "$BACKUP_DIR"
if ! git ls-files -z | rsync -a --files-from=- --from0 --backup \
        --backup-dir="$BACKUP_DIR" --chown=pi:pi \
        "$CLONE_DIR/" "$DEPLOY_DIR/" 2>> "$LOG_FILE"; then
    log "ERROR: rsync failed, restarting scoreboard without update"
    systemctl start cubs-scoreboard
    exit 1
fi

echo "$REMOTE" > "$MARKER_FILE"
chown pi:pi "$MARKER_FILE"

log "Deployed ${REMOTE:0:7}, rebooting..."
systemctl reboot

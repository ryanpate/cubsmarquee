#!/bin/bash
# Standalone log cleanup script for Cubs LED Scoreboard
# Can be run manually or via cron for automatic cleanup

LOG_DIR="/home/pi/scoreboard_logs"
MAX_LOG_FILES=5           # Keep only the last 5 uncompressed log files
MAX_LOG_AGE_DAYS=7        # Delete compressed logs older than 7 days
MAX_LOG_SIZE_MB=10        # Compress logs larger than 10MB

echo "=== Cubs Scoreboard Log Cleanup ==="
echo "Started at: $(date)"
echo "Log directory: $LOG_DIR"
echo ""

# Create log directory if it doesn't exist
if [ ! -d "$LOG_DIR" ]; then
    echo "Log directory does not exist. Nothing to clean."
    exit 0
fi

# Count current log files
total_logs=$(ls -1 "$LOG_DIR"/scoreboard_*.log 2>/dev/null | wc -l)
total_compressed=$(ls -1 "$LOG_DIR"/scoreboard_*.log.gz 2>/dev/null | wc -l)
total_error_logs=$(ls -1 "$LOG_DIR"/scoreboard_error_*.log 2>/dev/null | wc -l)

echo "Current log files:"
echo "  - Regular logs: $total_logs"
echo "  - Compressed logs: $total_compressed"
echo "  - Error logs: $total_error_logs"
echo ""

# Step 1: Remove oldest regular log files if we have too many
if [ $total_logs -gt $MAX_LOG_FILES ]; then
    files_to_delete=$((total_logs - MAX_LOG_FILES))
    echo "Removing $files_to_delete oldest log files..."
    ls -1t "$LOG_DIR"/scoreboard_*.log | tail -n $files_to_delete | while read -r file; do
        size=$(du -h "$file" | cut -f1)
        echo "  Deleting: $(basename "$file") ($size)"
        rm -f "$file"
    done
    echo ""
fi

# Step 2: Remove oldest error log files if we have too many
error_logs=$(ls -1 "$LOG_DIR"/scoreboard_error_*.log 2>/dev/null | wc -l)
if [ $error_logs -gt $MAX_LOG_FILES ]; then
    files_to_delete=$((error_logs - MAX_LOG_FILES))
    echo "Removing $files_to_delete oldest error log files..."
    ls -1t "$LOG_DIR"/scoreboard_error_*.log | tail -n $files_to_delete | while read -r file; do
        size=$(du -h "$file" | cut -f1)
        echo "  Deleting: $(basename "$file") ($size)"
        rm -f "$file"
    done
    echo ""
fi

# Step 3: Compress large log files
echo "Checking for large log files to compress (>${MAX_LOG_SIZE_MB}MB)..."
compressed_count=0
find "$LOG_DIR" -name "scoreboard*.log" -size +${MAX_LOG_SIZE_MB}M | while read -r file; do
    size_before=$(du -h "$file" | cut -f1)
    echo "  Compressing: $(basename "$file") ($size_before)"
    gzip "$file"
    size_after=$(du -h "${file}.gz" | cut -f1)
    echo "    → Compressed to: $size_after"
    compressed_count=$((compressed_count + 1))
done

if [ $compressed_count -eq 0 ]; then
    echo "  No large log files found."
fi
echo ""

# Step 4: Remove old compressed logs
echo "Removing compressed logs older than $MAX_LOG_AGE_DAYS days..."
old_compressed=$(find "$LOG_DIR" -name "scoreboard*.log.gz" -mtime +$MAX_LOG_AGE_DAYS)
if [ -n "$old_compressed" ]; then
    echo "$old_compressed" | while read -r file; do
        age_days=$(find "$file" -mtime +$MAX_LOG_AGE_DAYS -printf '%A@\n' | awk '{print int((systime()-$1)/86400)}')
        size=$(du -h "$file" | cut -f1)
        echo "  Deleting: $(basename "$file") (${age_days} days old, $size)"
        rm -f "$file"
    done
else
    echo "  No old compressed logs found."
fi
echo ""

# Step 5: Show final statistics
final_logs=$(ls -1 "$LOG_DIR"/scoreboard_*.log 2>/dev/null | wc -l)
final_compressed=$(ls -1 "$LOG_DIR"/scoreboard_*.log.gz 2>/dev/null | wc -l)
final_error_logs=$(ls -1 "$LOG_DIR"/scoreboard_error_*.log 2>/dev/null | wc -l)
total_size=$(du -sh "$LOG_DIR" 2>/dev/null | cut -f1)

echo "=== Cleanup Summary ==="
echo "Remaining files:"
echo "  - Regular logs: $final_logs"
echo "  - Compressed logs: $final_compressed"
echo "  - Error logs: $final_error_logs"
echo "Total disk usage: $total_size"
echo ""
echo "Cleanup completed at: $(date)"
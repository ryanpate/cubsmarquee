#!/bin/bash
# capture_image.sh - reads a prepared SD card to a .img file on macOS.
# Run on your Mac after running prepare_for_image.sh on the golden Pi
# and moving the SD card to a USB reader.

set -euo pipefail

if [[ "$(uname)" != "Darwin" ]]; then
    echo "ERROR: this script is for macOS. On Linux, use dd directly." >&2
    exit 1
fi

echo "==> Cubs Marquee SD card capture"
echo "==> Current disks:"
diskutil list

echo
read -r -p "Enter the disk identifier of the SD card (e.g., disk4): " DISK

if [[ ! "$DISK" =~ ^disk[0-9]+$ ]]; then
    echo "ERROR: invalid disk identifier '$DISK' (expected format: disk4)" >&2
    exit 1
fi

if [[ "$DISK" == "disk0" || "$DISK" == "disk1" ]]; then
    echo "ERROR: refusing to read $DISK (likely the system disk)" >&2
    exit 1
fi

echo
echo "==> Disk info for /dev/$DISK:"
diskutil info "/dev/$DISK" | grep -E "Device / Media Name|Disk Size|Protocol|Removable Media"

echo
echo "==> WARNING: about to read /dev/$DISK to a .img file."
read -r -p "Type YES to confirm: " CONFIRM
if [ "$CONFIRM" != "YES" ]; then
    echo "Aborted."
    exit 1
fi

OUT="cubsmarquee-v$(date +%Y-%m-%d).img"
if [ -e "$OUT" ]; then
    echo "ERROR: $OUT already exists. Move or rename it first." >&2
    exit 1
fi

echo "==> Unmounting /dev/$DISK"
diskutil unmountDisk "/dev/$DISK"

echo "==> Reading /dev/r$DISK -> $OUT (this can take 10-30 minutes)"
sudo dd if="/dev/r$DISK" of="$OUT" bs=4m status=progress

echo "==> Computing SHA-256"
shasum -a 256 "$OUT"

SIZE=$(ls -lh "$OUT" | awk '{print $5}')
echo "==> Done. Image: $OUT ($SIZE)"
echo "==> Flash with Raspberry Pi Imager: Use Custom -> select $OUT"

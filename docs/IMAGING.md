# Cubs Marquee — SD Card Imaging Workflow

This document describes how to produce flashable SD card images for new Cubs Marquee units.

## One-time setup of the golden master Pi

1. Flash a fresh Raspberry Pi OS Lite image to a small SD card (8 or 16 GB recommended — the smaller the source card, the smaller the resulting `.img` file).
2. Boot the Pi, complete normal setup, install the Cubs Marquee project under `/home/pi/cubsmarquee/`.
3. Verify the scoreboard runs end to end.
4. Verify `wifi-manager.service` and `wifi-web-config.service` are installed and enabled.

## Producing a new image

### On the golden master Pi

```bash
cd /home/pi/cubsmarquee
git pull
sudo ./prepare_for_image.sh
```

Type `YES` to confirm. The script will strip per-unit state, install the first-boot service, and shut the Pi down.

### On your Mac

1. Move the SD card from the Pi to a USB reader and plug it into your Mac.
2. From the project directory:

```bash
./capture_image.sh
```

3. Enter the disk identifier when prompted (run `diskutil list` first if needed).
4. Type `YES` to confirm.
5. Wait for `dd` to finish (10–30 minutes).

The output will be `cubsmarquee-vYYYY-MM-DD.img` with a SHA-256 checksum.

## Buyer setup card text

Print this on a card to ship with each unit:

```
Cubs Marquee Setup
1. Plug in power. Wait ~60 seconds.
2. The display will show: SETUP REQUIRED
3. On your phone, connect to WiFi: CubsMarquee-Setup
4. Open a browser and go to: cubsmarquee.local/admin
5. Enter your home WiFi name and password.
6. Done! The scoreboard will reboot and start.
```

## Troubleshooting

### Setup display never appears
- Confirm power and ribbon cable to the LED matrix.
- SSH in via ethernet and check `journalctl -u cubs-scoreboard`.

### `CubsMarquee-Setup` WiFi network does not appear
- Wait two full minutes after power-on (first boot includes a reboot).
- Check `journalctl -u wifi-manager`.

### `cubsmarquee.local/admin` does not load
- Some phones do not resolve `.local` mDNS. Try connecting from a laptop, or use the IP address shown on the AP gateway (typically `192.168.4.1`).

### Image is huge
- Capture from the smallest possible SD card. The image is the full size of the source card; Pi Imager will compress on flash.

## Image version stamp

Each prepared Pi has `/etc/cubsmarquee-version` written by `prepare_for_image.sh`. Run `cat /etc/cubsmarquee-version` on a unit to find out which image it was flashed from.

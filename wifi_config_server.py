#!/usr/bin/env python3
"""WiFi configuration web server - accessible at hostname.local/admin"""

from flask import (
    Flask, render_template_string, request, jsonify, redirect, send_file)
import subprocess
import os
import socket
import glob
import json
import time
import re

from scoreboard_config import DisplayConfig, PREVIEW_FILE_PATH
from teams import (
    TEAMS, DEFAULT_TEAM_SLUG, NON_DEFAULT_OFF_KEYS, DEFAULT_CUSTOM_MESSAGES,
    apply_team_defaults, get_active_team, NFL_TEAMS, DEFAULT_NFL_TEAM_SLUG)

app = Flask(__name__)

CONFIG_PATH = '/home/pi/config.json'
STATUS_FILE = '/var/tmp/scoreboard_status.json'
HEARTBEAT_STALE_SECONDS = 120


def get_connection_mode():
    """Determine if we're in AP mode or connected to WiFi"""
    try:
        result = subprocess.run(
            ['iwgetid', '-r'], capture_output=True, text=True, timeout=10)
        if result.stdout.strip():
            return 'Connected to WiFi'
        return 'Access Point Mode'
    except:
        return 'Unknown'


def get_hostname():
    """Get the Pi's hostname"""
    return socket.gethostname()


def _wpa_escape(value):
    """Escape backslashes and double quotes for a quoted wpa_supplicant string"""
    return value.replace('\\', '\\\\').replace('"', '\\"')


def validate_wifi_credentials(ssid, password):
    """Return an error message for invalid WiFi credentials, or None if valid"""
    if any(ord(c) < 32 for c in ssid + password):
        return 'SSID and password must not contain control characters'
    if len(ssid.encode('utf-8')) > 32:
        return 'SSID must be at most 32 bytes'
    if not 8 <= len(password) <= 63:
        return 'Password must be 8-63 characters'
    return None


def build_wpa_network_block(ssid, password):
    """Build a wpa_supplicant network block with escaped SSID/password"""
    return f"""network={{
    ssid="{_wpa_escape(ssid)}"
    psk="{_wpa_escape(password)}"
    key_mgmt=WPA-PSK
    priority=10
}}
"""


def set_hostname(new_hostname):
    """Set the Pi's hostname"""
    # Validate hostname format
    # Must be alphanumeric with hyphens, 1-63 characters, lowercase
    hostname_pattern = re.compile(r'^[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?$')

    if not hostname_pattern.match(new_hostname):
        return False, "Invalid hostname format. Use lowercase letters, numbers, and hyphens (1-63 chars)."

    # Reserved/problematic hostnames
    reserved = ['localhost', 'raspberrypi']
    if new_hostname in reserved:
        return False, f"Hostname '{new_hostname}' is reserved. Please choose a different name."

    try:
        current_hostname = get_hostname()

        # Update /etc/hostname
        with open('/tmp/hostname', 'w') as f:
            f.write(f"{new_hostname}\n")

        subprocess.run(['sudo', 'cp', '/tmp/hostname', '/etc/hostname'], check=True, timeout=10)

        # Update /etc/hosts
        # Read current hosts file
        with open('/etc/hosts', 'r') as f:
            hosts_content = f.read()

        # Replace old hostname with new hostname
        hosts_content = hosts_content.replace(current_hostname, new_hostname)

        # Ensure localhost entries exist
        if '127.0.0.1' not in hosts_content:
            hosts_content = f"127.0.0.1\tlocalhost\n127.0.1.1\t{new_hostname}\n" + hosts_content

        with open('/tmp/hosts', 'w') as f:
            f.write(hosts_content)

        subprocess.run(['sudo', 'cp', '/tmp/hosts', '/etc/hosts'], check=True, timeout=10)

        # Set hostname immediately (without reboot)
        subprocess.run(['sudo', 'hostnamectl', 'set-hostname', new_hostname], check=True, timeout=10)

        # Restart Avahi daemon to advertise new hostname via mDNS
        subprocess.run(['sudo', 'systemctl', 'restart', 'avahi-daemon'], check=False, timeout=30)

        return True, f"Hostname changed to '{new_hostname}'. Access at http://{new_hostname}.local/admin"

    except Exception as e:
        return False, f"Error setting hostname: {str(e)}"


def get_current_network():
    """Get currently connected network SSID"""
    try:
        result = subprocess.run(
            ['iwgetid', '-r'], capture_output=True, text=True, timeout=10)
        return result.stdout.strip() or 'Not connected'
    except:
        return 'Unknown'


def get_ip_address():
    """Get current IP address"""
    try:
        result = subprocess.run(
            ['hostname', '-I'], capture_output=True, text=True, timeout=10)
        return result.stdout.strip().split()[0] if result.stdout.strip() else 'No IP'
    except:
        return 'Unknown'


# Settings the running scoreboard cannot pick up on its own.
#
# Everything else is re-read while the display runs: off_season_handler
# reloads config.json every rotation iteration, and the display modules
# call load_user_config(), which re-parses whenever the file's mtime
# changes. Only these need the process restarted -- the team packs because
# handlers cache the pack's colors, logos and pre-generated backgrounds in
# __init__, and the matrix keys because they are applied once when the
# RGBMatrix is constructed.
#
# The four matrix keys are per-Pi and are not in the admin defaults (they
# are set by install_panel_v2.sh or by hand), so they are named here
# explicitly rather than coming from load_config().
REBOOT_REQUIRED_KEYS = {
    'team',
    'nfl_team',
    'panel_version',
    'hardware_mapping',
    'gpio_slowdown',
    'limit_refresh_rate_hz',
}

# Every other key in the admin defaults, listed so that adding a config key
# forces a reboot/live decision instead of silently defaulting to "live".
# tests/test_reboot_prompt.py fails when a key appears in neither set.
APPLIES_LIVE_KEYS = {
    'zip_code', 'weather_api_key', 'custom_message', 'display_mode',
    'enable_weather', 'enable_allstar', 'enable_bears', 'enable_bears_news',
    'nfl_preempt_mlb', 'enable_pga', 'enable_pga_news', 'enable_pga_facts',
    'enable_cubs_news', 'enable_cubs_facts', 'enable_bible',
    'enable_bible_facts', 'enable_newsmax', 'enable_usatoday',
    'enable_stocks', 'enable_spring_training', 'enable_playoff_race',
    'enable_flights', 'enable_flight_radar', 'enable_clock',
    'enable_cubs_history', 'enable_sky', 'enable_iss', 'enable_celebrations',
    'flights_between_displays',
    'scroll_speed_bears', 'scroll_speed_bears_news', 'scroll_speed_pga',
    'scroll_speed_pga_news', 'scroll_speed_pga_facts',
    'scroll_speed_cubs_facts', 'scroll_speed_cubs_news', 'scroll_speed_bible',
    'scroll_speed_bible_facts', 'scroll_speed_newsmax',
    'scroll_speed_usatoday', 'scroll_speed_stocks',
    'scroll_speed_spring_training', 'scroll_speed_flights',
    'flight_tracking_latitude', 'flight_tracking_longitude',
    'flight_tracking_address', 'flight_source', 'adsb_receiver_url',
    'flight_max_range_nm', 'airlabs_api_key',
    'brightness', 'dim_enabled', 'dim_start', 'dim_end', 'dim_brightness',
}

# The nightly updater only reboots when origin/main has moved, so there is
# no reboot to piggyback on for a quiet night. A transient one-shot timer
# is used instead; it does not survive a reboot, which is correct here --
# if the Pi restarts for any other reason the change is already applied.
SCHEDULED_REBOOT_UNIT = 'marquee-scheduled-reboot'
SCHEDULED_REBOOT_TIME = '04:00'


# Every admin-managed key and the value a fresh board starts with. Shared
# by load_config() and /save_config so the two cannot drift: a key added
# here is automatically preserved on save and checked by the
# reboot-classification completeness test.
DEFAULT_CONFIG = {
        'team': DEFAULT_TEAM_SLUG,
        'nfl_team': DEFAULT_NFL_TEAM_SLUG,
        'zip_code': '',
        'weather_api_key': '',
        'custom_message': 'GO CUBS GO! SEE YOU NEXT SEASON!',
        'display_mode': 'auto',
        'enable_weather': True,
        'enable_allstar': True,
        'enable_bears': True,
        'enable_bears_news': True,
        'nfl_preempt_mlb': False,
        'enable_pga': True,
        'enable_pga_news': True,
        'enable_pga_facts': True,
        'enable_cubs_news': True,
        'enable_cubs_facts': True,
        'enable_bible': True,
        'enable_bible_facts': True,
        'enable_newsmax': True,
        'enable_usatoday': True,
        'enable_stocks': True,
        'enable_spring_training': True,
        'enable_playoff_race': True,
        'enable_flights': True,
        'enable_flight_radar': True,
        'enable_clock': True,
        'enable_cubs_history': True,
        'enable_sky': True,
        'enable_iss': True,
        'enable_celebrations': True,
        'flights_between_displays': False,
        'scroll_speed_bears': 5,
        'scroll_speed_bears_news': 5,
        'scroll_speed_pga': 5,
        'scroll_speed_pga_news': 5,
        'scroll_speed_pga_facts': 5,
        'scroll_speed_cubs_facts': 5,
        'scroll_speed_cubs_news': 5,
        'scroll_speed_bible': 5,
        'scroll_speed_bible_facts': 5,
        'scroll_speed_newsmax': 5,
        'scroll_speed_usatoday': 5,
        'scroll_speed_stocks': 5,
        'scroll_speed_spring_training': 5,
        'scroll_speed_flights': 5,
        'flight_tracking_latitude': None,
        'flight_tracking_longitude': None,
        'flight_tracking_address': '',
        'flight_source': 'adsb_lol',
        'adsb_receiver_url': '',
        'flight_max_range_nm': 50,
        'airlabs_api_key': '',
        'brightness': 100,
        'dim_enabled': False,
        'dim_start': '22:00',
        'dim_end': '07:00',
        'dim_brightness': 30
}


def load_config():
    """Load configuration from JSON file"""
    default_config = dict(DEFAULT_CONFIG)

    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                loaded = json.load(f)
                default_config = apply_team_defaults(default_config, loaded)
                default_config.update(loaded)
    except Exception as e:
        print(f"Error loading config: {e}")

    return default_config


def save_config(config):
    """Save configuration to JSON file.

    Writes to a temp file and renames it into place so a power loss or
    concurrent reader never sees a truncated config.json.
    """
    tmp_path = CONFIG_PATH + '.tmp'
    try:
        with open(tmp_path, 'w') as f:
            json.dump(config, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, CONFIG_PATH)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return False


HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>{{ active_team.short_name }} Scoreboard Admin</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 20px auto;
            padding: 20px;
            background: #0C2340;
            color: white;
        }
        .container {
            background: white;
            color: #0C2340;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 0 20px rgba(0,0,0,0.3);
        }
        h1 {
            color: #CC3433;
            text-align: center;
            margin-bottom: 10px;
        }
        h2 {
            color: #0C2340;
            border-bottom: 2px solid #CC3433;
            padding-bottom: 5px;
            margin: 30px 0 15px 0;
        }
        .subtitle {
            text-align: center;
            color: #666;
            margin-bottom: 20px;
            font-size: 14px;
        }
        .nav-tabs {
            display: flex;
            border-bottom: 2px solid #0C2340;
            margin-bottom: 20px;
        }
        .nav-tab {
            padding: 10px 20px;
            cursor: pointer;
            background: #6c757d;
            border: none;
            font-size: 16px;
            font-weight: bold;
            margin-right: 5px;
            border-radius: 5px 5px 0 0;
        }
        .nav-tab.active {
            background: #0C2340;
            color: white;
        }
        .tab-content {
            display: none;
        }
        .tab-content.active {
            display: block;
        }
        .info-box {
            background: #f8f9fa;
            border-left: 4px solid #0C2340;
            padding: 15px;
            margin-bottom: 20px;
            border-radius: 4px;
        }
        .info-box strong {
            color: #CC3433;
        }
        .info-row {
            margin: 8px 0;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
        }
        input, select, textarea {
            width: 100%;
            padding: 10px;
            border: 2px solid #0C2340;
            border-radius: 5px;
            box-sizing: border-box;
            font-size: 16px;
        }
        textarea {
            resize: vertical;
            min-height: 60px;
        }
        input[type="checkbox"] {
            width: auto;
            display: inline-block;
            margin-right: 8px;
        }
        button {
            width: 100%;
            padding: 12px;
            background: #CC3433;
            color: white;
            border: none;
            border-radius: 5px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
        }
        button:hover {
            background: #A62C2B;
        }
        button:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
        .button-secondary {
            background: #0C2340;
            margin-top: 10px;
        }
        .button-secondary:hover {
            background: #081828;
        }
        .status {
            margin-top: 20px;
            padding: 10px;
            border-radius: 5px;
            display: none;
        }
        .status.success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        .status.error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        .network-list {
            max-height: 200px;
            overflow-y: auto;
            border: 2px solid #0C2340;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .network-item {
            padding: 10px;
            border-bottom: 1px solid #eee;
            cursor: pointer;
        }
        .network-item:hover {
            background: #f0f0f0;
        }
        .network-item:last-child {
            border-bottom: none;
        }
        .signal {
            float: right;
            color: #0C2340;
        }
        .warning {
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px;
            margin-bottom: 20px;
            border-radius: 4px;
            color: #856404;
        }
        .help-text {
            font-size: 13px;
            color: #666;
            margin-top: 5px;
        }
        .log-viewer {
            background: #1e1e1e;
            color: #d4d4d4;
            padding: 15px;
            border-radius: 5px;
            font-family: 'Courier New', monospace;
            font-size: 12px;
            height: 400px;
            overflow-y: auto;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        .service-status {
            display: inline-block;
            padding: 5px 10px;
            border-radius: 3px;
            font-weight: bold;
            margin-left: 10px;
        }
        .service-status.running {
            background: #d4edda;
            color: #155724;
        }
        .service-status.stopped {
            background: #f8d7da;
            color: #721c24;
        }
        .button-group {
            display: flex;
            gap: 10px;
        }
        .button-group button {
            flex: 1;
        }
        .button-start {
            background: #28a745;
        }
        .button-start:hover {
            background: #218838;
        }
        .button-stop {
            background: #dc3545;
        }
        .button-stop:hover {
            background: #c82333;
        }
        .button-restart {
            background: #fd7e14;
        }
        .button-restart:hover {
            background: #e96b02;
        }
        .button-reboot {
            background: #6c757d;
            margin-top: 20px;
        }
        .button-reboot:hover {
            background: #5a6268;
        }
        .reboot-prompt-backdrop {
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.55);
            z-index: 1000;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .reboot-prompt-backdrop.visible { display: flex; }
        .reboot-prompt-box {
            background: #fff;
            border-radius: 8px;
            padding: 24px;
            max-width: 460px;
            width: 100%;
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.3);
        }
        .reboot-prompt-box h3 { margin: 0 0 10px; }
        .reboot-prompt-box p { margin: 0 0 8px; }
        .reboot-prompt-keys {
            font-family: monospace;
            background: #f2f2f2;
            padding: 6px 8px;
            border-radius: 4px;
            display: inline-block;
        }
        .reboot-prompt-actions {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 18px;
        }
        .reboot-prompt-actions button { width: auto; flex: 1 1 auto; }
        .speed-control {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-top: 5px;
            padding: 8px;
            background: #f8f9fa;
            border-radius: 4px;
        }
        .speed-control label {
            min-width: 80px;
            margin-bottom: 0;
            font-size: 13px;
        }
        .speed-slider {
            flex: 1;
            height: 6px;
            -webkit-appearance: none;
            appearance: none;
            background: #ddd;
            border-radius: 3px;
            outline: none;
        }
        .speed-slider::-webkit-slider-thumb {
            -webkit-appearance: none;
            appearance: none;
            width: 18px;
            height: 18px;
            background: #0C2340;
            border-radius: 50%;
            cursor: pointer;
        }
        .speed-slider::-moz-range-thumb {
            width: 18px;
            height: 18px;
            background: #0C2340;
            border-radius: 50%;
            cursor: pointer;
            border: none;
        }
        .speed-value {
            min-width: 60px;
            text-align: center;
            font-weight: bold;
            font-size: 12px;
            color: #0C2340;
        }
        .scroll-speeds-section {
            background: #e9ecef;
            padding: 15px;
            border-radius: 8px;
            margin-top: 20px;
        }
        .scroll-speeds-section h4 {
            margin-top: 0;
            margin-bottom: 15px;
            color: #0C2340;
        }
        details.config-section {
            border: 1px solid #d0d7e2;
            border-radius: 8px;
            margin-bottom: 12px;
            background: #fafbfd;
        }
        details.config-section > summary {
            cursor: pointer;
            padding: 12px 15px;
            font-weight: bold;
            color: #0C2340;
            font-size: 1.05em;
            list-style-position: inside;
        }
        details.config-section[open] > summary {
            border-bottom: 1px solid #d0d7e2;
        }
        details.config-section > .section-body {
            padding: 15px;
        }
        .team-option {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px;
            border: 2px solid #d0d7e2;
            border-radius: 8px;
            margin-bottom: 8px;
            cursor: pointer;
        }
        .team-option:has(input:checked) {
            border-color: #CC3433;
            background: #fff5f5;
        }
        .team-option img { width: 28px; height: 28px; object-fit: contain; }
        .team-swatch {
            width: 18px; height: 18px; border-radius: 4px;
            border: 1px solid #999; margin-left: auto;
        }
        .checkbox-columns {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 4px 16px;
        }
    </style>
</head>
<body>
    <div class="reboot-prompt-backdrop" id="reboot-prompt">
        <div class="reboot-prompt-box">
            <h3>Reboot needed</h3>
            <p>Your settings were saved, but this change only takes effect
               after the Pi restarts:</p>
            <p><span class="reboot-prompt-keys" id="reboot-prompt-keys"></span></p>
            <p>Rebooting takes about two minutes, and the display is blank
               until it finishes.</p>
            <div class="reboot-prompt-actions">
                <button onclick="rebootFromPrompt(this)" class="button-reboot">Reboot now</button>
                <button onclick="scheduleRebootFromPrompt(this)" class="button-restart">Tonight at 4 AM</button>
                <button onclick="dismissRebootPrompt()">Not now</button>
            </div>
            <div id="reboot-prompt-status"></div>
        </div>
    </div>
    <div class="container">
        <h1>⚾ {{ active_team.short_name }} Scoreboard Admin</h1>
        <div class="subtitle">Configuration & Management Panel</div>

        <div class="info-box">
            <div class="info-row"><strong>Hostname:</strong> {{ hostname }}</div>
            <div class="info-row"><strong>Access URL:</strong> http://{{ hostname }}.local/admin</div>
            <div class="info-row"><strong>IP Address:</strong> {{ ip_address }}</div>
            <div class="info-row"><strong>Connection:</strong> {{ connection_mode }}</div>
            <div class="info-row"><strong>Current Network:</strong> {{ current_network }}</div>
            <div class="info-row"><strong>Scoreboard:</strong> <span id="scoreboard-status">checking...</span></div>
            <div class="info-row" style="text-align: center; margin-top: 8px;">
                <img id="matrix-preview" width="384" height="192" alt="Preview not available yet"
                     style="image-rendering: pixelated; background: #000; border-radius: 4px; max-width: 100%;">
            </div>
        </div>

        <div class="nav-tabs">
            <button class="nav-tab active" onclick="switchTab('wifi')">WiFi Setup</button>
            <button class="nav-tab" onclick="switchTab('config')">Display Config</button>
            <button class="nav-tab" onclick="switchTab('system')">System</button>
            <button class="nav-tab" onclick="switchTab('service')">Service Control</button>
            <button class="nav-tab" onclick="switchTab('logs')">Logs</button>
        </div>

        <div id="wifi-tab" class="tab-content active">
            <h2>WiFi Configuration</h2>
            <div class="warning">
                <strong>⚠️ Important:</strong> After connecting to WiFi, the IP address will change and this page will reload.
                You'll need to reconnect to this page using your new network at: <strong>http://{{ hostname }}.local/admin</strong>
            </div>
            
            <button onclick="scanNetworks()" class="button-secondary">Scan for Networks</button>
            <div id="network-list" class="network-list" style="display:none;"></div>

            <div class="form-group">
                <label for="ssid">Network Name (SSID):</label>
                <input type="text" id="ssid" placeholder="Enter WiFi network name">
            </div>

            <div class="form-group">
                <label for="password">Password:</label>
                <input type="password" id="password" placeholder="Enter WiFi password">
                <div class="help-text">Your WiFi password will be securely stored on the device</div>
            </div>

            <button onclick="connectWifi()">Connect to WiFi</button>
            <div id="wifi-status" class="status"></div>
        </div>

        <div id="config-tab" class="tab-content">
            <h2>Display Configuration</h2>

            <details class="config-section" open>
                <summary>Team</summary>
                <div class="section-body">
                    <p class="help-text">Pick the MLB team this board follows. The whole display re-themes to the team. Reboot required after changing.</p>
                    {% for slug, t in teams.items() %}
                    <label class="team-option">
                        <input type="radio" name="team" value="{{ slug }}">
                        <img src="/team_logo/{{ slug }}" alt="{{ t.name }}">
                        <span>{{ t.name }}</span>
                        <span class="team-swatch" style="background: rgb({{ t.primary_color[0] }},{{ t.primary_color[1] }},{{ t.primary_color[2] }})"></span>
                    </label>
                    {% endfor %}
                    <hr style="border: none; border-top: 1px solid #444; margin: 12px 0;">
                    <p class="help-text">Pick the NFL team for the football screens (game info and breaking news). Reboot required after changing.</p>
                    {% for slug, t in nfl_teams.items() %}
                    <label class="team-option">
                        <input type="radio" name="nfl_team" value="{{ slug }}">
                        <img src="/nfl_logo/{{ slug }}" alt="{{ t.name }}">
                        <span>{{ t.name }}</span>
                        <span class="team-swatch" style="background: rgb({{ t.primary_color[0] }},{{ t.primary_color[1] }},{{ t.primary_color[2] }})"></span>
                    </label>
                    {% endfor %}
                </div>
            </details>

            <details class="config-section">
                <summary>Brightness &amp; Auto-Dim</summary>
                <div class="section-body">
                    <div class="scroll-speeds-section">
                        <div class="speed-control">
                            <label>Brightness:</label>
                            <input type="range" class="speed-slider" id="brightness" min="10" max="100" value="100">
                            <span class="speed-value" id="brightness_val">100%</span>
                        </div>
                        <p class="help-text" style="margin-top: 8px;">Controls LED matrix brightness (10% = dim, 100% = full). Changes apply within ~10 seconds.</p>

                        <div class="speed-control" style="margin-top: 12px;">
                            <label><input type="checkbox" id="dim_enabled"> Auto-dim at night</label>
                        </div>
                        <div class="speed-control">
                            <label>Dim from:</label>
                            <input type="time" id="dim_start" value="22:00">
                            <label>until:</label>
                            <input type="time" id="dim_end" value="07:00">
                        </div>
                        <div class="speed-control">
                            <label>Night brightness:</label>
                            <input type="range" class="speed-slider" id="dim_brightness" min="10" max="100" value="30">
                            <span class="speed-value" id="dim_brightness_val">30%</span>
                        </div>
                        <p class="help-text" style="margin-top: 8px;">Automatically lowers brightness during the set hours (handles windows past midnight, e.g. 22:00 to 07:00).</p>
                    </div>
                </div>
            </details>

            <details class="config-section">
                <summary>Display Mode</summary>
                <div class="section-body">
                    <div class="form-group">
                        <label for="display_mode">Display Mode:</label>
                        <select id="display_mode">
                            <option value="auto">Automatic (Games during season, off-season content otherwise)</option>
                            <option value="game">Always show game (if available)</option>
                            <option value="offseason">Game schedule + off-season content rotation</option>
                            <option value="no_games">Off-season content only (never interrupt with game info)</option>
                        </select>
                    </div>
                </div>
            </details>

            <details class="config-section">
                <summary>Content Displays</summary>
                <div class="section-body">
                    <p class="help-text">Select which content to show in the rotation:</p>
                    <h4>Baseball</h4>
                    <div class="checkbox-columns">
                        <div class="form-group">
                            <label>
                                <input type="checkbox" id="enable_cubs_facts">
                                Team facts & custom message
                            </label>
                        </div>

                        <div class="form-group">
                            <label>
                                <input type="checkbox" id="enable_cubs_news">
                                Team breaking news
                            </label>
                        </div>

                        <div class="form-group">
                            <label>
                                <input type="checkbox" id="enable_cubs_history">
                                Today in team history
                            </label>
                        </div>

                        <div class="form-group">
                            <label>
                                <input type="checkbox" id="enable_spring_training">
                                Enable Spring Training countdown display
                            </label>
                        </div>

                        <div class="form-group">
                            <label>
                                <input type="checkbox" id="enable_playoff_race">
                                Enable playoff race display (July-September)
                            </label>
                        </div>

                        <div class="form-group">
                            <label>
                                <input type="checkbox" id="enable_clock">
                                Wrigley scoreboard clock
                            </label>
                        </div>

                        <div class="form-group">
                            <label>
                                <input type="checkbox" id="enable_allstar">
                                Enable All-Star Game display
                            </label>
                        </div>
                    </div>

                    <h4>Other Sports</h4>
                    <div class="checkbox-columns">
                        <div class="form-group">
                            <label>
                                <input type="checkbox" id="enable_bears">
                                Enable NFL team game display (football season)
                            </label>
                        </div>

                        <div class="form-group">
                            <label>
                                <input type="checkbox" id="enable_bears_news">
                                Enable NFL breaking news display
                            </label>
                        </div>

                        <div class="form-group">
                            <label>
                                <input type="checkbox" id="nfl_preempt_mlb">
                                NFL preempts MLB
                            </label>
                            <div class="help-text">A live football game takes over the display, the way a baseball game normally does. Off by default, so baseball wins.</div>
                        </div>

                        <div class="form-group">
                            <label>
                                <input type="checkbox" id="enable_pga">
                                Enable PGA Tour leaderboard display (golf season)
                            </label>
                        </div>

                        <div class="form-group">
                            <label>
                                <input type="checkbox" id="enable_pga_news">
                                Enable PGA Tour news display (golf season)
                            </label>
                        </div>

                        <div class="form-group">
                            <label>
                                <input type="checkbox" id="enable_pga_facts">
                                Enable PGA Tour facts display (golf season)
                            </label>
                        </div>
                    </div>

                    <h4>News &amp; Info</h4>
                    <div class="checkbox-columns">
                        <div class="form-group">
                            <label>
                                <input type="checkbox" id="enable_weather">
                                Enable Weather display
                            </label>
                        </div>

                        <div class="form-group">
                            <label>
                                <input type="checkbox" id="enable_newsmax">
                                Enable Newsmax news display
                            </label>
                        </div>

                        <div class="form-group">
                            <label>
                                <input type="checkbox" id="enable_usatoday">
                                Enable USA Today news display
                            </label>
                        </div>

                        <div class="form-group">
                            <label>
                                <input type="checkbox" id="enable_stocks">
                                Enable Stock Exchange ticker display
                            </label>
                        </div>
                    </div>

                    <h4>Sky &amp; Flight</h4>
                    <div class="checkbox-columns">
                        <div class="form-group">
                            <label>
                                <input type="checkbox" id="enable_sky">
                                Enable Sun &amp; Sky display (sunrise arc, moon phase)
                            </label>
                        </div>

                        <div class="form-group">
                            <label>
                                <input type="checkbox" id="enable_iss">
                                Enable ISS tracker display
                            </label>
                        </div>

                        <div class="form-group">
                            <label>
                                <input type="checkbox" id="enable_flights">
                                Enable Flight Tracking display
                            </label>
                        </div>

                        <div class="form-group">
                            <label>
                                <input type="checkbox" id="enable_flight_radar">
                                Enable Flight Radar View (full-screen radar scope)
                            </label>
                        </div>

                        <div class="form-group">
                            <label>
                                <input type="checkbox" id="flights_between_displays">
                                Show flight display between every screen (~45s interstitial)
                            </label>
                        </div>
                    </div>

                    <h4>Faith &amp; Fun</h4>
                    <div class="checkbox-columns">
                        <div class="form-group">
                            <label>
                                <input type="checkbox" id="enable_bible">
                                Enable Bible Verse of the Day display
                            </label>
                        </div>

                        <div class="form-group">
                            <label>
                                <input type="checkbox" id="enable_bible_facts">
                                Enable Bible Facts display
                            </label>
                        </div>

                        <div class="form-group">
                            <label>
                                <input type="checkbox" id="enable_celebrations">
                                Enable celebration days display (birthdays &amp; holidays)
                            </label>
                        </div>
                    </div>
                </div>
            </details>

            <details class="config-section">
                <summary>Scroll Speeds</summary>
                <div class="section-body">
                    <div class="scroll-speeds-section">
                        <p class="help-text" style="margin-bottom: 15px;">Adjust scrolling text speed for each display (1 = slowest, 10 = fastest):</p>

                        <div class="speed-control">
                            <label>NFL Game:</label>
                            <input type="range" class="speed-slider" id="scroll_speed_bears" min="1" max="10" value="5">
                            <span class="speed-value" id="scroll_speed_bears_val">5</span>
                        </div>

                        <div class="speed-control">
                            <label>NFL News:</label>
                            <input type="range" class="speed-slider" id="scroll_speed_bears_news" min="1" max="10" value="5">
                            <span class="speed-value" id="scroll_speed_bears_news_val">5</span>
                        </div>

                        <div class="speed-control">
                            <label>PGA:</label>
                            <input type="range" class="speed-slider" id="scroll_speed_pga" min="1" max="10" value="5">
                            <span class="speed-value" id="scroll_speed_pga_val">5</span>
                        </div>

                        <div class="speed-control">
                            <label>PGA News:</label>
                            <input type="range" class="speed-slider" id="scroll_speed_pga_news" min="1" max="10" value="5">
                            <span class="speed-value" id="scroll_speed_pga_news_val">5</span>
                        </div>

                        <div class="speed-control">
                            <label>PGA Facts:</label>
                            <input type="range" class="speed-slider" id="scroll_speed_pga_facts" min="1" max="10" value="5">
                            <span class="speed-value" id="scroll_speed_pga_facts_val">5</span>
                        </div>

                        <div class="speed-control">
                            <label>Team Facts:</label>
                            <input type="range" class="speed-slider" id="scroll_speed_cubs_facts" min="1" max="10" value="5">
                            <span class="speed-value" id="scroll_speed_cubs_facts_val">5</span>
                        </div>

                        <div class="speed-control">
                            <label>Team News:</label>
                            <input type="range" class="speed-slider" id="scroll_speed_cubs_news" min="1" max="10" value="5">
                            <span class="speed-value" id="scroll_speed_cubs_news_val">5</span>
                        </div>

                        <div class="speed-control">
                            <label>Bible Verse:</label>
                            <input type="range" class="speed-slider" id="scroll_speed_bible" min="1" max="10" value="5">
                            <span class="speed-value" id="scroll_speed_bible_val">5</span>
                        </div>

                        <div class="speed-control">
                            <label>Bible Facts:</label>
                            <input type="range" class="speed-slider" id="scroll_speed_bible_facts" min="1" max="10" value="5">
                            <span class="speed-value" id="scroll_speed_bible_facts_val">5</span>
                        </div>

                        <div class="speed-control">
                            <label>Newsmax:</label>
                            <input type="range" class="speed-slider" id="scroll_speed_newsmax" min="1" max="10" value="5">
                            <span class="speed-value" id="scroll_speed_newsmax_val">5</span>
                        </div>

                        <div class="speed-control">
                            <label>USA Today:</label>
                            <input type="range" class="speed-slider" id="scroll_speed_usatoday" min="1" max="10" value="5">
                            <span class="speed-value" id="scroll_speed_usatoday_val">5</span>
                        </div>

                        <div class="speed-control">
                            <label>Stocks:</label>
                            <input type="range" class="speed-slider" id="scroll_speed_stocks" min="1" max="10" value="5">
                            <span class="speed-value" id="scroll_speed_stocks_val">5</span>
                        </div>

                        <div class="speed-control">
                            <label>Spring Training:</label>
                            <input type="range" class="speed-slider" id="scroll_speed_spring_training" min="1" max="10" value="5">
                            <span class="speed-value" id="scroll_speed_spring_training_val">5</span>
                        </div>

                        <div class="speed-control">
                            <label>Flights:</label>
                            <input type="range" class="speed-slider" id="scroll_speed_flights" min="1" max="10" value="5">
                            <span class="speed-value" id="scroll_speed_flights_val">5</span>
                        </div>
                    </div>
                </div>
            </details>

            <details class="config-section">
                <summary>Flight Tracking</summary>
                <div class="section-body">
                    <p class="help-text" style="margin-bottom: 15px;">Set your location to track flights overhead. Enter coordinates directly or use address lookup:</p>

                    <div class="form-group">
                        <label for="flight_tracking_latitude">Latitude:</label>
                        <input type="text" id="flight_tracking_latitude" placeholder="e.g., 39.7500" style="width: 200px;">
                    </div>

                    <div class="form-group">
                        <label for="flight_tracking_longitude">Longitude:</label>
                        <input type="text" id="flight_tracking_longitude" placeholder="e.g., -89.6653" style="width: 200px;">
                        <div class="help-text">Enter decimal coordinates directly, or use address lookup below to auto-fill</div>
                    </div>

                    <div class="form-group" style="margin-top: 10px; padding: 10px; background: #f0f4f8; border-radius: 8px;">
                        <label for="flight_tracking_address">Address Lookup (optional):</label>
                        <input type="text" id="flight_tracking_address" placeholder="e.g., Rochester, IL">
                        <div class="help-text">Enter a city/state or full address, then click Calculate to auto-fill lat/lon above</div>
                        <button type="button" onclick="geocodeAddress()" class="button-secondary" style="margin-top: 8px;">Calculate Coordinates</button>
                        <div id="coordinates-display" style="margin-top: 5px;">
                            <span id="coords-text" class="help-text"></span>
                        </div>
                    </div>

                    <div class="form-group" style="margin-top: 15px; padding: 10px; background: #f5f5f5; border-radius: 5px;">
                        <label style="font-weight: bold; color: #0C2340;">Flight Data Source:</label>
                        <div style="margin-top: 8px;">
                            <label style="display: block; font-weight: normal; margin-bottom: 6px;">
                                <input type="radio" name="flight_source" id="flight_source_adsb_lol" value="adsb_lol">
                                adsb.lol (recommended &mdash; no setup)
                            </label>
                            <label style="display: block; font-weight: normal;">
                                <input type="radio" name="flight_source" id="flight_source_local" value="local">
                                Local ADS-B receiver
                            </label>
                        </div>
                        <div id="local_receiver_url_wrapper" style="margin-top: 10px; padding-left: 22px; display: none;">
                            <label for="adsb_receiver_url" style="font-weight: normal;">Local Receiver URL:</label>
                            <input type="text" id="adsb_receiver_url"
                                   placeholder="http://piaware.local/skyaware/data/aircraft.json"
                                   value="{{ config.adsb_receiver_url }}">
                            <small style="display: block; margin-top: 5px; color: #666;">
                                Enter the URL of your PiAware / readsb aircraft.json endpoint.
                                Example: <code>http://piaware.local/skyaware/data/aircraft.json</code>
                            </small>
                        </div>
                    </div>

                    <div class="form-group">
                        <label for="flight_max_range_nm">Max Range (NM): <span id="flight_range_val">{{ config.flight_max_range_nm or 50 }}</span></label>
                        <input type="range" id="flight_max_range_nm" min="10" max="100" value="{{ config.flight_max_range_nm or 50 }}" oninput="document.getElementById('flight_range_val').textContent=this.value">
                        <div class="help-text">Maximum range in nautical miles for flight tracking (10-100 NM)</div>
                    </div>

                    <div class="form-group">
                        <label for="airlabs_api_key">AirLabs API Key (optional, for flight destinations):</label>
                        <input type="text" id="airlabs_api_key" placeholder="Optional - destinations auto-lookup via airplanes.live" value="{{ config.airlabs_api_key }}">
                        <div class="help-text">Optional. Destinations are now looked up free via airplanes.live. AirLabs is a secondary fallback.</div>
                    </div>
                </div>
            </details>

            <details class="config-section">
                <summary>Weather &amp; Location</summary>
                <div class="section-body">
                    <div class="form-group">
                        <label for="zip_code">ZIP Code (for weather):</label>
                        <input type="text" id="zip_code" placeholder="e.g., 60613" value="{{ config.zip_code }}">
                    </div>

                    <div class="form-group">
                        <label for="weather_api_key">OpenWeather API Key (optional - weather now uses Open-Meteo; only the flight address lookup below uses this):</label>
                        <input type="text" id="weather_api_key" placeholder="Get free API key from openweathermap.org" value="{{ config.weather_api_key }}">
                        <div class="help-text">Free tier API key from <a href="https://openweathermap.org/api" target="_blank">openweathermap.org</a></div>
                    </div>
                </div>
            </details>

            <details class="config-section">
                <summary>Custom Message</summary>
                <div class="section-body">
                    <div class="form-group">
                        <label for="custom_message">Custom Message:</label>
                        <textarea id="custom_message">{{ config.custom_message }}</textarea>
                        <div class="help-text">This message displays during the off-season rotation</div>
                    </div>
                </div>
            </details>

            <button onclick="saveConfig()">Save Configuration</button>
            <div id="config-status" class="status"></div>
        </div>

        <div id="system-tab" class="tab-content">
            <h2>System Settings</h2>

            <div class="info-box">
                <strong>Current Hostname:</strong> {{ hostname }}
                <div class="help-text" style="margin-top: 10px;">
                    This is how you access the scoreboard on your local network: <strong>http://{{ hostname }}.local/admin</strong>
                </div>
            </div>

            <div class="warning">
                <strong>⚠️ Important:</strong> If multiple scoreboards are on the same WiFi network, each must have a unique hostname.
                After changing the hostname, you'll need to access the admin page at the new address: <strong>http://new-hostname.local/admin</strong>
            </div>

            <div class="form-group">
                <label for="new_hostname">New Hostname:</label>
                <input type="text" id="new_hostname" placeholder="e.g., cubsmarquee-1" pattern="[a-z0-9\-]+" value="{{ hostname }}">
                <div class="help-text">
                    Use lowercase letters, numbers, and hyphens only (1-63 characters).
                    Examples: cubsmarquee-1, scoreboard-wrigley, cubs-display-01
                </div>
            </div>

            <button onclick="changeHostname()">Change Hostname</button>
            <div id="hostname-status" class="status"></div>
        </div>

        <div id="service-tab" class="tab-content">
            <h2>Service Control</h2>
            
            <div class="info-box">
                <div class="info-row">
                    <strong>Scoreboard Service Status:</strong>
                    <span id="service-status-badge" class="service-status">Loading...</span>
                </div>
            </div>

            <div class="button-group">
                <button onclick="controlService(this, 'start')" class="button-start">Start Service</button>
                <button onclick="controlService(this, 'stop')" class="button-stop">Stop Service</button>
                <button onclick="controlService(this, 'restart')" class="button-restart">Restart Service</button>
            </div>

            <button onclick="rebootDevice(this)" class="button-reboot">Reboot Pi</button>
            
            <div id="service-control-status" class="status"></div>
        </div>

        <div id="logs-tab" class="tab-content">
            <h2>System Logs</h2>
            
            <div class="button-group" style="margin-bottom: 15px;">
                <button onclick="loadLogs('application')" class="button-secondary">Application Logs</button>
                <button onclick="loadLogs('error')" class="button-secondary">Error Logs</button>
                <button onclick="loadLogs('wifi')" class="button-secondary">WiFi Manager Logs</button>
            </div>

            <div class="info-box">
                <strong id="log-filename">Select a log type above</strong>
            </div>

            <div id="log-content" class="log-viewer">
                Select a log type to view...
            </div>

            <button onclick="refreshCurrentLog()" style="margin-top: 10px;" class="button-secondary">Refresh Current Log</button>
        </div>
    </div>

    <script>
        let currentLogType = null;

        // Per-team default custom_message text, keyed by slug. Rendered
        // from teams.py so this can never drift from apply_team_defaults().
        const TEAM_DEFAULT_MESSAGES = {{ team_default_messages | tojson }};
        // Config keys that default to off for non-Cubs teams (see
        // teams.NON_DEFAULT_OFF_KEYS); these double as the checkbox ids.
        const NON_DEFAULT_OFF_KEYS = {{ non_default_off_keys | tojson }};

        // Poll the scoreboard heartbeat for the status row
        async function refreshScoreboardStatus() {
            const el = document.getElementById('scoreboard-status');
            try {
                const resp = await fetch('/scoreboard_status');
                const data = await resp.json();
                if (!data.available) {
                    el.textContent = 'No status reported yet';
                } else if (data.stale) {
                    el.textContent = data.state + ' (stale - last update ' + data.age_seconds + 's ago)';
                } else {
                    el.textContent = data.state + (data.detail ? ' - ' + data.detail : '');
                }
            } catch (e) {
                el.textContent = 'unavailable';
            }
        }
        refreshScoreboardStatus();
        setInterval(refreshScoreboardStatus, 10000);

        // Live matrix preview - the scoreboard republishes every ~2s
        function refreshPreview() {
            const img = document.getElementById('matrix-preview');
            img.src = '/preview.png?t=' + Date.now();
        }
        refreshPreview();
        setInterval(refreshPreview, 2000);

        // Auto-load config values on page load
        window.onload = function() {
            const config = {{ config | tojson }};
            const teamSlug = config.team || 'cubs';
            const teamRadio = document.querySelector(
                `input[name="team"][value="${teamSlug}"]`);
            if (teamRadio) teamRadio.checked = true;
            window._loadedTeam = teamSlug;

            const nflSlug = config.nfl_team || 'bears';
            const nflRadio = document.querySelector(
                `input[name="nfl_team"][value="${nflSlug}"]`);
            if (nflRadio) nflRadio.checked = true;
            window._loadedNflTeam = nflSlug;

            // Track the currently-selected team separately from
            // window._loadedTeam (which reflects what's saved on the
            // server and drives the "reboot required" notice) so the
            // team-change handler below can tell whether the custom
            // message is still the previous team's default.
            let currentTeamSlug = teamSlug;
            document.querySelectorAll('input[name="team"]').forEach(function(radio) {
                radio.addEventListener('change', function() {
                    const previousSlug = currentTeamSlug;
                    const newSlug = this.value;

                    // Chicago-specific content defaults to off for
                    // non-Cubs teams; re-checked when switching back to
                    // Cubs. The user can still override before saving.
                    NON_DEFAULT_OFF_KEYS.forEach(function(key) {
                        document.getElementById(key).checked = (newSlug === 'cubs');
                    });

                    // Only replace the custom message if it still matches
                    // the previous team's default - never touch text the
                    // user customized themselves.
                    const messageField = document.getElementById('custom_message');
                    const previousDefault = TEAM_DEFAULT_MESSAGES[previousSlug];
                    if (previousDefault !== undefined &&
                        messageField.value === previousDefault &&
                        TEAM_DEFAULT_MESSAGES[newSlug] !== undefined) {
                        messageField.value = TEAM_DEFAULT_MESSAGES[newSlug];
                    }

                    currentTeamSlug = newSlug;
                });
            });

            document.getElementById('display_mode').value = config.display_mode || 'auto';
            document.getElementById('enable_weather').checked = config.enable_weather !== false;
            document.getElementById('enable_allstar').checked = config.enable_allstar !== false;
            document.getElementById('enable_bears').checked = config.enable_bears !== false;
            document.getElementById('enable_bears_news').checked = config.enable_bears_news !== false;
            document.getElementById('nfl_preempt_mlb').checked = config.nfl_preempt_mlb === true;
            document.getElementById('enable_pga').checked = config.enable_pga !== false;
            document.getElementById('enable_pga_news').checked = config.enable_pga_news !== false;
            document.getElementById('enable_pga_facts').checked = config.enable_pga_facts !== false;
            document.getElementById('enable_cubs_facts').checked = config.enable_cubs_facts !== false;
            document.getElementById('enable_cubs_news').checked = config.enable_cubs_news !== false;
            document.getElementById('enable_bible').checked = config.enable_bible !== false;
            document.getElementById('enable_bible_facts').checked = config.enable_bible_facts !== false;
            document.getElementById('enable_newsmax').checked = config.enable_newsmax !== false;
            document.getElementById('enable_usatoday').checked = config.enable_usatoday !== false;
            document.getElementById('enable_stocks').checked = config.enable_stocks !== false;
            document.getElementById('enable_spring_training').checked = config.enable_spring_training !== false;
            document.getElementById('enable_playoff_race').checked = config.enable_playoff_race !== false;
            document.getElementById('enable_flights').checked = config.enable_flights !== false;
            document.getElementById('enable_flight_radar').checked = config.enable_flight_radar !== false;
            document.getElementById('enable_clock').checked = config.enable_clock !== false;
            document.getElementById('enable_cubs_history').checked = config.enable_cubs_history !== false;
            document.getElementById('enable_sky').checked = config.enable_sky !== false;
            document.getElementById('enable_iss').checked = config.enable_iss !== false;
            document.getElementById('enable_celebrations').checked = config.enable_celebrations !== false;
            document.getElementById('flights_between_displays').checked = config.flights_between_displays === true;

            // Load brightness setting
            const brightnessSlider = document.getElementById('brightness');
            const brightnessVal = document.getElementById('brightness_val');
            const brightnessValue = config.brightness != null ? config.brightness : 100;
            brightnessSlider.value = brightnessValue;
            brightnessVal.textContent = brightnessValue + '%';
            brightnessSlider.addEventListener('input', function() {
                brightnessVal.textContent = this.value + '%';
            });

            // Load auto-dim settings
            document.getElementById('dim_enabled').checked = !!config.dim_enabled;
            document.getElementById('dim_start').value = config.dim_start || '22:00';
            document.getElementById('dim_end').value = config.dim_end || '07:00';
            const dimSlider = document.getElementById('dim_brightness');
            const dimVal = document.getElementById('dim_brightness_val');
            const dimValue = config.dim_brightness != null ? config.dim_brightness : 30;
            dimSlider.value = dimValue;
            dimVal.textContent = dimValue + '%';
            dimSlider.addEventListener('input', function() {
                dimVal.textContent = this.value + '%';
            });

            // Load flight tracking location
            document.getElementById('flight_tracking_address').value = config.flight_tracking_address || '';
            document.getElementById('flight_tracking_latitude').value = config.flight_tracking_latitude != null ? config.flight_tracking_latitude : '';
            document.getElementById('flight_tracking_longitude').value = config.flight_tracking_longitude != null ? config.flight_tracking_longitude : '';

            // Load ADS-B receiver config
            document.getElementById('adsb_receiver_url').value = config.adsb_receiver_url || '';
            // Load flight source radio (default 'adsb_lol')
            var flightSource = config.flight_source || 'adsb_lol';
            if (flightSource === 'local') {
                document.getElementById('flight_source_local').checked = true;
                document.getElementById('local_receiver_url_wrapper').style.display = 'block';
            } else {
                document.getElementById('flight_source_adsb_lol').checked = true;
                document.getElementById('local_receiver_url_wrapper').style.display = 'none';
            }
            // Toggle the URL field visibility when the radio changes
            document.getElementById('flight_source_adsb_lol').addEventListener('change', function() {
                document.getElementById('local_receiver_url_wrapper').style.display = 'none';
            });
            document.getElementById('flight_source_local').addEventListener('change', function() {
                document.getElementById('local_receiver_url_wrapper').style.display = 'block';
            });
            document.getElementById('flight_max_range_nm').value = config.flight_max_range_nm || 50;
            document.getElementById('flight_range_val').textContent = config.flight_max_range_nm || 50;

            // Load AirLabs API key
            document.getElementById('airlabs_api_key').value = config.airlabs_api_key || '';

            // Load scroll speed settings
            const speedFields = [
                'scroll_speed_bears', 'scroll_speed_bears_news',
                'scroll_speed_pga', 'scroll_speed_pga_news', 'scroll_speed_pga_facts',
                'scroll_speed_cubs_facts', 'scroll_speed_cubs_news',
                'scroll_speed_bible', 'scroll_speed_bible_facts',
                'scroll_speed_newsmax', 'scroll_speed_usatoday', 'scroll_speed_stocks',
                'scroll_speed_spring_training', 'scroll_speed_flights'
            ];

            speedFields.forEach(field => {
                const slider = document.getElementById(field);
                const valueDisplay = document.getElementById(field + '_val');
                const value = config[field] || 5;
                slider.value = value;
                valueDisplay.textContent = value;

                // Add event listener to update display value
                slider.addEventListener('input', function() {
                    valueDisplay.textContent = this.value;
                });
            });

            updateServiceStatus();
        };

        function switchTab(tabName) {
            // Hide all tabs
            const tabs = document.querySelectorAll('.tab-content');
            tabs.forEach(tab => tab.classList.remove('active'));

            // Remove active from all tab buttons
            const buttons = document.querySelectorAll('.nav-tab');
            buttons.forEach(btn => btn.classList.remove('active'));

            // Show selected tab
            document.getElementById(tabName + '-tab').classList.add('active');

            // Activate button
            event.target.classList.add('active');

            // Update service status when switching to service tab
            if (tabName === 'service') {
                updateServiceStatus();
            }
        }

        function showStatus(elementId, message, isSuccess) {
            const status = document.getElementById(elementId);
            status.textContent = message;
            status.className = 'status ' + (isSuccess ? 'success' : 'error');
            status.style.display = 'block';
            setTimeout(() => {
                status.style.display = 'none';
            }, 5000);
        }

        async function scanNetworks() {
            const networkList = document.getElementById('network-list');
            networkList.innerHTML = '<div style="padding: 10px; text-align: center;">Scanning...</div>';
            networkList.style.display = 'block';

            try {
                const response = await fetch('/scan_networks');
                const data = await response.json();

                if (data.success && data.networks.length > 0) {
                    // Build DOM nodes with textContent so hostile SSIDs
                    // can never inject HTML or script
                    networkList.innerHTML = '';
                    if (data.cached) {
                        const note = document.createElement('div');
                        note.style.cssText = 'padding: 6px 10px; font-size: 12px; color: #888;';
                        note.textContent = 'Networks seen before the hotspot started';
                        networkList.appendChild(note);
                    }
                    data.networks.forEach(network => {
                        const item = document.createElement('div');
                        item.className = 'network-item';
                        item.addEventListener('click', () => selectNetwork(network.ssid));
                        item.appendChild(document.createTextNode(network.ssid + ' '));
                        const signal = document.createElement('span');
                        signal.className = 'signal';
                        signal.textContent = network.signal;
                        item.appendChild(signal);
                        networkList.appendChild(item);
                    });
                } else {
                    networkList.innerHTML = '<div style="padding: 10px; text-align: center;">No networks found</div>';
                }
            } catch (error) {
                networkList.innerHTML = '<div style="padding: 10px; text-align: center; color: red;">Error scanning networks</div>';
            }
        }

        function selectNetwork(ssid) {
            document.getElementById('ssid').value = ssid;
        }

        async function connectWifi() {
            const ssid = document.getElementById('ssid').value;
            const password = document.getElementById('password').value;

            if (!ssid || !password) {
                showStatus('wifi-status', 'Please enter both SSID and password', false);
                return;
            }

            const button = event.target;
            button.disabled = true;
            button.textContent = 'Connecting...';

            try {
                const response = await fetch('/connect_wifi', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ssid, password })
                });

                const data = await response.json();

                if (data.success) {
                    showStatus('wifi-status', data.message + ' The page will reload in 10 seconds...', true);
                    // Wait for connection to establish, then reload
                    setTimeout(() => {
                        window.location.reload();
                    }, 10000);
                } else {
                    showStatus('wifi-status', 'Error: ' + data.message, false);
                    button.disabled = false;
                    button.textContent = 'Connect to WiFi';
                }
            } catch (error) {
                showStatus('wifi-status', 'Connection error: ' + error.message, false);
                button.disabled = false;
                button.textContent = 'Connect to WiFi';
            }
        }

        async function geocodeAddress() {
            const address = document.getElementById('flight_tracking_address').value;
            const apiKey = document.getElementById('weather_api_key').value;

            if (!address) {
                showStatus('config-status', 'Please enter a location address', false);
                return;
            }

            if (!apiKey) {
                showStatus('config-status', 'OpenWeather API key is required for geocoding', false);
                return;
            }

            try {
                const response = await fetch('/geocode_address', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ address: address, api_key: apiKey })
                });

                const data = await response.json();

                if (data.success) {
                    document.getElementById('flight_tracking_latitude').value = data.latitude;
                    document.getElementById('flight_tracking_longitude').value = data.longitude;
                    document.getElementById('coords-text').textContent =
                        `Found: ${data.latitude.toFixed(4)}, ${data.longitude.toFixed(4)} — verify these are correct, then Save`;
                    showStatus('config-status', 'Coordinates filled in above. Verify they look right, then click Save Configuration.', true);
                } else {
                    showStatus('config-status', 'Geocoding error: ' + data.message, false);
                }
            } catch (error) {
                showStatus('config-status', 'Geocoding error: ' + error.message, false);
            }
        }

        async function saveConfig() {
            const latValue = document.getElementById('flight_tracking_latitude').value;
            const lonValue = document.getElementById('flight_tracking_longitude').value;

            const checkedTeamRadio = document.querySelector('input[name="team"]:checked');
            const checkedNflRadio = document.querySelector('input[name="nfl_team"]:checked');
            const config = {
                team: checkedTeamRadio ? checkedTeamRadio.value : 'cubs',
                nfl_team: checkedNflRadio ? checkedNflRadio.value : 'bears',
                zip_code: document.getElementById('zip_code').value,
                weather_api_key: document.getElementById('weather_api_key').value,
                custom_message: document.getElementById('custom_message').value,
                display_mode: document.getElementById('display_mode').value,
                enable_weather: document.getElementById('enable_weather').checked,
                enable_allstar: document.getElementById('enable_allstar').checked,
                enable_bears: document.getElementById('enable_bears').checked,
                enable_bears_news: document.getElementById('enable_bears_news').checked,
                nfl_preempt_mlb: document.getElementById('nfl_preempt_mlb').checked,
                enable_pga: document.getElementById('enable_pga').checked,
                enable_pga_news: document.getElementById('enable_pga_news').checked,
                enable_pga_facts: document.getElementById('enable_pga_facts').checked,
                enable_cubs_facts: document.getElementById('enable_cubs_facts').checked,
                enable_cubs_news: document.getElementById('enable_cubs_news').checked,
                enable_bible: document.getElementById('enable_bible').checked,
                enable_bible_facts: document.getElementById('enable_bible_facts').checked,
                enable_newsmax: document.getElementById('enable_newsmax').checked,
                enable_usatoday: document.getElementById('enable_usatoday').checked,
                enable_stocks: document.getElementById('enable_stocks').checked,
                enable_spring_training: document.getElementById('enable_spring_training').checked,
                enable_playoff_race: document.getElementById('enable_playoff_race').checked,
                enable_flights: document.getElementById('enable_flights').checked,
                enable_flight_radar: document.getElementById('enable_flight_radar').checked,
                enable_clock: document.getElementById('enable_clock').checked,
                enable_cubs_history: document.getElementById('enable_cubs_history').checked,
                enable_sky: document.getElementById('enable_sky').checked,
                enable_iss: document.getElementById('enable_iss').checked,
                enable_celebrations: document.getElementById('enable_celebrations').checked,
                flights_between_displays: document.getElementById('flights_between_displays').checked,
                scroll_speed_bears: parseInt(document.getElementById('scroll_speed_bears').value),
                scroll_speed_bears_news: parseInt(document.getElementById('scroll_speed_bears_news').value),
                scroll_speed_pga: parseInt(document.getElementById('scroll_speed_pga').value),
                scroll_speed_pga_news: parseInt(document.getElementById('scroll_speed_pga_news').value),
                scroll_speed_pga_facts: parseInt(document.getElementById('scroll_speed_pga_facts').value),
                scroll_speed_cubs_facts: parseInt(document.getElementById('scroll_speed_cubs_facts').value),
                scroll_speed_cubs_news: parseInt(document.getElementById('scroll_speed_cubs_news').value),
                scroll_speed_bible: parseInt(document.getElementById('scroll_speed_bible').value),
                scroll_speed_bible_facts: parseInt(document.getElementById('scroll_speed_bible_facts').value),
                scroll_speed_newsmax: parseInt(document.getElementById('scroll_speed_newsmax').value),
                scroll_speed_usatoday: parseInt(document.getElementById('scroll_speed_usatoday').value),
                scroll_speed_stocks: parseInt(document.getElementById('scroll_speed_stocks').value),
                scroll_speed_spring_training: parseInt(document.getElementById('scroll_speed_spring_training').value),
                scroll_speed_flights: parseInt(document.getElementById('scroll_speed_flights').value),
                flight_tracking_address: document.getElementById('flight_tracking_address').value,
                flight_tracking_latitude: latValue ? parseFloat(latValue) : null,
                flight_tracking_longitude: lonValue ? parseFloat(lonValue) : null,
                flight_source: document.querySelector('input[name="flight_source"]:checked').value,
                adsb_receiver_url: document.getElementById('adsb_receiver_url').value,
                flight_max_range_nm: parseInt(document.getElementById('flight_max_range_nm').value),
                airlabs_api_key: document.getElementById('airlabs_api_key').value,
                brightness: parseInt(document.getElementById('brightness').value),
                dim_enabled: document.getElementById('dim_enabled').checked,
                dim_start: document.getElementById('dim_start').value,
                dim_end: document.getElementById('dim_end').value,
                dim_brightness: parseInt(document.getElementById('dim_brightness').value)
            };

            const button = event.target;
            button.disabled = true;
            button.textContent = 'Saving...';

            try {
                const response = await fetch('/save_config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(config)
                });

                const data = await response.json();

                if (data.success) {
                    window._loadedTeam = config.team;
                    window._loadedNflTeam = config.nfl_team;
                    // The server decides: it compares the saved values
                    // against the previous ones, so we only prompt when a
                    // reboot would actually change something. Everything
                    // else the running display picks up on its own.
                    if (data.reboot_required) {
                        showRebootPrompt(data.reboot_keys);
                        showStatus('config-status', 'Configuration saved.', true);
                    } else {
                        showStatus('config-status',
                            'Configuration saved. Changes apply within a few minutes.',
                            true);
                    }
                } else {
                    showStatus('config-status', 'Error: ' + data.message, false);
                }
            } catch (error) {
                showStatus('config-status', 'Save error: ' + error.message, false);
            } finally {
                button.disabled = false;
                button.textContent = 'Save Configuration';
            }
        }

        async function changeHostname() {
            const newHostname = document.getElementById('new_hostname').value.toLowerCase().trim();
            const currentHostname = '{{ hostname }}';

            if (!newHostname) {
                showStatus('hostname-status', 'Please enter a hostname', false);
                return;
            }

            if (newHostname === currentHostname) {
                showStatus('hostname-status', 'New hostname is the same as current hostname', false);
                return;
            }

            // Validate hostname format
            const hostnamePattern = /^[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?$/;
            if (!hostnamePattern.test(newHostname)) {
                showStatus('hostname-status', 'Invalid hostname format. Use lowercase letters, numbers, and hyphens only (1-63 chars)', false);
                return;
            }

            if (!confirm(`Are you sure you want to change the hostname from "${currentHostname}" to "${newHostname}"?\n\nAfter the change, you'll need to access this page at:\nhttp://${newHostname}.local/admin`)) {
                return;
            }

            const button = event.target;
            button.disabled = true;
            button.textContent = 'Changing Hostname...';

            try {
                const response = await fetch('/change_hostname', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ hostname: newHostname })
                });

                const data = await response.json();

                if (data.success) {
                    showStatus('hostname-status', data.message + ' Redirecting in 5 seconds...', true);
                    setTimeout(() => {
                        window.location.href = `http://${newHostname}.local/admin`;
                    }, 5000);
                } else {
                    showStatus('hostname-status', 'Error: ' + data.message, false);
                    button.disabled = false;
                    button.textContent = 'Change Hostname';
                }
            } catch (error) {
                showStatus('hostname-status', 'Error changing hostname: ' + error.message, false);
                button.disabled = false;
                button.textContent = 'Change Hostname';
            }
        }

        async function updateServiceStatus() {
            try {
                const response = await fetch('/service_status');
                const data = await response.json();
                const badge = document.getElementById('service-status-badge');
                
                if (data.running) {
                    badge.textContent = 'Running';
                    badge.className = 'service-status running';
                } else {
                    badge.textContent = 'Stopped';
                    badge.className = 'service-status stopped';
                }
            } catch (error) {
                const badge = document.getElementById('service-status-badge');
                badge.textContent = 'Unknown';
                badge.className = 'service-status';
            }
        }

        async function controlService(button, action) {
            button.disabled = true;
            const originalText = button.textContent;
            button.textContent = action.charAt(0).toUpperCase() + action.slice(1) + 'ing...';

            try {
                const response = await fetch('/control_service', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action })
                });

                const data = await response.json();

                if (data.success) {
                    showStatus('service-control-status', data.message + ' Refreshing status...', true);
                    // Poll status multiple times to show when operation completes
                    setTimeout(updateServiceStatus, 2000);
                    setTimeout(updateServiceStatus, 5000);
                    setTimeout(updateServiceStatus, 8000);
                } else {
                    showStatus('service-control-status', 'Error: ' + data.message, false);
                }
            } catch (error) {
                showStatus('service-control-status', 'Control error: ' + error.message, false);
            } finally {
                button.disabled = false;
                button.textContent = originalText;
            }
        }

        function showRebootPrompt(keys) {
            document.getElementById('reboot-prompt-keys').textContent =
                (keys && keys.length) ? keys.join(', ') : 'this setting';
            document.getElementById('reboot-prompt-status').innerHTML = '';
            document.getElementById('reboot-prompt').classList.add('visible');
        }

        function dismissRebootPrompt() {
            document.getElementById('reboot-prompt').classList.remove('visible');
        }

        async function rebootFromPrompt(button) {
            button.disabled = true;
            button.textContent = 'Rebooting...';
            try {
                const response = await fetch('/reboot', { method: 'POST' });
                const data = await response.json();
                if (data.success) {
                    showStatus('reboot-prompt-status',
                        'Rebooting... wait about 2 minutes before reconnecting.', true);
                } else {
                    showStatus('reboot-prompt-status',
                        'Reboot error: ' + data.message, false);
                    button.disabled = false;
                    button.textContent = 'Reboot now';
                }
            } catch (error) {
                showStatus('reboot-prompt-status',
                    'Reboot error: ' + error.message, false);
                button.disabled = false;
                button.textContent = 'Reboot now';
            }
        }

        async function scheduleRebootFromPrompt(button) {
            button.disabled = true;
            button.textContent = 'Scheduling...';
            try {
                const response = await fetch('/schedule_reboot', { method: 'POST' });
                const data = await response.json();
                if (data.success) {
                    showStatus('reboot-prompt-status', data.message, true);
                    setTimeout(dismissRebootPrompt, 2000);
                } else {
                    // Say so plainly - a user who thinks the reboot is
                    // booked will not come back to check.
                    showStatus('reboot-prompt-status',
                        'Could not schedule: ' + data.message +
                        ' - reboot now or from the System tab instead.', false);
                    button.disabled = false;
                    button.textContent = 'Tonight at 4 AM';
                }
            } catch (error) {
                showStatus('reboot-prompt-status',
                    'Could not schedule: ' + error.message, false);
                button.disabled = false;
                button.textContent = 'Tonight at 4 AM';
            }
        }

        async function rebootDevice(button) {
            if (!confirm('Are you sure you want to reboot the Raspberry Pi? The display will be unavailable for about 2 minutes.')) {
                return;
            }

            button.disabled = true;
            button.textContent = 'Rebooting...';

            try {
                const response = await fetch('/reboot', {
                    method: 'POST'
                });

                const data = await response.json();

                if (data.success) {
                    showStatus('service-control-status', 'Rebooting... Please wait 2 minutes before reconnecting.', true);
                } else {
                    showStatus('service-control-status', 'Reboot error: ' + data.message, false);
                    button.disabled = false;
                    button.textContent = 'Reboot Pi';
                }
            } catch (error) {
                showStatus('service-control-status', 'Reboot error: ' + error.message, false);
                button.disabled = false;
                button.textContent = 'Reboot Pi';
            }
        }

        async function loadLogs(logType) {
            currentLogType = logType;
            const logContent = document.getElementById('log-content');
            const logFilename = document.getElementById('log-filename');

            logContent.textContent = 'Loading logs...';
            logFilename.textContent = 'Loading...';

            try {
                const response = await fetch(`/logs/${logType}`);
                const data = await response.json();

                if (data.success) {
                    logContent.textContent = data.content;
                    logFilename.textContent = data.filename;
                    // Auto-scroll to bottom
                    logContent.scrollTop = logContent.scrollHeight;
                } else {
                    logContent.textContent = 'Error: ' + data.message;
                    logFilename.textContent = 'Error';
                }
            } catch (error) {
                logContent.textContent = 'Failed to load logs: ' + error.message;
                logFilename.textContent = 'Error';
            }
        }

        function refreshCurrentLog() {
            if (currentLogType) {
                loadLogs(currentLogType);
            }
        }
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    return redirect('/admin')


@app.route('/admin')
def admin():
    """Main admin page"""
    config = load_config()

    return render_template_string(
        HTML_TEMPLATE,
        hostname=get_hostname(),
        connection_mode=get_connection_mode(),
        current_network=get_current_network(),
        ip_address=get_ip_address(),
        config=config,
        teams=TEAMS,
        nfl_teams=NFL_TEAMS,
        active_team=get_active_team(config),
        team_default_messages=DEFAULT_CUSTOM_MESSAGES,
        non_default_off_keys=NON_DEFAULT_OFF_KEYS
    )


@app.route('/team_logo/<slug>')
def team_logo(slug):
    pack = TEAMS.get(slug)
    if pack is None:
        return ('Not found', 404)
    return send_file(pack.logo_path, mimetype='image/png')


@app.route('/nfl_logo/<slug>')
def nfl_logo(slug):
    pack = NFL_TEAMS.get(slug)
    if pack is None:
        return ('Not found', 404)
    return send_file(pack.logo_path, mimetype='image/png')


# Raw iwlist output written by wifi_manager.sh just before it starts the
# hotspot - the radio can't scan while hostapd owns it
SCAN_CACHE_PATH = '/var/tmp/wifi_scan_cache.txt'


def _parse_iwlist(output):
    """Parse `iwlist wlan0 scan` output into unique ssid/signal entries"""
    networks = []
    current_network = None

    for line in output.split('\n'):
        if 'ESSID:' in line:
            ssid = line.split('ESSID:')[1].strip().strip('"')
            if ssid and current_network:
                current_network['ssid'] = ssid
                networks.append(current_network)
                current_network = None

        if 'Cell' in line and 'Address' in line:
            current_network = {'ssid': '', 'signal': ''}

        if 'Quality=' in line and current_network:
            try:
                quality = line.split('Quality=')[1].split()[0]
                num, den = quality.split('/')
                signal_strength = int((int(num) / int(den)) * 100)
                bars = '█' * (signal_strength // 20)
                current_network['signal'] = f"{bars} {signal_strength}%"
            except:
                current_network['signal'] = 'Unknown'

    # Remove duplicates
    unique_networks = []
    seen_ssids = set()
    for network in networks:
        if network['ssid'] and network['ssid'] not in seen_ssids:
            unique_networks.append(network)
            seen_ssids.add(network['ssid'])
    return unique_networks


# Bookworm/Trixie images hand wlan0 to NetworkManager: there is no
# wpa_supplicant.conf to write and iwlist scans come back empty, so the
# wpa_supplicant path above is inert there. Cache written by wifi_manager_nm.sh.
NM_SCAN_CACHE_PATH = '/var/tmp/wifi_scan_cache_nm.txt'


def _use_networkmanager():
    """True when NetworkManager owns the WiFi rather than wpa_supplicant."""
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', 'NetworkManager'],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() == 'active'
    except Exception:
        return False


def _parse_nmcli_scan(output):
    """Parse `nmcli -t -f SSID,SIGNAL dev wifi list` into the same shape
    _parse_iwlist returns, so the page renders both identically."""
    networks = []
    seen_ssids = set()
    for line in output.split('\n'):
        if not line.strip():
            continue
        # nmcli -t escapes colons inside fields as '\:'
        parts = re.split(r'(?<!\\):', line)
        ssid = parts[0].replace('\\:', ':').strip()
        if not ssid or ssid in seen_ssids:
            continue
        seen_ssids.add(ssid)
        try:
            strength = int(parts[1])
        except (IndexError, ValueError):
            strength = 0
        bars = '█' * (strength // 20)
        networks.append({'ssid': ssid, 'signal': f"{bars} {strength}%"})
    return networks


def _connect_wifi_nm(ssid, password):
    """Save and activate a WiFi profile via NetworkManager."""
    con_name = f'marquee-{ssid}'
    subprocess.run(['sudo', 'nmcli', 'connection', 'delete', con_name],
                   check=False, capture_output=True, timeout=15)

    added = subprocess.run(
        ['sudo', 'nmcli', 'connection', 'add', 'type', 'wifi',
         'con-name', con_name, 'ifname', 'wlan0', 'ssid', ssid,
         'wifi-sec.key-mgmt', 'wpa-psk', 'wifi-sec.psk', password,
         'connection.autoconnect', 'yes',
         'connection.autoconnect-priority', '50'],
        capture_output=True, text=True, timeout=30
    )
    if added.returncode != 0:
        return jsonify({'success': False,
                        'message': f'Could not save network: {added.stderr.strip()}'})

    # One radio cannot host an AP and join a network at once. Dropping the
    # hotspot kills this HTTP response if the browser arrived over it -- the
    # profile is already saved and autoconnects, so that is expected.
    subprocess.run(['sudo', 'nmcli', 'connection', 'down', 'marquee-hotspot'],
                   check=False, capture_output=True, timeout=20)

    up = subprocess.run(['sudo', 'nmcli', 'connection', 'up', con_name],
                        capture_output=True, text=True, timeout=60)
    hostname = get_hostname()
    if up.returncode == 0:
        return jsonify({
            'success': True,
            'message': f'Connected to {ssid}! Admin page: http://{hostname}.local/admin'
        })
    return jsonify({
        'success': True,
        'message': (f'Saved {ssid} but it has not connected yet '
                    f'({up.stderr.strip()}). It will keep retrying.')
    })


@app.route('/scan_networks')
def scan_networks():
    """Scan for available WiFi networks; in hotspot mode the live scan
    fails (hostapd owns the radio), so fall back to the scan cached by
    wifi_manager.sh right before the AP started"""
    networks = []
    use_nm = _use_networkmanager()
    try:
        if use_nm:
            result = subprocess.run(
                ['sudo', 'nmcli', '-t', '-f', 'SSID,SIGNAL', 'dev', 'wifi',
                 'list', '--rescan', 'yes'],
                capture_output=True, text=True, timeout=20
            )
            networks = _parse_nmcli_scan(result.stdout)
        else:
            result = subprocess.run(
                ['sudo', 'iwlist', 'wlan0', 'scan'],
                capture_output=True,
                text=True,
                timeout=15
            )
            networks = _parse_iwlist(result.stdout)
    except Exception as e:
        print(f"Live WiFi scan failed: {e}")

    cached = False
    if not networks:
        cache_path = NM_SCAN_CACHE_PATH if use_nm else SCAN_CACHE_PATH
        parser = _parse_nmcli_scan if use_nm else _parse_iwlist
        try:
            with open(cache_path) as f:
                networks = parser(f.read())
            cached = bool(networks)
        except OSError:
            pass

    return jsonify({'success': True, 'networks': networks, 'cached': cached})


@app.route('/connect_wifi', methods=['POST'])
def connect_wifi():
    """Connect to a WiFi network"""
    try:
        data = request.json
        ssid = data.get('ssid')
        password = data.get('password')

        if not ssid or not password:
            return jsonify({'success': False, 'message': 'SSID and password required'})

        error = validate_wifi_credentials(ssid, password)
        if error:
            return jsonify({'success': False, 'message': error})

        if _use_networkmanager():
            return _connect_wifi_nm(ssid, password)

        # Read existing wpa_supplicant config
        existing_header = """ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=US

"""
        existing_networks = []

        try:
            with open('/etc/wpa_supplicant/wpa_supplicant.conf', 'r') as f:
                content = f.read()
                # Extract existing networks (except the one we're adding)
                network_blocks = re.findall(r'network=\{[^}]+\}', content, re.DOTALL)
                for block in network_blocks:
                    # Check if this is a different SSID
                    ssid_match = re.search(r'ssid="([^"]+)"', block)
                    if ssid_match and ssid_match.group(1) != ssid:
                        existing_networks.append(block)
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"Warning: Could not read existing config: {e}")

        # Build new config with existing networks plus the new one (with highest priority)
        wpa_config = existing_header

        # Add existing networks first with lower priority
        for network in existing_networks:
            wpa_config += f"network={network[8:]}\n\n"  # Remove 'network=' prefix

        # Add new network with highest priority
        wpa_config += build_wpa_network_block(ssid, password)

        # Write to temp file first
        with open('/tmp/wpa_supplicant.conf', 'w') as f:
            f.write(wpa_config)

        # Copy to proper location with correct permissions
        subprocess.run(
            ['sudo', 'cp', '/tmp/wpa_supplicant.conf',
             '/etc/wpa_supplicant/wpa_supplicant.conf'],
            check=True, timeout=10
        )
        
        subprocess.run(
            ['sudo', 'chmod', '600', '/etc/wpa_supplicant/wpa_supplicant.conf'],
            check=True, timeout=10
        )
        
        # Ensure wpa_supplicant service is enabled for persistence
        subprocess.run(
            ['sudo', 'systemctl', 'enable', 'wpa_supplicant'],
            check=False, timeout=30
        )

        # Stop AP mode if running
        subprocess.run(['sudo', 'systemctl', 'stop', 'hostapd'], check=False, timeout=30)
        subprocess.run(['sudo', 'systemctl', 'stop', 'dnsmasq'], check=False, timeout=30)

        # Remove AP IP if set
        subprocess.run(['sudo', 'ip', 'addr', 'flush', 'dev', 'wlan0'], check=False, timeout=10)

        # Restart networking services in proper order
        subprocess.run(['sudo', 'systemctl', 'restart', 'dhcpcd'], check=False, timeout=30)
        time.sleep(2)
        subprocess.run(['sudo', 'wpa_cli', '-i', 'wlan0', 'reconfigure'], check=False, timeout=30)
        time.sleep(3)
        
        # Restart Avahi to advertise hostname on new network
        subprocess.run(['sudo', 'systemctl', 'restart', 'avahi-daemon'], check=False, timeout=30)
        time.sleep(2)
        
        # Check if we got an IP (not the AP IP)
        result = subprocess.run(
            ['ip', 'addr', 'show', 'wlan0'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        hostname = get_hostname()
        
        if 'inet ' in result.stdout and '10.0.0.1' not in result.stdout:
            # We have a new IP, connection looks good
            return jsonify({
                'success': True,
                'message': f'WiFi configured and connected to {ssid}! Access the admin page at http://{hostname}.local/admin'
            })
        else:
            return jsonify({
                'success': True,
                'message': f'WiFi configured. Attempting to connect to {ssid}... Access at http://{hostname}.local/admin once connected.'
            })

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/geocode_address', methods=['POST'])
def geocode_address():
    """Geocode an address to latitude/longitude using OpenWeatherMap Geocoding API"""
    try:
        data = request.json
        address = data.get('address', '')
        api_key = data.get('api_key', '')

        if not address:
            return jsonify({'success': False, 'message': 'Address is required'})

        if not api_key:
            return jsonify({'success': False, 'message': 'OpenWeather API key is required'})

        # Use OpenWeatherMap Geocoding API
        import requests
        url = f"http://api.openweathermap.org/geo/1.0/direct?q={address}&limit=1&appid={api_key}"

        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            results = response.json()
            if results and len(results) > 0:
                lat = results[0]['lat']
                lon = results[0]['lon']
                return jsonify({
                    'success': True,
                    'latitude': lat,
                    'longitude': lon,
                    'name': results[0].get('name', ''),
                    'country': results[0].get('country', '')
                })
            else:
                return jsonify({'success': False, 'message': 'Address not found'})
        else:
            return jsonify({'success': False, 'message': f'API error: {response.status_code}'})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


def _validate_hhmm(raw, default):
    """Return raw if it is a valid 'HH:MM' string, else the default"""
    try:
        hours, minutes = str(raw).split(':')
        if 0 <= int(hours) <= 23 and 0 <= int(minutes) <= 59:
            return raw
    except (ValueError, AttributeError):
        pass
    return default


@app.route('/preview.png')
def preview_png():
    """Serve the latest frame the scoreboard rendered"""
    try:
        with open(PREVIEW_FILE_PATH, 'rb') as f:
            data = f.read()
    except OSError:
        return ('', 404)
    response = app.response_class(data, mimetype='image/png')
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.route('/scoreboard_status')
def scoreboard_status():
    """Report what the scoreboard process is currently showing"""
    try:
        with open(STATUS_FILE, 'r') as f:
            heartbeat = json.load(f)
        age = time.time() - heartbeat.get('timestamp', 0)
        return jsonify({
            'available': True,
            'state': heartbeat.get('state', 'Unknown'),
            'detail': heartbeat.get('detail', ''),
            'age_seconds': int(age),
            'stale': age > HEARTBEAT_STALE_SECONDS,
        })
    except (OSError, ValueError):
        return jsonify({'available': False})


def _clamp_brightness(raw) -> int:
    """Coerce and clamp an incoming brightness value to the allowed range.

    Returns BRIGHTNESS_DEFAULT if the value is missing or non-numeric, so a
    bad brightness field doesn't prevent the rest of the config from saving.
    """
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DisplayConfig.BRIGHTNESS_DEFAULT
    return max(
        DisplayConfig.BRIGHTNESS_MIN,
        min(DisplayConfig.BRIGHTNESS_MAX, value)
    )


@app.route('/save_config', methods=['POST'])
def save_config_route():
    """Save display configuration"""
    try:
        data = request.json
        current_config = load_config()
        # Snapshot before the update so we can tell a real change from a
        # re-save of the same value.
        previous_config = dict(current_config)

        # A key the request omits keeps whatever is already saved. Falling
        # back to a hardcoded default here would silently reset every
        # setting the caller did not happen to mention -- blanking the
        # weather ZIP, re-enabling switched-off screens, and so on. Note
        # this is `key in data`, not data.get(key) or default: an explicit
        # False, 0 or "" is a real edit and must survive.
        current_config.update({
            key: data[key] if key in data else current_config.get(key, default)
            for key, default in DEFAULT_CONFIG.items()
        })

        # Fields that need coercion or validation. These fall back to
        # previous_config, not current_config: the passthrough above has
        # already copied the incoming value in, so validating against
        # current_config would let a bad value validate against itself.
        current_config.update({
            'brightness': _clamp_brightness(
                data.get('brightness', previous_config.get('brightness'))),
            'dim_enabled': bool(
                data.get('dim_enabled', previous_config.get('dim_enabled', False))),
            'dim_start': _validate_hhmm(
                data.get('dim_start'), previous_config.get('dim_start', '22:00')),
            'dim_end': _validate_hhmm(
                data.get('dim_end'), previous_config.get('dim_end', '07:00')),
            'dim_brightness': _clamp_brightness(
                data.get('dim_brightness', previous_config.get('dim_brightness', 30))),
        })

        # Report which reboot-requiring settings actually changed value, so
        # the page only prompts when a reboot would really change something.
        reboot_keys = sorted(
            key for key in REBOOT_REQUIRED_KEYS
            if key in current_config
            and current_config[key] != previous_config.get(key))

        if save_config(current_config):
            return jsonify({
                'success': True,
                'reboot_required': bool(reboot_keys),
                'reboot_keys': reboot_keys,
            })
        else:
            return jsonify({'success': False, 'message': 'Failed to save configuration'})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/change_hostname', methods=['POST'])
def change_hostname_route():
    """Change the system hostname"""
    try:
        data = request.json
        new_hostname = data.get('hostname', '').lower().strip()

        if not new_hostname:
            return jsonify({'success': False, 'message': 'Hostname is required'})

        success, message = set_hostname(new_hostname)

        return jsonify({'success': success, 'message': message})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/service_status')
def service_status():
    """Check if the scoreboard service is running"""
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', 'cubs-scoreboard'],
            capture_output=True,
            text=True,
            timeout=5
        )

        is_running = result.stdout.strip() == 'active'

        return jsonify({
            'running': is_running,
            'status': result.stdout.strip()
        })

    except Exception as e:
        return jsonify({'running': False, 'error': str(e)})


@app.route('/control_service', methods=['POST'])
def control_service():
    """Control the scoreboard service (stop/start/restart)"""
    try:
        data = request.json
        action = data.get('action')

        if action not in ['stop', 'start', 'restart']:
            return jsonify({'success': False, 'message': 'Invalid action'})

        if action == 'stop':
            # Run stop in background to avoid timeout
            subprocess.Popen(
                ['bash', '-c', 'sudo systemctl stop cubs-scoreboard; sudo pkill -9 -f "python.*main.py" 2>/dev/null; exit 0'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            return jsonify({'success': True, 'message': 'Stop command sent. Service will stop shortly.'})

        elif action == 'start':
            # Run start in background to avoid timeout
            subprocess.Popen(
                ['bash', '-c', 'sudo pkill -9 -f "python.*main.py" 2>/dev/null; sleep 1; sudo systemctl start cubs-scoreboard'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            return jsonify({'success': True, 'message': 'Start command sent. Service will start shortly.'})

        elif action == 'restart':
            # Run full restart sequence in background to avoid timeout
            subprocess.Popen(
                ['bash', '-c', '''
                    sudo systemctl stop cubs-scoreboard 2>/dev/null
                    sleep 2
                    sudo pkill -9 -f "python.*main.py" 2>/dev/null
                    sleep 2
                    sudo systemctl start cubs-scoreboard
                '''],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            return jsonify({'success': True, 'message': 'Restart command sent. Service will restart shortly.'})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/reboot', methods=['POST'])
def reboot_device():
    """Reboot the Raspberry Pi"""
    try:
        # Use 'shutdown -r now' with a small delay via 'at' or bash to ensure response is sent
        # Run reboot in background after 2 second delay to allow HTTP response to complete
        subprocess.Popen(
            ['bash', '-c', 'sleep 2 && sudo reboot'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        return jsonify({'success': True, 'message': 'Reboot initiated - Pi will restart in a few seconds'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/schedule_reboot', methods=['POST'])
def schedule_reboot():
    """Book a one-shot reboot for tonight instead of rebooting now.

    Any previously scheduled reboot is cancelled first, so repeatedly
    saving settings cannot stack up timers.
    """
    try:
        subprocess.run(
            ['sudo', 'systemctl', 'stop', f'{SCHEDULED_REBOOT_UNIT}.timer'],
            capture_output=True, timeout=10)
        subprocess.run(
            ['sudo', 'systemd-run',
             f'--unit={SCHEDULED_REBOOT_UNIT}',
             f'--on-calendar=*-*-* {SCHEDULED_REBOOT_TIME}:00',
             '--timer-property=AccuracySec=1min',
             '/sbin/reboot'],
            capture_output=True, timeout=10, check=True)
        return jsonify({
            'success': True,
            'message': f'Reboot scheduled for {SCHEDULED_REBOOT_TIME} tonight',
        })
    except Exception as e:
        # Never report success we cannot back up: a user who believes the
        # reboot is booked will not check again.
        return jsonify({'success': False, 'message': str(e)})


@app.route('/logs/<log_type>')
def get_logs(log_type):
    """Retrieve logs based on type"""
    try:
        log_dir = '/home/pi/scoreboard_logs'

        if log_type == 'application':
            log_files = glob.glob(f'{log_dir}/scoreboard_*.log')
            if not log_files:
                return jsonify({'success': False, 'message': 'No application logs found'})

            latest_log = max(log_files, key=os.path.getmtime)
            with open(latest_log, 'r') as f:
                lines = f.readlines()
                content = ''.join(lines[-500:])

            return jsonify({
                'success': True,
                'content': content,
                'filename': os.path.basename(latest_log)
            })

        elif log_type == 'error':
            log_files = glob.glob(f'{log_dir}/scoreboard_error_*.log')
            if not log_files:
                return jsonify({'success': False, 'message': 'No error logs found'})

            latest_log = max(log_files, key=os.path.getmtime)
            with open(latest_log, 'r') as f:
                lines = f.readlines()
                content = ''.join(lines[-500:])

            return jsonify({
                'success': True,
                'content': content,
                'filename': os.path.basename(latest_log)
            })

        elif log_type == 'wifi':
            result = subprocess.run(
                ['journalctl', '-u', 'wifi-manager', '-n', '200', '--no-pager'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                return jsonify({
                    'success': True,
                    'content': result.stdout,
                    'filename': 'WiFi Manager Journal'
                })
            else:
                wifi_log = '/var/log/wifi_manager.log'
                if os.path.exists(wifi_log):
                    with open(wifi_log, 'r') as f:
                        lines = f.readlines()
                        content = ''.join(lines[-200:])
                    return jsonify({
                        'success': True,
                        'content': content,
                        'filename': 'wifi_manager.log'
                    })
                else:
                    return jsonify({
                        'success': False,
                        'message': 'WiFi manager logs not available'
                    })

        else:
            return jsonify({'success': False, 'message': 'Invalid log type'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Error reading logs: {str(e)}'})


if __name__ == '__main__':
    # threaded=True so one hung request (e.g. a stuck systemctl call)
    # can't make the whole admin panel unreachable
    app.run(host='0.0.0.0', port=80, debug=False, threaded=True)

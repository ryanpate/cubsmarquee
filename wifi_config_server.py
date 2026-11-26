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
    apply_team_defaults, get_active_team, NFL_TEAMS, DEFAULT_NFL_TEAM_SLUG,
    NCAAB_TEAMS, DEFAULT_NCAAB_TEAM_SLUG)

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
    'ncaab_team',
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
    'enable_ncaab', 'enable_ncaab_rankings', 'enable_ncaab_standings',
    'enable_ncaab_news', 'enable_ncaab_facts',
    'scroll_speed_ncaab_news', 'scroll_speed_ncaab_facts',
    'enable_cubs_news', 'enable_cubs_facts', 'enable_bible',
    'enable_bible_facts', 'enable_newsmax', 'enable_usatoday',
    'enable_stocks', 'enable_spring_training', 'enable_playoff_race',
    'enable_flights', 'enable_flight_radar', 'enable_clock',
    'enable_cubs_history', 'enable_sky', 'enable_iss', 'enable_celebrations',
    'enable_holiday_facts', 'scroll_speed_holiday_facts',
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
        'ncaab_team': DEFAULT_NCAAB_TEAM_SLUG,
        'zip_code': '',
        'weather_api_key': '',
        'custom_message': 'GO CUBS GO! SEE YOU NEXT SEASON!',
        'display_mode': 'auto',
        'enable_weather': True,
        'enable_allstar': True,
        'enable_bears': True,
        'enable_bears_news': True,
        'nfl_preempt_mlb': False,
        'enable_ncaab': True,
        'enable_ncaab_rankings': True,
        'enable_ncaab_standings': True,
        'enable_ncaab_news': True,
        'enable_ncaab_facts': True,
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
        'enable_holiday_facts': True,
        'flights_between_displays': False,
        'scroll_speed_bears': 5,
        'scroll_speed_bears_news': 5,
        'scroll_speed_ncaab_news': 5,
        'scroll_speed_ncaab_facts': 5,
        'scroll_speed_pga': 5,
        'scroll_speed_pga_news': 5,
        'scroll_speed_pga_facts': 5,
        'scroll_speed_cubs_facts': 5,
        'scroll_speed_cubs_news': 5,
        'scroll_speed_bible': 5,
        'scroll_speed_bible_facts': 5,
        'scroll_speed_holiday_facts': 5,
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
    <title>{{ active_team.short_name }} Scoreboard Settings</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    {% set pc = active_team.primary_color %}
    <style>
        :root {
            --accent: rgb({{ pc[0] }}, {{ pc[1] }}, {{ pc[2] }});
            --bg: #f3f4f7;
            --card: #ffffff;
            --text: #1d2433;
            --muted: #5f6b7d;
            --line: #e2e6ec;
            --good: #1f8a4c;
            --bad: #c62f2f;
            --warn-bg: #fff6e0;
            --warn-text: #7a5300;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
            background: var(--bg);
            color: var(--text);
            font-size: 16px;
            line-height: 1.45;
            padding-bottom: 90px;
        }
        .page { max-width: 760px; margin: 0 auto; padding: 0 16px; }
        header.top {
            background: var(--accent);
            color: #fff;
            padding: 18px 0 0;
        }
        header.top h1 { margin: 0; font-size: 1.35em; }
        header.top .sub { opacity: 0.85; font-size: 0.9em; margin-bottom: 14px; }

        /* Live preview of the LED panel */
        .preview-card {
            background: #000;
            border-radius: 12px;
            padding: 10px;
            text-align: center;
        }
        #matrix-preview {
            image-rendering: pixelated;
            width: 100%;
            max-width: 480px;
            aspect-ratio: 2 / 1;
            height: auto;
            display: block;
            margin: 0 auto;
            background: #000;
        }
        .now-showing {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            color: #ddd;
            font-size: 0.9em;
            padding-top: 8px;
        }
        .dot { width: 9px; height: 9px; border-radius: 50%; background: #888; flex: none; }
        .dot.on { background: #3ad07a; }
        .dot.off { background: #e05050; }

        /* Tabs */
        nav.tabs {
            display: flex;
            gap: 4px;
            margin-top: 16px;
            overflow-x: auto;
        }
        nav.tabs button {
            flex: 1;
            background: transparent;
            color: rgba(255,255,255,0.8);
            border: none;
            padding: 12px 10px;
            font-size: 0.95em;
            font-weight: 600;
            border-radius: 10px 10px 0 0;
            cursor: pointer;
            white-space: nowrap;
        }
        nav.tabs button.active { background: var(--bg); color: var(--accent); }
        .tab-content { display: none; padding-top: 18px; }
        .tab-content.active { display: block; }
        .tab-intro { color: var(--muted); margin: 0 0 14px; }

        /* Cards */
        .card {
            background: var(--card);
            border: 1px solid var(--line);
            border-radius: 12px;
            margin-bottom: 14px;
            overflow: hidden;
        }
        .card > h2, details.card > summary {
            font-size: 1.05em;
            margin: 0;
            padding: 14px 16px;
        }
        details.card > summary {
            cursor: pointer;
            list-style: none;
            display: flex;
            align-items: center;
            font-weight: 700;
        }
        details.card > summary::-webkit-details-marker { display: none; }
        details.card > summary::after {
            content: "";
            margin-left: auto;
            width: 9px; height: 9px;
            border-right: 2px solid var(--muted);
            border-bottom: 2px solid var(--muted);
            transform: rotate(45deg);
            transition: transform 0.15s;
        }
        details.card[open] > summary::after { transform: rotate(-135deg); }
        details.card[open] > summary { border-bottom: 1px solid var(--line); }
        .summary-note { font-weight: 400; color: var(--muted); font-size: 0.85em; margin-left: 8px; }
        @media (max-width: 480px) { .summary-note { display: none; } }
        .card-body { padding: 4px 16px 16px; }
        .card-body > p.hint:first-child { margin-top: 12px; }
        h3.group {
            font-size: 0.78em;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: var(--muted);
            margin: 18px 0 2px;
        }

        /* A labelled row: text + help icon on the left, control on the right */
        .row {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 11px 0;
            border-bottom: 1px solid var(--line);
        }
        .row:last-child { border-bottom: none; }
        .row > label { flex: 1; cursor: pointer; }
        .row .control { margin-left: auto; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; justify-content: flex-end; min-width: 0; }
        .field { padding: 12px 0; }
        .field > label { display: block; font-weight: 600; margin-bottom: 6px; }
        .label-line { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
        .label-line label { font-weight: 600; }
        .hint { color: var(--muted); font-size: 0.88em; margin: 6px 0 0; }

        input[type=text], input[type=password], input[type=time], select, textarea {
            width: 100%;
            padding: 10px 12px;
            border: 1px solid #c8cfd9;
            border-radius: 8px;
            font-size: 16px;
            font-family: inherit;
            background: #fff;
            color: var(--text);
        }
        input[type=time] { width: auto; }
        textarea { min-height: 70px; resize: vertical; }
        input:focus, select:focus, textarea:focus { outline: 2px solid var(--accent); outline-offset: 1px; }

        /* On/off switches */
        input.switch {
            appearance: none;
            -webkit-appearance: none;
            width: 46px; height: 26px;
            border-radius: 13px;
            background: #c4cad3;
            position: relative;
            cursor: pointer;
            flex: none;
            margin: 0;
            transition: background 0.15s;
        }
        input.switch::after {
            content: "";
            position: absolute;
            top: 3px; left: 3px;
            width: 20px; height: 20px;
            border-radius: 50%;
            background: #fff;
            box-shadow: 0 1px 3px rgba(0,0,0,0.3);
            transition: left 0.15s;
        }
        input.switch:checked { background: var(--good); }
        input.switch:checked::after { left: 23px; }
        input.switch:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

        /* Sliders */
        input[type=range] { flex: 1; accent-color: var(--accent); min-width: 120px; }
        .slider-row { display: flex; align-items: center; gap: 10px; }
        .slider-row .end { font-size: 0.8em; color: var(--muted); }
        .value-pill {
            min-width: 52px;
            text-align: center;
            font-weight: 700;
            font-size: 0.9em;
            color: var(--accent);
        }

        /* Help "?" icons and their pop-up */
        button.help {
            width: 20px; height: 20px;
            border-radius: 50%;
            border: 1px solid #b6bec9;
            background: #fff;
            color: var(--muted);
            font-size: 12px;
            font-weight: 700;
            line-height: 1;
            padding: 0;
            cursor: help;
            flex: none;
        }
        button.help:hover, button.help:focus-visible { background: var(--accent); color: #fff; border-color: var(--accent); }
        #help-popup {
            position: fixed;
            z-index: 2000;
            max-width: 280px;
            background: #1d2433;
            color: #fff;
            font-size: 0.86em;
            line-height: 1.4;
            padding: 10px 12px;
            border-radius: 8px;
            box-shadow: 0 6px 20px rgba(0,0,0,0.25);
            pointer-events: none;
            opacity: 0;
            transition: opacity 0.12s;
        }
        #help-popup.visible { opacity: 1; }

        /* Team pickers */
        .team-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px; }
        .team-option {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px 12px;
            border: 2px solid var(--line);
            border-radius: 10px;
            cursor: pointer;
            font-weight: 600;
        }
        .team-option input { position: absolute; opacity: 0; pointer-events: none; }
        .team-option:has(input:checked) { border-color: var(--accent); background: #f5f7fb; }
        .team-option:has(input:focus-visible) { outline: 2px solid var(--accent); }
        .team-option img { width: 32px; height: 32px; object-fit: contain; background: #111; border-radius: 6px; padding: 3px; box-sizing: border-box; }

        /* Choice list (radio options) */
        .choice {
            display: flex;
            gap: 10px;
            align-items: flex-start;
            padding: 10px 12px;
            border: 1px solid var(--line);
            border-radius: 10px;
            margin-top: 8px;
            cursor: pointer;
        }
        .choice:has(input:checked) { border-color: var(--accent); background: #f5f7fb; }
        .choice input { margin-top: 4px; accent-color: var(--accent); }
        .choice strong { display: block; }
        .choice span { color: var(--muted); font-size: 0.88em; }

        /* Buttons */
        button.btn {
            display: inline-block;
            padding: 11px 18px;
            border: none;
            border-radius: 9px;
            font-size: 15px;
            font-weight: 600;
            cursor: pointer;
            background: var(--accent);
            color: #fff;
        }
        button.btn:disabled { opacity: 0.5; cursor: not-allowed; }
        button.btn.light { background: #e7eaf0; color: var(--text); }
        button.btn.danger { background: var(--bad); }
        button.btn.wide { width: 100%; }
        .btn-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
        .btn-row .btn { flex: 1 1 140px; }

        .notice {
            background: var(--warn-bg);
            color: var(--warn-text);
            border-radius: 10px;
            padding: 12px 14px;
            font-size: 0.92em;
            margin: 12px 0;
        }
        .facts { display: grid; grid-template-columns: auto 1fr; gap: 6px 14px; font-size: 0.93em; margin: 12px 0; }
        .facts dt { color: var(--muted); }
        .facts dd { margin: 0; font-weight: 600; word-break: break-all; }

        .status {
            margin-top: 12px;
            padding: 10px 12px;
            border-radius: 8px;
            display: none;
            font-size: 0.92em;
        }
        .status.success { background: #e3f5ea; color: #155a32; }
        .status.error { background: #fde8e8; color: #8a1c1c; }

        .network-list { border: 1px solid var(--line); border-radius: 10px; margin: 10px 0; max-height: 240px; overflow-y: auto; }
        .network-item { padding: 11px 12px; border-bottom: 1px solid var(--line); cursor: pointer; display: flex; }
        .network-item:last-child { border-bottom: none; }
        .network-item:hover { background: #f5f7fb; }
        .signal { margin-left: auto; color: var(--muted); font-size: 0.9em; }

        .service-status { font-weight: 700; }
        .service-status.running { color: var(--good); }
        .service-status.stopped { color: var(--bad); }

        .log-viewer {
            background: #16191f;
            color: #d4d4d4;
            padding: 12px;
            border-radius: 8px;
            font-family: Menlo, Consolas, monospace;
            font-size: 12px;
            height: 360px;
            overflow-y: auto;
            white-space: pre-wrap;
            word-wrap: break-word;
            margin-top: 10px;
        }

        /* Sticky save bar for the settings tabs */
        .save-bar {
            position: fixed;
            left: 0; right: 0; bottom: 0;
            background: #fff;
            border-top: 1px solid var(--line);
            box-shadow: 0 -4px 16px rgba(0,0,0,0.06);
            padding: 12px 0;
            z-index: 500;
        }
        .save-bar.hidden { display: none; }
        .save-bar .page { display: flex; align-items: center; gap: 12px; }
        .save-bar .save-msg { flex: 1; color: var(--muted); font-size: 0.9em; }
        .save-bar.dirty .save-msg { color: var(--warn-text); font-weight: 600; }
        .save-bar .status { margin: 0; }

        /* Reboot pop-up */
        .reboot-prompt-backdrop {
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.55);
            z-index: 1000;
            align-items: center;
            justify-content: center;
            padding: 16px;
        }
        .reboot-prompt-backdrop.visible { display: flex; }
        .reboot-prompt-box {
            background: #fff;
            border-radius: 14px;
            padding: 22px;
            max-width: 440px;
            width: 100%;
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.3);
        }
        .reboot-prompt-box h3 { margin: 0 0 10px; }
        .reboot-prompt-box p { margin: 0 0 8px; }
        .reboot-prompt-keys { font-weight: 700; }
    </style>
</head>
<body>
    {% macro help(text) -%}
        <button type="button" class="help" data-help="{{ text }}" aria-label="Help: {{ text }}">?</button>
    {%- endmacro %}

    {% macro toggle(id, title, text) -%}
        <div class="row">
            <label for="{{ id }}">{{ title }}</label>
            {{ help(text) }}
            <input type="checkbox" class="switch" id="{{ id }}">
        </div>
    {%- endmacro %}

    {% macro speed(id, title) -%}
        <div class="row">
            <label for="{{ id }}" style="flex: 0 0 120px;">{{ title }}</label>
            <div class="slider-row" style="flex: 1;">
                <span class="end">Slow</span>
                <input type="range" id="{{ id }}" min="1" max="10" value="5">
                <span class="end">Fast</span>
                <span class="value-pill" id="{{ id }}_val">5</span>
            </div>
        </div>
    {%- endmacro %}

    <div id="help-popup" role="tooltip"></div>

    <div class="reboot-prompt-backdrop" id="reboot-prompt">
        <div class="reboot-prompt-box">
            <h3>Restart needed</h3>
            <p>Your settings were saved. This change only shows up after the
               scoreboard restarts:</p>
            <p><span class="reboot-prompt-keys" id="reboot-prompt-keys"></span></p>
            <p class="hint">A restart takes about two minutes, and the screen
               is blank while it happens.</p>
            <div class="btn-row">
                <button onclick="rebootFromPrompt(this)" class="btn">Restart now</button>
                <button onclick="scheduleRebootFromPrompt(this)" class="btn light">Tonight at 4 AM</button>
                <button onclick="dismissRebootPrompt()" class="btn light">Not now</button>
            </div>
            <div id="reboot-prompt-status" class="status"></div>
        </div>
    </div>

    <header class="top">
        <div class="page">
            <h1>{{ active_team.short_name }} Scoreboard</h1>
            <div class="sub">Settings for {{ hostname }}</div>

            <div class="preview-card">
                <img id="matrix-preview" alt="" onload="this.style.visibility='visible'" onerror="this.style.visibility='hidden'">
                <div class="now-showing">
                    <span class="dot" id="status-dot"></span>
                    <span>Now showing: <span id="scoreboard-status">checking...</span></span>
                </div>
            </div>

            <nav class="tabs">
                <button class="active" data-tab="config" onclick="switchTab('config')">Display</button>
                <button data-tab="location" onclick="switchTab('location')">Location</button>
                <button data-tab="wifi" onclick="switchTab('wifi')">Wi-Fi</button>
                <button data-tab="device" onclick="switchTab('device')">Device</button>
            </nav>
        </div>
    </header>

    <main class="page">

        <!-- ============ DISPLAY ============ -->
        <div id="config-tab" class="tab-content active">
            <p class="tab-intro">Choose your teams and what appears on the scoreboard. Tap
                <strong>?</strong> next to anything for an explanation, then press
                <strong>Save changes</strong> at the bottom.</p>

            <details class="card" open>
                <summary>Your teams</summary>
                <div class="card-body">
                    <div class="label-line" style="margin-top: 12px;">
                        <strong>Baseball team</strong>
                        {{ help("The baseball team the scoreboard follows. Its games, colors and logo are used throughout the display. The scoreboard needs a restart after you change this.") }}
                    </div>
                    <div class="team-grid">
                    {% for slug, t in teams.items() %}
                        <label class="team-option">
                            <input type="radio" name="team" value="{{ slug }}">
                            <img src="/team_logo/{{ slug }}" alt="">
                            <span>{{ t.name }}</span>
                        </label>
                    {% endfor %}
                    </div>

                    <div class="label-line" style="margin-top: 18px;">
                        <strong>Football team</strong>
                        {{ help("The NFL team used for the football game and football news screens. The scoreboard needs a restart after you change this.") }}
                    </div>
                    <div class="team-grid">
                    {% for slug, t in nfl_teams.items() %}
                        <label class="team-option">
                            <input type="radio" name="nfl_team" value="{{ slug }}">
                            <img src="/nfl_logo/{{ slug }}" alt="">
                            <span>{{ t.name }}</span>
                        </label>
                    {% endfor %}
                    </div>

                    <div class="label-line" style="margin-top: 18px;">
                        <strong>College basketball team</strong>
                        {{ help("The college team used for the basketball screens: games, rankings, conference standings, news and trivia. The scoreboard needs a restart after you change this.") }}
                    </div>
                    <div class="team-grid">
                    {% for slug, t in ncaab_teams.items() %}
                        <label class="team-option">
                            <input type="radio" name="ncaab_team" value="{{ slug }}">
                            <img src="/ncaab_logo/{{ slug }}" alt="">
                            <span>{{ t.name }}</span>
                        </label>
                    {% endfor %}
                    </div>
                </div>
            </details>

            <details class="card" open>
                <summary>Brightness</summary>
                <div class="card-body">
                    <div class="field">
                        <div class="label-line">
                            <label for="brightness">Screen brightness</label>
                            {{ help("How bright the lights are. Lower it if the scoreboard feels too bright for the room. Takes effect within about 10 seconds of saving.") }}
                        </div>
                        <div class="slider-row">
                            <span class="end">Dim</span>
                            <input type="range" id="brightness" min="10" max="100" value="100">
                            <span class="end">Bright</span>
                            <span class="value-pill" id="brightness_val">100%</span>
                        </div>
                    </div>

                    <div class="row">
                        <label for="dim_enabled">Dim automatically at night</label>
                        {{ help("Turns the brightness down during the hours you pick below, then back up in the morning. Overnight times like 10:00 PM to 7:00 AM work fine.") }}
                        <input type="checkbox" class="switch" id="dim_enabled">
                    </div>
                    <div id="dim-options">
                        <div class="row">
                            <label for="dim_start">Dim from</label>
                            <div class="control">
                                <input type="time" id="dim_start" value="22:00">
                                <span>to</span>
                                <input type="time" id="dim_end" value="07:00" aria-label="Dim until">
                            </div>
                        </div>
                        <div class="field">
                            <label for="dim_brightness">Night-time brightness</label>
                            <div class="slider-row">
                                <span class="end">Dim</span>
                                <input type="range" id="dim_brightness" min="10" max="100" value="30">
                                <span class="end">Bright</span>
                                <span class="value-pill" id="dim_brightness_val">30%</span>
                            </div>
                        </div>
                    </div>
                </div>
            </details>

            <details class="card" open>
                <summary>When to show baseball games</summary>
                <div class="card-body">
                    <div class="field">
                        <div class="label-line">
                            <label for="display_mode">Game mode</label>
                            {{ help("Decides how game-day information and the other screens (weather, news, trivia and so on) share the scoreboard. Most people should leave this on Automatic.") }}
                        </div>
                        <select id="display_mode">
                            <option value="auto">Automatic (recommended): games during the season, other screens the rest of the year</option>
                            <option value="game">Games first: always show the game when there is one</option>
                            <option value="offseason">Mix: show the next game and standings, then the other screens</option>
                            <option value="no_games">No games: only show the other screens</option>
                        </select>
                        <p class="hint">Live games always take over the screen unless you choose “No games”.</p>
                    </div>
                </div>
            </details>

            <details class="card" open>
                <summary>What to show <span class="summary-note">Turn screens on or off</span></summary>
                <div class="card-body">
                    <h3 class="group">Baseball</h3>
                    {{ toggle('enable_cubs_facts', 'Team trivia & your message', 'Fun facts about your baseball team, shown together with the custom message you write in the “Your message” section below.') }}
                    {{ toggle('enable_cubs_news', 'Team news headlines', 'Scrolls the latest news headlines about your baseball team.') }}
                    {{ toggle('enable_cubs_history', 'This day in team history', 'Shows something that happened to your team on today’s date in years past.') }}
                    {{ toggle('enable_spring_training', 'Spring Training countdown', 'During the winter, counts down the days until Spring Training begins.') }}
                    {{ toggle('enable_playoff_race', 'Playoff race', 'From July through September, shows where your team stands in the race for the playoffs.') }}
                    {{ toggle('enable_allstar', 'All-Star Game', 'Shows the All-Star Game in July.') }}
                    {{ toggle('enable_clock', 'Wrigley-style clock', 'A clock styled after the classic Wrigley Field scoreboard.') }}

                    <h3 class="group">Football, basketball &amp; golf</h3>
                    {{ toggle('enable_bears', 'NFL team games', 'During football season, shows your football team’s next game or the live score.') }}
                    {{ toggle('enable_bears_news', 'NFL team news', 'Scrolls the latest news headlines about your football team.') }}
                    {{ toggle('nfl_preempt_mlb', 'Football beats baseball', 'When ON, a live football game takes over the whole screen, even during a baseball game. When OFF (the usual setting), baseball comes first.') }}
                    {{ toggle('enable_ncaab', 'College basketball games', 'During basketball season, shows your college team’s next game, a game-day countdown, the live score and the final. A live game takes the screen whenever no baseball game is on.') }}
                    {{ toggle('enable_ncaab_rankings', 'College basketball rankings', 'Shows your team’s national rank and the AP Top 25.') }}
                    {{ toggle('enable_ncaab_standings', 'Conference standings', 'Shows where your college team stands in its conference.') }}
                    {{ toggle('enable_ncaab_news', 'College basketball news', 'Scrolls the latest news headlines about your college team.') }}
                    {{ toggle('enable_ncaab_facts', 'College basketball trivia', 'Shows fun facts about your college team.') }}
                    {{ toggle('enable_pga', 'Golf leaderboard', 'During golf season, shows the current PGA Tour tournament leaderboard.') }}
                    {{ toggle('enable_pga_news', 'Golf news', 'Scrolls the latest PGA Tour news headlines.') }}
                    {{ toggle('enable_pga_facts', 'Golf trivia', 'Shows fun facts and records from the PGA Tour.') }}

                    <h3 class="group">News &amp; weather</h3>
                    {{ toggle('enable_weather', 'Weather', 'Current conditions and forecast for your ZIP code, with animated rain, snow and clouds. Set your ZIP code on the Location tab.') }}
                    {{ toggle('enable_newsmax', 'Newsmax headlines', 'Scrolls top national news headlines from Newsmax.') }}
                    {{ toggle('enable_usatoday', 'USA Today headlines', 'Scrolls top national news headlines from USA Today.') }}
                    {{ toggle('enable_stocks', 'Stock market ticker', 'Shows how the major stock market indexes are doing.') }}

                    <h3 class="group">Sky &amp; planes</h3>
                    {{ toggle('enable_sky', 'Sun & moon', 'Shows sunrise and sunset times and tonight’s moon phase.') }}
                    {{ toggle('enable_iss', 'Space Station tracker', 'Shows where the International Space Station is right now.') }}
                    {{ toggle('enable_flights', 'Planes overhead', 'Shows airplanes currently flying near you: airline, where they are going, and how high they are. Set your location on the Location tab.') }}
                    {{ toggle('enable_flight_radar', 'Radar view', 'A full-screen radar picture showing nearby planes as dots.') }}
                    {{ toggle('flights_between_displays', 'Planes between every screen', 'Shows nearby planes for about 45 seconds between each of the other screens. Leave this off if you want planes to appear only in their normal turn.') }}

                    <h3 class="group">Faith &amp; fun</h3>
                    {{ toggle('enable_bible', 'Bible verse of the day', 'Shows a daily Bible verse.') }}
                    {{ toggle('enable_bible_facts', 'Bible facts', 'Shows interesting facts about the Bible.') }}
                    {{ toggle('enable_celebrations', 'Holidays & birthdays', 'Celebrates holidays and special days with a themed screen.') }}
                    {{ toggle('enable_holiday_facts', 'Holiday fun facts', 'On holidays like Christmas, Easter and Thanksgiving, shows a themed picture and fun facts about the day. Only appears on the holiday itself.') }}
                </div>
            </details>

            <details class="card" open>
                <summary>Your message</summary>
                <div class="card-body">
                    <div class="field">
                        <div class="label-line">
                            <label for="custom_message">Message to scroll across the screen</label>
                            {{ help("Your own words, scrolled across the scoreboard together with the team trivia. Make sure “Team trivia & your message” is turned on above.") }}
                        </div>
                        <textarea id="custom_message">{{ config.custom_message }}</textarea>
                    </div>
                </div>
            </details>

            <details class="card">
                <summary>Scrolling speed <span class="summary-note">Optional</span></summary>
                <div class="card-body">
                    <p class="hint">How fast the moving text travels across each screen. 5 is the normal speed.</p>
                    {{ speed('scroll_speed_cubs_facts', 'Team trivia') }}
                    {{ speed('scroll_speed_cubs_news', 'Team news') }}
                    {{ speed('scroll_speed_spring_training', 'Spring Training') }}
                    {{ speed('scroll_speed_bears', 'NFL games') }}
                    {{ speed('scroll_speed_bears_news', 'NFL news') }}
                    {{ speed('scroll_speed_ncaab_news', 'College basketball news') }}
                    {{ speed('scroll_speed_ncaab_facts', 'College basketball trivia') }}
                    {{ speed('scroll_speed_pga', 'Golf leaderboard') }}
                    {{ speed('scroll_speed_pga_news', 'Golf news') }}
                    {{ speed('scroll_speed_pga_facts', 'Golf trivia') }}
                    {{ speed('scroll_speed_newsmax', 'Newsmax') }}
                    {{ speed('scroll_speed_usatoday', 'USA Today') }}
                    {{ speed('scroll_speed_stocks', 'Stocks') }}
                    {{ speed('scroll_speed_flights', 'Planes') }}
                    {{ speed('scroll_speed_bible', 'Bible verse') }}
                    {{ speed('scroll_speed_bible_facts', 'Bible facts') }}
                    {{ speed('scroll_speed_holiday_facts', 'Holiday fun facts') }}
                </div>
            </details>
        </div>

        <!-- ============ LOCATION ============ -->
        <div id="location-tab" class="tab-content">
            <p class="tab-intro">Tell the scoreboard where it is, so it can show your local weather and the planes flying over you.</p>

            <section class="card">
                <h2>Weather</h2>
                <div class="card-body">
                    <div class="field">
                        <div class="label-line">
                            <label for="zip_code">ZIP code</label>
                            {{ help("The 5-digit ZIP code used for the weather screen.") }}
                        </div>
                        <input type="text" id="zip_code" inputmode="numeric" placeholder="e.g. 60613" value="{{ config.zip_code }}">
                    </div>
                </div>
            </section>

            <section class="card">
                <h2>Planes overhead</h2>
                <div class="card-body">
                    <div class="field">
                        <div class="label-line">
                            <label for="flight_tracking_address">Your town or address</label>
                            {{ help("Type a city and state or a street address, then press Find. This fills in the exact map position below. Looking up an address needs an OpenWeather key (see More options).") }}
                        </div>
                        <input type="text" id="flight_tracking_address" placeholder="e.g. Rochester, IL">
                        <div class="btn-row">
                            <button type="button" onclick="geocodeAddress()" class="btn light">Find this location</button>
                        </div>
                        <p class="hint" id="coords-text"></p>
                    </div>

                    <div class="row">
                        <label for="flight_tracking_latitude">Latitude</label>
                        {{ help("The north–south map position. Filled in for you when you use Find. You can also copy it from Google Maps by right-clicking your home.") }}
                        <div class="control"><input type="text" id="flight_tracking_latitude" placeholder="e.g. 39.7500" style="width: 150px;"></div>
                    </div>
                    <div class="row">
                        <label for="flight_tracking_longitude">Longitude</label>
                        {{ help("The east–west map position. In the United States this is a negative number.") }}
                        <div class="control"><input type="text" id="flight_tracking_longitude" placeholder="e.g. -89.6653" style="width: 150px;"></div>
                    </div>

                    <div class="field">
                        <div class="label-line">
                            <label for="flight_max_range_nm">How far away to look</label>
                            {{ help("Only planes within this distance are shown. A smaller number means only planes almost directly overhead. Distance is in nautical miles (1 nautical mile ≈ 1.15 regular miles).") }}
                        </div>
                        <div class="slider-row">
                            <span class="end">Near</span>
                            <input type="range" id="flight_max_range_nm" min="10" max="100" value="{{ config.flight_max_range_nm or 50 }}">
                            <span class="end">Far</span>
                            <span class="value-pill"><span id="flight_range_val">{{ config.flight_max_range_nm or 50 }}</span> NM</span>
                        </div>
                    </div>
                </div>
            </section>

            <details class="card">
                <summary>More options <span class="summary-note">Most people can skip this</span></summary>
                <div class="card-body">
                    <div class="field">
                        <div class="label-line">
                            <strong>Where plane information comes from</strong>
                            {{ help("Where the scoreboard gets its list of nearby planes. The free internet service works with no extra equipment.") }}
                        </div>
                        <label class="choice">
                            <input type="radio" name="flight_source" id="flight_source_adsb_lol" value="adsb_lol">
                            <div><strong>Internet (recommended)</strong><span>Free service from adsb.lol, no setup needed.</span></div>
                        </label>
                        <label class="choice">
                            <input type="radio" name="flight_source" id="flight_source_local" value="local">
                            <div><strong>My own antenna</strong><span>Only if you have a plane-tracking receiver (like PiAware) on your network.</span></div>
                        </label>
                        <div id="local_receiver_url_wrapper" class="field" style="display: none;">
                            <label for="adsb_receiver_url">Receiver address</label>
                            <input type="text" id="adsb_receiver_url"
                                   placeholder="http://piaware.local/skyaware/data/aircraft.json"
                                   value="{{ config.adsb_receiver_url }}">
                        </div>
                    </div>

                    <div class="field">
                        <div class="label-line">
                            <label for="weather_api_key">OpenWeather key</label>
                            {{ help("Only needed for the “Find this location” button. Weather works without it. Get a free key at openweathermap.org.") }}
                        </div>
                        <input type="text" id="weather_api_key" placeholder="Optional" value="{{ config.weather_api_key }}">
                    </div>

                    <div class="field">
                        <div class="label-line">
                            <label for="airlabs_api_key">AirLabs key</label>
                            {{ help("Optional backup for looking up where planes are flying to. Destinations already work without it.") }}
                        </div>
                        <input type="text" id="airlabs_api_key" placeholder="Optional" value="{{ config.airlabs_api_key }}">
                    </div>
                </div>
            </details>
        </div>

        <!-- ============ WI-FI ============ -->
        <div id="wifi-tab" class="tab-content">
            <p class="tab-intro">Connect the scoreboard to your home Wi-Fi.</p>

            <section class="card">
                <h2>Current connection</h2>
                <div class="card-body">
                    <dl class="facts">
                        <dt>Status</dt><dd>{{ connection_mode }}</dd>
                        <dt>Network</dt><dd>{{ current_network }}</dd>
                    </dl>
                </div>
            </section>

            <section class="card">
                <h2>Join a network</h2>
                <div class="card-body">
                    <div class="btn-row">
                        <button onclick="scanNetworks()" class="btn light">Find nearby networks</button>
                    </div>
                    <div id="network-list" class="network-list" style="display:none;"></div>

                    <div class="field">
                        <div class="label-line">
                            <label for="ssid">Network name</label>
                            {{ help("The name of your Wi-Fi network. Tap one from the list above, or type it exactly, including capital letters.") }}
                        </div>
                        <input type="text" id="ssid" placeholder="Your Wi-Fi name" autocapitalize="off" autocorrect="off">
                    </div>

                    <div class="field">
                        <div class="label-line">
                            <label for="password">Wi-Fi password</label>
                            {{ help("The password you use to join this Wi-Fi network on your phone. It is saved only on the scoreboard.") }}
                        </div>
                        <input type="password" id="password" placeholder="Wi-Fi password">
                    </div>

                    <div class="notice">After connecting, this page will stop responding. Join your phone or
                        computer to the same Wi-Fi, then open
                        <strong>http://{{ hostname }}.local/admin</strong> to come back.</div>

                    <button onclick="connectWifi()" class="btn wide">Connect</button>
                    <div id="wifi-status" class="status"></div>
                </div>
            </section>
        </div>

        <!-- ============ DEVICE ============ -->
        <div id="device-tab" class="tab-content">
            <p class="tab-intro">Restart the scoreboard, rename it, or look at troubleshooting details.</p>

            <section class="card">
                <h2>Restart</h2>
                <div class="card-body">
                    <p class="hint">If the screen looks stuck or blank, try <strong>Restart display</strong> first.
                        If that doesn't fix it, use <strong>Restart everything</strong>.</p>
                    <div class="row">
                        <span style="flex: 1;">Display program</span>
                        {{ help("The program that draws on the scoreboard. Running means it is working normally.") }}
                        <span id="service-status-badge" class="service-status">Checking...</span>
                    </div>
                    <div class="btn-row">
                        <button onclick="controlService(this, 'restart')" class="btn">Restart display</button>
                        <button onclick="rebootDevice(this)" class="btn light">Restart everything</button>
                    </div>
                    <details style="margin-top: 12px;">
                        <summary class="hint" style="cursor: pointer;">Turn the display off or on</summary>
                        <div class="btn-row">
                            <button onclick="controlService(this, 'stop')" class="btn danger">Turn display off</button>
                            <button onclick="controlService(this, 'start')" class="btn light">Turn display on</button>
                        </div>
                    </details>
                    <div id="service-control-status" class="status"></div>
                </div>
            </section>

            <section class="card">
                <h2>Scoreboard name</h2>
                <div class="card-body">
                    <dl class="facts">
                        <dt>Settings page</dt><dd>http://{{ hostname }}.local/admin</dd>
                        <dt>IP address</dt><dd>{{ ip_address }}</dd>
                    </dl>
                    <div class="field">
                        <div class="label-line">
                            <label for="new_hostname">Name</label>
                            {{ help("The name is part of this page’s web address. If you have more than one scoreboard on the same Wi-Fi, give each one a different name. Use lowercase letters, numbers and dashes only.") }}
                        </div>
                        <input type="text" id="new_hostname" placeholder="e.g. cubsmarquee-1" pattern="[a-z0-9\-]+" value="{{ hostname }}" autocapitalize="off" autocorrect="off">
                        <p class="hint">After renaming, open this page at http://<em>new-name</em>.local/admin</p>
                    </div>
                    <button onclick="changeHostname()" class="btn light wide">Rename scoreboard</button>
                    <div id="hostname-status" class="status"></div>
                </div>
            </section>

            <details class="card">
                <summary>Troubleshooting logs <span class="summary-note">For technical help</span></summary>
                <div class="card-body">
                    <p class="hint">Logs are a record of what the scoreboard has been doing. Someone helping you fix a problem may ask you for these.</p>
                    <div class="btn-row">
                        <button onclick="loadLogs('application')" class="btn light">Activity</button>
                        <button onclick="loadLogs('error')" class="btn light">Errors</button>
                        <button onclick="loadLogs('wifi')" class="btn light">Wi-Fi</button>
                    </div>
                    <p class="hint"><strong id="log-filename">Choose a log above</strong>
                        &middot; <a href="#" onclick="refreshCurrentLog(); return false;">Refresh</a></p>
                    <div id="log-content" class="log-viewer">Choose a log above to view it.</div>
                </div>
            </details>
        </div>
    </main>

    <div class="save-bar" id="save-bar">
        <div class="page">
            <div class="save-msg" id="save-msg">All changes saved</div>
            <div id="config-status" class="status"></div>
            <button onclick="saveConfig()" class="btn" id="save-button">Save changes</button>
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

        // Plain-English names for the settings that need a restart
        // (REBOOT_REQUIRED_KEYS on the server).
        const REBOOT_KEY_NAMES = {
            team: 'Baseball team',
            nfl_team: 'Football team',
            ncaab_team: 'College basketball team',
        };

        // ---- Help pop-ups: hover, focus or tap any "?" button ----
        const helpPopup = document.getElementById('help-popup');
        let helpOwner = null;
        function showHelp(btn) {
            helpOwner = btn;
            helpPopup.textContent = btn.dataset.help;
            helpPopup.classList.add('visible');
            const r = btn.getBoundingClientRect();
            const w = helpPopup.offsetWidth, h = helpPopup.offsetHeight;
            let left = r.left + r.width / 2 - w / 2;
            left = Math.max(8, Math.min(left, window.innerWidth - w - 8));
            let top = r.top - h - 8;
            if (top < 8) top = r.bottom + 8;
            helpPopup.style.left = left + 'px';
            helpPopup.style.top = top + 'px';
        }
        function hideHelp() {
            helpOwner = null;
            helpPopup.classList.remove('visible');
        }
        document.querySelectorAll('button.help').forEach(function(btn) {
            btn.addEventListener('mouseenter', () => showHelp(btn));
            btn.addEventListener('mouseleave', hideHelp);
            btn.addEventListener('focus', () => showHelp(btn));
            btn.addEventListener('blur', hideHelp);
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                if (helpOwner === btn) { hideHelp(); } else { showHelp(btn); }
            });
        });
        window.addEventListener('scroll', function() {
            if (helpOwner) showHelp(helpOwner);
        }, { passive: true });

        // Poll the scoreboard heartbeat for the status row
        async function refreshScoreboardStatus() {
            const el = document.getElementById('scoreboard-status');
            const dot = document.getElementById('status-dot');
            try {
                const resp = await fetch('/scoreboard_status');
                const data = await resp.json();
                if (!data.available) {
                    el.textContent = 'waiting for the scoreboard to start';
                    dot.className = 'dot';
                } else if (data.stale) {
                    el.textContent = data.state + ' (not updated for ' + Math.round(data.age_seconds / 60) + ' min)';
                    dot.className = 'dot off';
                } else {
                    el.textContent = data.state + (data.detail ? ' - ' + data.detail : '');
                    dot.className = 'dot on';
                }
            } catch (e) {
                el.textContent = 'unavailable';
                dot.className = 'dot off';
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

        // ---- Unsaved-changes indicator on the save bar ----
        let isDirty = false;
        function setDirty(dirty) {
            isDirty = dirty;
            document.getElementById('save-bar').classList.toggle('dirty', dirty);
            document.getElementById('save-msg').textContent =
                dirty ? 'You have unsaved changes' : 'All changes saved';
        }
        window.addEventListener('beforeunload', function(e) {
            if (isDirty) { e.preventDefault(); e.returnValue = ''; }
        });

        function updateDimOptions() {
            document.getElementById('dim-options').style.opacity =
                document.getElementById('dim_enabled').checked ? '1' : '0.45';
        }

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

            const ncaabSlug = config.ncaab_team || 'illini';
            const ncaabRadio = document.querySelector(
                `input[name="ncaab_team"][value="${ncaabSlug}"]`);
            if (ncaabRadio) ncaabRadio.checked = true;

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
            ['enable_ncaab', 'enable_ncaab_rankings', 'enable_ncaab_standings',
             'enable_ncaab_news', 'enable_ncaab_facts'].forEach(function(key) {
                document.getElementById(key).checked = config[key] !== false;
            });
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
            document.getElementById('enable_holiday_facts').checked = config.enable_holiday_facts !== false;
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
            document.getElementById('dim_enabled').addEventListener('change', updateDimOptions);
            updateDimOptions();

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
            const rangeSlider = document.getElementById('flight_max_range_nm');
            rangeSlider.value = config.flight_max_range_nm || 50;
            document.getElementById('flight_range_val').textContent = config.flight_max_range_nm || 50;
            rangeSlider.addEventListener('input', function() {
                document.getElementById('flight_range_val').textContent = this.value;
            });

            // Load AirLabs API key
            document.getElementById('airlabs_api_key').value = config.airlabs_api_key || '';

            // Load scroll speed settings
            const speedFields = [
                'scroll_speed_bears', 'scroll_speed_bears_news',
                'scroll_speed_ncaab_news', 'scroll_speed_ncaab_facts',
                'scroll_speed_pga', 'scroll_speed_pga_news', 'scroll_speed_pga_facts',
                'scroll_speed_cubs_facts', 'scroll_speed_cubs_news',
                'scroll_speed_bible', 'scroll_speed_bible_facts',
                'scroll_speed_holiday_facts',
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

            // Any edit on the two settings tabs marks the page unsaved
            ['config-tab', 'location-tab'].forEach(function(id) {
                const tab = document.getElementById(id);
                tab.addEventListener('input', () => setDirty(true));
                tab.addEventListener('change', () => setDirty(true));
            });

            updateServiceStatus();
        };

        function switchTab(tabName) {
            document.querySelectorAll('.tab-content').forEach(
                tab => tab.classList.toggle('active', tab.id === tabName + '-tab'));
            document.querySelectorAll('nav.tabs button').forEach(
                btn => btn.classList.toggle('active', btn.dataset.tab === tabName));

            // The save bar belongs to the two settings tabs only
            document.getElementById('save-bar').classList.toggle(
                'hidden', tabName !== 'config' && tabName !== 'location');

            if (tabName === 'device') {
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
            networkList.innerHTML = '<div style="padding: 10px; text-align: center;">Looking for networks...</div>';
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
                        note.style.cssText = 'padding: 6px 12px; font-size: 12px; color: #888;';
                        note.textContent = 'Networks seen before the setup hotspot started';
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
                networkList.innerHTML = '<div style="padding: 10px; text-align: center; color: red;">Could not look for networks</div>';
            }
        }

        function selectNetwork(ssid) {
            document.getElementById('ssid').value = ssid;
            document.getElementById('password').focus();
        }

        async function connectWifi() {
            const ssid = document.getElementById('ssid').value;
            const password = document.getElementById('password').value;

            if (!ssid || !password) {
                showStatus('wifi-status', 'Please enter both the network name and the password', false);
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
                    button.textContent = 'Connect';
                }
            } catch (error) {
                showStatus('wifi-status', 'Connection error: ' + error.message, false);
                button.disabled = false;
                button.textContent = 'Connect';
            }
        }

        async function geocodeAddress() {
            const address = document.getElementById('flight_tracking_address').value;
            const apiKey = document.getElementById('weather_api_key').value;
            const coordsText = document.getElementById('coords-text');

            if (!address) {
                coordsText.textContent = 'Type your town or address first.';
                return;
            }

            if (!apiKey) {
                coordsText.textContent = 'Finding an address needs an OpenWeather key. Add one under More options below, or type the latitude and longitude yourself.';
                return;
            }

            coordsText.textContent = 'Looking up...';
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
                    coordsText.textContent =
                        `Found ${data.latitude.toFixed(4)}, ${data.longitude.toFixed(4)}. Check it looks right, then press Save changes.`;
                    setDirty(true);
                } else {
                    coordsText.textContent = 'Could not find that place: ' + data.message;
                }
            } catch (error) {
                coordsText.textContent = 'Could not find that place: ' + error.message;
            }
        }

        async function saveConfig() {
            const latValue = document.getElementById('flight_tracking_latitude').value;
            const lonValue = document.getElementById('flight_tracking_longitude').value;

            const checkedTeamRadio = document.querySelector('input[name="team"]:checked');
            const checkedNflRadio = document.querySelector('input[name="nfl_team"]:checked');
            const checkedNcaabRadio = document.querySelector('input[name="ncaab_team"]:checked');
            const config = {
                team: checkedTeamRadio ? checkedTeamRadio.value : 'cubs',
                nfl_team: checkedNflRadio ? checkedNflRadio.value : 'bears',
                ncaab_team: checkedNcaabRadio ? checkedNcaabRadio.value : 'illini',
                zip_code: document.getElementById('zip_code').value,
                weather_api_key: document.getElementById('weather_api_key').value,
                custom_message: document.getElementById('custom_message').value,
                display_mode: document.getElementById('display_mode').value,
                enable_weather: document.getElementById('enable_weather').checked,
                enable_allstar: document.getElementById('enable_allstar').checked,
                enable_bears: document.getElementById('enable_bears').checked,
                enable_bears_news: document.getElementById('enable_bears_news').checked,
                nfl_preempt_mlb: document.getElementById('nfl_preempt_mlb').checked,
                enable_ncaab: document.getElementById('enable_ncaab').checked,
                enable_ncaab_rankings: document.getElementById('enable_ncaab_rankings').checked,
                enable_ncaab_standings: document.getElementById('enable_ncaab_standings').checked,
                enable_ncaab_news: document.getElementById('enable_ncaab_news').checked,
                enable_ncaab_facts: document.getElementById('enable_ncaab_facts').checked,
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
                enable_holiday_facts: document.getElementById('enable_holiday_facts').checked,
                flights_between_displays: document.getElementById('flights_between_displays').checked,
                scroll_speed_bears: parseInt(document.getElementById('scroll_speed_bears').value),
                scroll_speed_bears_news: parseInt(document.getElementById('scroll_speed_bears_news').value),
                scroll_speed_ncaab_news: parseInt(document.getElementById('scroll_speed_ncaab_news').value),
                scroll_speed_ncaab_facts: parseInt(document.getElementById('scroll_speed_ncaab_facts').value),
                scroll_speed_pga: parseInt(document.getElementById('scroll_speed_pga').value),
                scroll_speed_pga_news: parseInt(document.getElementById('scroll_speed_pga_news').value),
                scroll_speed_pga_facts: parseInt(document.getElementById('scroll_speed_pga_facts').value),
                scroll_speed_cubs_facts: parseInt(document.getElementById('scroll_speed_cubs_facts').value),
                scroll_speed_cubs_news: parseInt(document.getElementById('scroll_speed_cubs_news').value),
                scroll_speed_bible: parseInt(document.getElementById('scroll_speed_bible').value),
                scroll_speed_bible_facts: parseInt(document.getElementById('scroll_speed_bible_facts').value),
                scroll_speed_holiday_facts: parseInt(document.getElementById('scroll_speed_holiday_facts').value),
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

            const button = document.getElementById('save-button');
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
                    setDirty(false);
                    // The server decides: it compares the saved values
                    // against the previous ones, so we only prompt when a
                    // reboot would actually change something. Everything
                    // else the running display picks up on its own.
                    if (data.reboot_required) {
                        showRebootPrompt(data.reboot_keys);
                        document.getElementById('save-msg').textContent = 'Saved. Restart needed.';
                    } else {
                        document.getElementById('save-msg').textContent =
                            'Saved! The scoreboard will update within a few minutes.';
                    }
                } else {
                    showStatus('config-status', 'Could not save: ' + data.message, false);
                }
            } catch (error) {
                showStatus('config-status', 'Could not save: ' + error.message, false);
            } finally {
                button.disabled = false;
                button.textContent = 'Save changes';
            }
        }

        async function changeHostname() {
            const newHostname = document.getElementById('new_hostname').value.toLowerCase().trim();
            const currentHostname = '{{ hostname }}';

            if (!newHostname) {
                showStatus('hostname-status', 'Please enter a name', false);
                return;
            }

            if (newHostname === currentHostname) {
                showStatus('hostname-status', 'That is already the scoreboard’s name', false);
                return;
            }

            // Validate hostname format
            const hostnamePattern = /^[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?$/;
            if (!hostnamePattern.test(newHostname)) {
                showStatus('hostname-status', 'Use only lowercase letters, numbers and dashes, and don’t start or end with a dash', false);
                return;
            }

            if (!confirm(`Rename the scoreboard from "${currentHostname}" to "${newHostname}"?\n\nAfterwards, open this page at:\nhttp://${newHostname}.local/admin`)) {
                return;
            }

            const button = event.target;
            button.disabled = true;
            button.textContent = 'Renaming...';

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
                    button.textContent = 'Rename scoreboard';
                }
            } catch (error) {
                showStatus('hostname-status', 'Error renaming: ' + error.message, false);
                button.disabled = false;
                button.textContent = 'Rename scoreboard';
            }
        }

        async function updateServiceStatus() {
            const badge = document.getElementById('service-status-badge');
            try {
                const response = await fetch('/service_status');
                const data = await response.json();

                if (data.running) {
                    badge.textContent = 'Running';
                    badge.className = 'service-status running';
                } else {
                    badge.textContent = 'Off';
                    badge.className = 'service-status stopped';
                }
            } catch (error) {
                badge.textContent = 'Unknown';
                badge.className = 'service-status';
            }
        }

        async function controlService(button, action) {
            if (action === 'stop' && !confirm('Turn the display off? The screen will stay dark until you turn it back on or restart.')) {
                return;
            }
            button.disabled = true;
            const originalText = button.textContent;
            button.textContent = 'Working...';

            try {
                const response = await fetch('/control_service', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action })
                });

                const data = await response.json();

                if (data.success) {
                    showStatus('service-control-status', data.message + ' Checking status...', true);
                    // Poll status multiple times to show when operation completes
                    setTimeout(updateServiceStatus, 2000);
                    setTimeout(updateServiceStatus, 5000);
                    setTimeout(updateServiceStatus, 8000);
                } else {
                    showStatus('service-control-status', 'Error: ' + data.message, false);
                }
            } catch (error) {
                showStatus('service-control-status', 'Error: ' + error.message, false);
            } finally {
                button.disabled = false;
                button.textContent = originalText;
            }
        }

        function showRebootPrompt(keys) {
            const names = (keys || []).map(k => REBOOT_KEY_NAMES[k] || 'Display hardware settings');
            document.getElementById('reboot-prompt-keys').textContent =
                names.length ? [...new Set(names)].join(', ') : 'this setting';
            document.getElementById('reboot-prompt-status').style.display = 'none';
            document.getElementById('reboot-prompt').classList.add('visible');
        }

        function dismissRebootPrompt() {
            document.getElementById('reboot-prompt').classList.remove('visible');
        }

        async function rebootFromPrompt(button) {
            button.disabled = true;
            button.textContent = 'Restarting...';
            try {
                const response = await fetch('/reboot', { method: 'POST' });
                const data = await response.json();
                if (data.success) {
                    showStatus('reboot-prompt-status',
                        'Restarting... wait about 2 minutes, then reload this page.', true);
                } else {
                    showStatus('reboot-prompt-status',
                        'Restart error: ' + data.message, false);
                    button.disabled = false;
                    button.textContent = 'Restart now';
                }
            } catch (error) {
                showStatus('reboot-prompt-status',
                    'Restart error: ' + error.message, false);
                button.disabled = false;
                button.textContent = 'Restart now';
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
                        ' - restart now, or from the Device tab later.', false);
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
            if (!confirm('Restart the whole scoreboard? The screen will be blank for about 2 minutes.')) {
                return;
            }

            button.disabled = true;
            button.textContent = 'Restarting...';

            try {
                const response = await fetch('/reboot', {
                    method: 'POST'
                });

                const data = await response.json();

                if (data.success) {
                    showStatus('service-control-status', 'Restarting... wait about 2 minutes, then reload this page.', true);
                } else {
                    showStatus('service-control-status', 'Restart error: ' + data.message, false);
                    button.disabled = false;
                    button.textContent = 'Restart everything';
                }
            } catch (error) {
                showStatus('service-control-status', 'Restart error: ' + error.message, false);
                button.disabled = false;
                button.textContent = 'Restart everything';
            }
        }

        async function loadLogs(logType) {
            currentLogType = logType;
            const logContent = document.getElementById('log-content');
            const logFilename = document.getElementById('log-filename');

            logContent.textContent = 'Loading...';
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
        ncaab_teams=NCAAB_TEAMS,
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


@app.route('/ncaab_logo/<slug>')
def ncaab_logo(slug):
    pack = NCAAB_TEAMS.get(slug)
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

    # --wait makes nmcli give up before the subprocess timeout does, so a
    # wrong password always reaches the hotspot restore below
    up = subprocess.run(['sudo', 'nmcli', '--wait', '45', 'connection', 'up', con_name],
                        capture_output=True, text=True, timeout=60)
    hostname = get_hostname()
    if up.returncode == 0:
        return jsonify({
            'success': True,
            'message': f'Connected to {ssid}! Admin page: http://{hostname}.local/admin'
        })
    # Bring the hotspot back, or a mistyped password leaves the unit with no
    # network and no way to retry short of a power cycle. Harmless if the
    # hotspot was never up (profile missing: nmcli just fails).
    subprocess.run(['sudo', 'nmcli', 'connection', 'up', 'marquee-hotspot'],
                   check=False, capture_output=True, timeout=60)
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

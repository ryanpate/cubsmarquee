#!/usr/bin/env python3
"""WiFi configuration web server - accessible at hostname.local/admin"""

from flask import Flask, render_template_string, request, jsonify, redirect
import subprocess
import os
import socket
import glob
import json
import time
import re

app = Flask(__name__)

CONFIG_PATH = '/home/pi/config.json'


def get_connection_mode():
    """Determine if we're in AP mode or connected to WiFi"""
    try:
        result = subprocess.run(
            ['iwgetid', '-r'], capture_output=True, text=True)
        if result.stdout.strip():
            return 'Connected to WiFi'
        return 'Access Point Mode'
    except:
        return 'Unknown'


def get_hostname():
    """Get the Pi's hostname"""
    return socket.gethostname()


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

        subprocess.run(['sudo', 'cp', '/tmp/hostname', '/etc/hostname'], check=True)

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

        subprocess.run(['sudo', 'cp', '/tmp/hosts', '/etc/hosts'], check=True)

        # Set hostname immediately (without reboot)
        subprocess.run(['sudo', 'hostnamectl', 'set-hostname', new_hostname], check=True)

        # Restart Avahi daemon to advertise new hostname via mDNS
        subprocess.run(['sudo', 'systemctl', 'restart', 'avahi-daemon'], check=False)

        return True, f"Hostname changed to '{new_hostname}'. Access at http://{new_hostname}.local/admin"

    except Exception as e:
        return False, f"Error setting hostname: {str(e)}"


def get_current_network():
    """Get currently connected network SSID"""
    try:
        result = subprocess.run(
            ['iwgetid', '-r'], capture_output=True, text=True)
        return result.stdout.strip() or 'Not connected'
    except:
        return 'Unknown'


def get_ip_address():
    """Get current IP address"""
    try:
        result = subprocess.run(
            ['hostname', '-I'], capture_output=True, text=True)
        return result.stdout.strip().split()[0] if result.stdout.strip() else 'No IP'
    except:
        return 'Unknown'


def load_config():
    """Load configuration from JSON file"""
    default_config = {
        'zip_code': '',
        'weather_api_key': '',
        'custom_message': 'GO CUBS GO! SEE YOU NEXT SEASON!',
        'display_mode': 'auto',
        'enable_weather': True,
        'enable_bears': True,
        'enable_bears_news': True,
        'enable_pga': True,
        'enable_pga_news': True,
        'enable_pga_facts': True,
        'enable_cubs_news': True,
        'enable_cubs_facts': True,
        'enable_bible': True,
        'enable_newsmax': True,
        'enable_stocks': True,
        'enable_spring_training': True
    }

    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                loaded = json.load(f)
                default_config.update(loaded)
    except Exception as e:
        print(f"Error loading config: {e}")

    return default_config


def save_config(config):
    """Save configuration to JSON file"""
    try:
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False


HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Cubs Scoreboard Admin</title>
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
    </style>
</head>
<body>
    <div class="container">
        <h1>🐻 Cubs Scoreboard Admin</h1>
        <div class="subtitle">Configuration & Management Panel</div>

        <div class="info-box">
            <div class="info-row"><strong>Hostname:</strong> {{ hostname }}</div>
            <div class="info-row"><strong>Access URL:</strong> http://{{ hostname }}.local/admin</div>
            <div class="info-row"><strong>IP Address:</strong> {{ ip_address }}</div>
            <div class="info-row"><strong>Connection:</strong> {{ connection_mode }}</div>
            <div class="info-row"><strong>Current Network:</strong> {{ current_network }}</div>
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
            
            <div class="form-group">
                <label for="display_mode">Display Mode:</label>
                <select id="display_mode">
                    <option value="auto">Automatic (Games during season, off-season content otherwise)</option>
                    <option value="game">Always show game (if available)</option>
                    <option value="offseason">Always show off-season content</option>
                </select>
            </div>

            <h3 style="margin-top: 20px; color: #0C2340;">Content Display Options</h3>
            <p class="help-text" style="margin-bottom: 15px;">Select which content to show in the off-season rotation:</p>

            <div class="form-group">
                <label>
                    <input type="checkbox" id="enable_weather">
                    Enable Weather display
                </label>
            </div>

            <div class="form-group">
                <label>
                    <input type="checkbox" id="enable_bears">
                    Enable Chicago Bears display (football season)
                </label>
            </div>

            <div class="form-group">
                <label>
                    <input type="checkbox" id="enable_bears_news">
                    Enable Bears breaking news display
                </label>
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

            <div class="form-group">
                <label>
                    <input type="checkbox" id="enable_cubs_facts">
                    Enable Cubs facts & custom message display
                </label>
            </div>

            <div class="form-group">
                <label>
                    <input type="checkbox" id="enable_cubs_news">
                    Enable Cubs breaking news display
                </label>
            </div>

            <div class="form-group">
                <label>
                    <input type="checkbox" id="enable_bible">
                    Enable Bible Verse of the Day display
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
                    <input type="checkbox" id="enable_stocks">
                    Enable Stock Exchange ticker display
                </label>
            </div>

            <div class="form-group">
                <label>
                    <input type="checkbox" id="enable_spring_training">
                    Enable Spring Training countdown display
                </label>
            </div>

            <div class="form-group">
                <label for="zip_code">ZIP Code (for weather):</label>
                <input type="text" id="zip_code" placeholder="e.g., 60613" value="{{ config.zip_code }}">
            </div>

            <div class="form-group">
                <label for="weather_api_key">OpenWeather API Key:</label>
                <input type="text" id="weather_api_key" placeholder="Get free API key from openweathermap.org" value="{{ config.weather_api_key }}">
                <div class="help-text">Free tier API key from <a href="https://openweathermap.org/api" target="_blank">openweathermap.org</a></div>
            </div>

            <div class="form-group">
                <label for="custom_message">Custom Message:</label>
                <textarea id="custom_message">{{ config.custom_message }}</textarea>
                <div class="help-text">This message displays during the off-season rotation</div>
            </div>

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

        // Auto-load config values on page load
        window.onload = function() {
            const config = {{ config | tojson }};
            document.getElementById('display_mode').value = config.display_mode || 'auto';
            document.getElementById('enable_weather').checked = config.enable_weather !== false;
            document.getElementById('enable_bears').checked = config.enable_bears !== false;
            document.getElementById('enable_bears_news').checked = config.enable_bears_news !== false;
            document.getElementById('enable_pga').checked = config.enable_pga !== false;
            document.getElementById('enable_pga_news').checked = config.enable_pga_news !== false;
            document.getElementById('enable_pga_facts').checked = config.enable_pga_facts !== false;
            document.getElementById('enable_cubs_facts').checked = config.enable_cubs_facts !== false;
            document.getElementById('enable_cubs_news').checked = config.enable_cubs_news !== false;
            document.getElementById('enable_bible').checked = config.enable_bible !== false;
            document.getElementById('enable_newsmax').checked = config.enable_newsmax !== false;
            document.getElementById('enable_stocks').checked = config.enable_stocks !== false;
            document.getElementById('enable_spring_training').checked = config.enable_spring_training !== false;
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
                    networkList.innerHTML = data.networks.map(network =>
                        `<div class="network-item" onclick="selectNetwork('${network.ssid}')">
                            ${network.ssid}
                            <span class="signal">${network.signal}</span>
                        </div>`
                    ).join('');
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

        async function saveConfig() {
            const config = {
                zip_code: document.getElementById('zip_code').value,
                weather_api_key: document.getElementById('weather_api_key').value,
                custom_message: document.getElementById('custom_message').value,
                display_mode: document.getElementById('display_mode').value,
                enable_weather: document.getElementById('enable_weather').checked,
                enable_bears: document.getElementById('enable_bears').checked,
                enable_bears_news: document.getElementById('enable_bears_news').checked,
                enable_pga: document.getElementById('enable_pga').checked,
                enable_pga_news: document.getElementById('enable_pga_news').checked,
                enable_pga_facts: document.getElementById('enable_pga_facts').checked,
                enable_cubs_facts: document.getElementById('enable_cubs_facts').checked,
                enable_cubs_news: document.getElementById('enable_cubs_news').checked,
                enable_bible: document.getElementById('enable_bible').checked,
                enable_newsmax: document.getElementById('enable_newsmax').checked,
                enable_stocks: document.getElementById('enable_stocks').checked,
                enable_spring_training: document.getElementById('enable_spring_training').checked
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
                    showStatus('config-status', 'Configuration saved successfully! Restart the service for changes to take effect.', true);
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
        config=config
    )


@app.route('/scan_networks')
def scan_networks():
    """Scan for available WiFi networks"""
    try:
        result = subprocess.run(
            ['sudo', 'iwlist', 'wlan0', 'scan'],
            capture_output=True,
            text=True,
            timeout=15
        )

        networks = []
        current_network = None

        for line in result.stdout.split('\n'):
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

        return jsonify({'success': True, 'networks': unique_networks})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/connect_wifi', methods=['POST'])
def connect_wifi():
    """Connect to a WiFi network"""
    try:
        data = request.json
        ssid = data.get('ssid')
        password = data.get('password')

        if not ssid or not password:
            return jsonify({'success': False, 'message': 'SSID and password required'})

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
        wpa_config += f"""network={{
    ssid="{ssid}"
    psk="{password}"
    key_mgmt=WPA-PSK
    priority=10
}}
"""

        # Write to temp file first
        with open('/tmp/wpa_supplicant.conf', 'w') as f:
            f.write(wpa_config)

        # Copy to proper location with correct permissions
        subprocess.run(
            ['sudo', 'cp', '/tmp/wpa_supplicant.conf',
             '/etc/wpa_supplicant/wpa_supplicant.conf'],
            check=True
        )
        
        subprocess.run(
            ['sudo', 'chmod', '600', '/etc/wpa_supplicant/wpa_supplicant.conf'],
            check=True
        )
        
        # Ensure wpa_supplicant service is enabled for persistence
        subprocess.run(
            ['sudo', 'systemctl', 'enable', 'wpa_supplicant'],
            check=False
        )

        # Stop AP mode if running
        subprocess.run(['sudo', 'systemctl', 'stop', 'hostapd'], check=False)
        subprocess.run(['sudo', 'systemctl', 'stop', 'dnsmasq'], check=False)

        # Remove AP IP if set
        subprocess.run(['sudo', 'ip', 'addr', 'flush', 'dev', 'wlan0'], check=False)

        # Restart networking services in proper order
        subprocess.run(['sudo', 'systemctl', 'restart', 'dhcpcd'], check=False)
        time.sleep(2)
        subprocess.run(['sudo', 'wpa_cli', '-i', 'wlan0', 'reconfigure'], check=False)
        time.sleep(3)
        
        # Restart Avahi to advertise hostname on new network
        subprocess.run(['sudo', 'systemctl', 'restart', 'avahi-daemon'], check=False)
        time.sleep(2)
        
        # Check if we got an IP (not the AP IP)
        result = subprocess.run(
            ['ip', 'addr', 'show', 'wlan0'],
            capture_output=True,
            text=True
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


@app.route('/save_config', methods=['POST'])
def save_config_route():
    """Save display configuration"""
    try:
        data = request.json
        current_config = load_config()

        # Update with new values
        current_config.update({
            'zip_code': data.get('zip_code', ''),
            'weather_api_key': data.get('weather_api_key', ''),
            'custom_message': data.get('custom_message', 'GO CUBS GO!'),
            'display_mode': data.get('display_mode', 'auto'),
            'enable_weather': data.get('enable_weather', True),
            'enable_bears': data.get('enable_bears', True),
            'enable_bears_news': data.get('enable_bears_news', True),
            'enable_pga': data.get('enable_pga', True),
            'enable_pga_news': data.get('enable_pga_news', True),
            'enable_pga_facts': data.get('enable_pga_facts', True),
            'enable_cubs_facts': data.get('enable_cubs_facts', True),
            'enable_cubs_news': data.get('enable_cubs_news', True),
            'enable_bible': data.get('enable_bible', True),
            'enable_newsmax': data.get('enable_newsmax', True),
            'enable_stocks': data.get('enable_stocks', True),
            'enable_spring_training': data.get('enable_spring_training', True)
        })

        if save_config(current_config):
            return jsonify({'success': True})
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
    app.run(host='0.0.0.0', port=80, debug=False)

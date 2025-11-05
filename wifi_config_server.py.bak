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
        'enable_bears': True
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
        .footer {
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            text-align: center;
            color: #666;
            font-size: 12px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🐻 Cubs Scoreboard Admin</h1>
        <div class="subtitle">Configuration & Management</div>

        <div class="info-box">
            <div class="info-row"><strong>Status:</strong> <span id="connection-mode">Loading...</span></div>
            <div class="info-row"><strong>Hostname:</strong> {{ hostname }}</div>
            <div class="info-row"><strong>Current Network:</strong> <span id="current-network">Loading...</span></div>
            <div class="info-row"><strong>IP Address:</strong> <span id="ip-address">Loading...</span></div>
            <div class="info-row"><strong>Access URL:</strong> http://{{ hostname }}.local/admin</div>
        </div>

        <div class="nav-tabs">
            <button class="nav-tab active" onclick="switchTab('wifi')">WiFi Setup</button>
            <button class="nav-tab" onclick="switchTab('display')">Display Config</button>
            <button class="nav-tab" onclick="switchTab('system')">System</button>
            <button class="nav-tab" onclick="switchTab('logs')">Logs</button>
        </div>

        <!-- WiFi Tab -->
        <div id="wifi-tab" class="tab-content active">
            <h2>WiFi Configuration</h2>
            
            <div class="warning">
                <strong>⚠️ Important:</strong> After connecting to WiFi, the device will leave Access Point mode. 
                Make sure to note the hostname above to access this page on your network.
            </div>

            <div class="form-group">
                <label>Available Networks</label>
                <button onclick="scanNetworks()" class="button-secondary">Scan for Networks</button>
                <div id="network-list" class="network-list" style="display:none; margin-top: 10px;">
                    <div style="padding: 20px; text-align: center; color: #666;">
                        Click "Scan for Networks" to see available WiFi networks
                    </div>
                </div>
            </div>

            <div class="form-group">
                <label for="wifi-ssid">Network Name (SSID)</label>
                <input type="text" id="wifi-ssid" placeholder="Enter WiFi network name">
            </div>

            <div class="form-group">
                <label for="wifi-password">Password</label>
                <input type="password" id="wifi-password" placeholder="Enter WiFi password">
                <div class="help-text">Your WiFi credentials are stored securely on the device</div>
            </div>

            <button onclick="connectWiFi()">Connect to WiFi</button>
            <div id="wifi-status" class="status"></div>
        </div>

        <!-- Display Config Tab -->
        <div id="display-tab" class="tab-content">
            <h2>Display Configuration</h2>

            <div class="form-group">
                <label for="zip-code">ZIP Code</label>
                <input type="text" id="zip-code" placeholder="60613" value="{{ config.zip_code }}">
                <div class="help-text">Used for weather information and local game times</div>
            </div>

            <div class="form-group">
                <label for="weather-api-key">Weather API Key (OpenWeatherMap)</label>
                <input type="text" id="weather-api-key" placeholder="Enter your API key" value="{{ config.weather_api_key }}">
                <div class="help-text">Get a free API key at <a href="https://openweathermap.org/api" target="_blank">openweathermap.org/api</a></div>
            </div>

            <div class="form-group">
                <label for="custom-message">Custom Message</label>
                <textarea id="custom-message" rows="3">{{ config.custom_message }}</textarea>
                <div class="help-text">Displayed during off-season or when no games are scheduled</div>
            </div>

            <div class="form-group">
                <label for="display-mode">Display Mode</label>
                <select id="display-mode">
                    <option value="auto" {% if config.display_mode == 'auto' %}selected{% endif %}>Auto (Game schedule based)</option>
                    <option value="always_on" {% if config.display_mode == 'always_on' %}selected{% endif %}>Always On</option>
                    <option value="schedule" {% if config.display_mode == 'schedule' %}selected{% endif %}>Schedule Only</option>
                </select>
            </div>

            <div class="form-group">
                <label>
                    <input type="checkbox" id="enable-bears" {% if config.enable_bears %}checked{% endif %}>
                    Enable Chicago Bears Scores
                </label>
                <div class="help-text">Show Bears game information during NFL season</div>
            </div>

            <button onclick="saveConfig()">Save Configuration</button>
            <div id="config-status" class="status"></div>
        </div>

        <!-- System Tab -->
        <div id="system-tab" class="tab-content">
            <h2>System Control</h2>

            <div class="info-box">
                <div class="info-row">
                    <strong>Scoreboard Service:</strong> <span id="service-status">Loading...</span>
                </div>
            </div>

            <button onclick="controlService('stop')" class="button-secondary">Stop Scoreboard</button>
            <button onclick="controlService('start')" class="button-secondary">Start Scoreboard</button>
            <button onclick="controlService('restart')" class="button-secondary">Restart Scoreboard</button>
            
            <h2 style="margin-top: 30px;">System Actions</h2>
            <div class="warning">
                <strong>⚠️ Warning:</strong> Rebooting will temporarily disconnect the device
            </div>
            <button onclick="rebootDevice()" class="button-secondary">Reboot Device</button>
            
            <div id="system-status" class="status"></div>
        </div>

        <!-- Logs Tab -->
        <div id="logs-tab" class="tab-content">
            <h2>System Logs</h2>

            <div class="form-group">
                <button onclick="viewLogs('application')" class="button-secondary">View Application Logs</button>
                <button onclick="viewLogs('error')" class="button-secondary">View Error Logs</button>
                <button onclick="viewLogs('wifi')" class="button-secondary">View WiFi Manager Logs</button>
            </div>

            <div id="log-viewer" style="display:none; margin-top: 20px;">
                <h3 id="log-title"></h3>
                <textarea readonly style="width: 100%; height: 400px; font-family: monospace; font-size: 12px; background: #f5f5f5;" id="log-content"></textarea>
            </div>
        </div>

        <div class="footer">
            Cubs Scoreboard v1.0 | <a href="https://github.com/yourusername/cubs-scoreboard" target="_blank">Documentation</a>
        </div>
    </div>

    <script>
        // Update status information on load
        function updateStatus() {
            fetch('/service_status')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('service-status').textContent = 
                        data.running ? '✓ Running' : '✗ Stopped';
                });

            document.getElementById('connection-mode').textContent = '{{ mode }}';
            document.getElementById('current-network').textContent = '{{ current_network }}';
            document.getElementById('ip-address').textContent = '{{ ip }}';
        }

        updateStatus();
        setInterval(updateStatus, 5000);

        function switchTab(tabName) {
            document.querySelectorAll('.tab-content').forEach(tab => {
                tab.classList.remove('active');
            });
            document.querySelectorAll('.nav-tab').forEach(btn => {
                btn.classList.remove('active');
            });

            document.getElementById(tabName + '-tab').classList.add('active');
            event.target.classList.add('active');
        }

        function scanNetworks() {
            const listEl = document.getElementById('network-list');
            listEl.style.display = 'block';
            listEl.innerHTML = '<div style="padding: 20px; text-align: center;">Scanning...</div>';

            fetch('/scan')
                .then(r => r.json())
                .then(data => {
                    if (data.networks && data.networks.length > 0) {
                        listEl.innerHTML = data.networks.map(net => 
                            `<div class="network-item" onclick="selectNetwork('${net.ssid}')">
                                ${net.ssid}
                                <span class="signal">${net.signal}%</span>
                            </div>`
                        ).join('');
                    } else {
                        listEl.innerHTML = '<div style="padding: 20px; text-align: center; color: #666;">No networks found</div>';
                    }
                });
        }

        function selectNetwork(ssid) {
            document.getElementById('wifi-ssid').value = ssid;
            document.getElementById('wifi-password').focus();
        }

        function connectWiFi() {
            const ssid = document.getElementById('wifi-ssid').value;
            const password = document.getElementById('wifi-password').value;
            const statusEl = document.getElementById('wifi-status');

            if (!ssid || !password) {
                showStatus(statusEl, 'Please enter both SSID and password', 'error');
                return;
            }

            showStatus(statusEl, 'Configuring WiFi...', 'success');

            fetch('/connect', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ssid, password})
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    showStatus(statusEl, data.message + ' The device will exit AP mode if connection is successful. You may need to reconnect to your regular WiFi network to access the scoreboard again.', 'success');
                } else {
                    showStatus(statusEl, 'Error: ' + data.message, 'error');
                }
            })
            .catch(err => {
                showStatus(statusEl, 'Connection error: ' + err, 'error');
            });
        }

        function saveConfig() {
            const statusEl = document.getElementById('config-status');
            showStatus(statusEl, 'Saving configuration...', 'success');

            const config = {
                zip_code: document.getElementById('zip-code').value,
                weather_api_key: document.getElementById('weather-api-key').value,
                custom_message: document.getElementById('custom-message').value,
                display_mode: document.getElementById('display-mode').value,
                enable_bears: document.getElementById('enable-bears').checked
            };

            fetch('/save_config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(config)
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    showStatus(statusEl, 'Configuration saved successfully!', 'success');
                } else {
                    showStatus(statusEl, 'Error: ' + data.message, 'error');
                }
            });
        }

        function controlService(action) {
            const statusEl = document.getElementById('system-status');
            showStatus(statusEl, `${action}ing service...`, 'success');

            fetch('/control_service', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({action})
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    showStatus(statusEl, data.message, 'success');
                    setTimeout(updateStatus, 2000);
                } else {
                    showStatus(statusEl, 'Error: ' + data.message, 'error');
                }
            });
        }

        function rebootDevice() {
            if (!confirm('Are you sure you want to reboot the device?')) return;

            const statusEl = document.getElementById('system-status');
            showStatus(statusEl, 'Rebooting device... Please wait about 30 seconds.', 'success');

            fetch('/reboot', {method: 'POST'})
                .then(r => r.json())
                .then(data => {
                    showStatus(statusEl, 'Device is rebooting. This page will become unavailable.', 'success');
                });
        }

        function viewLogs(logType) {
            const viewer = document.getElementById('log-viewer');
            const title = document.getElementById('log-title');
            const content = document.getElementById('log-content');

            viewer.style.display = 'block';
            title.textContent = 'Loading logs...';
            content.value = '';

            fetch(`/logs/${logType}`)
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        title.textContent = data.filename;
                        content.value = data.content;
                    } else {
                        title.textContent = 'Error';
                        content.value = data.message;
                    }
                });
        }

        function showStatus(element, message, type) {
            element.textContent = message;
            element.className = 'status ' + type;
            element.style.display = 'block';
            
            setTimeout(() => {
                element.style.display = 'none';
            }, 5000);
        }
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    """Redirect root to admin page"""
    return redirect('/admin')


@app.route('/admin')
def admin():
    """Main admin interface"""
    config = load_config()
    return render_template_string(
        HTML_TEMPLATE,
        hostname=get_hostname(),
        mode=get_connection_mode(),
        current_network=get_current_network(),
        ip=get_ip_address(),
        config=config
    )


@app.route('/scan')
def scan_networks():
    """Scan for available WiFi networks"""
    try:
        result = subprocess.run(
            ['sudo', 'iwlist', 'wlan0', 'scan'],
            capture_output=True,
            text=True,
            timeout=10
        )

        networks = []
        current_network = {}

        for line in result.stdout.split('\n'):
            line = line.strip()

            if 'ESSID:' in line:
                ssid = line.split('ESSID:"')[1].rstrip('"')
                if ssid:
                    current_network['ssid'] = ssid

            elif 'Quality=' in line:
                quality = line.split('Quality=')[1].split(' ')[0]
                numerator, denominator = quality.split('/')
                signal_percent = int((int(numerator) / int(denominator)) * 100)
                current_network['signal'] = signal_percent

                if 'ssid' in current_network:
                    networks.append(current_network.copy())
                    current_network = {}

        unique_networks = {n['ssid']: n for n in networks}
        sorted_networks = sorted(unique_networks.values(),
                                 key=lambda x: x['signal'],
                                 reverse=True)

        return jsonify({'networks': sorted_networks})

    except Exception as e:
        return jsonify({'networks': [], 'error': str(e)})


@app.route('/connect', methods=['POST'])
def connect_wifi():
    """Configure WiFi and attempt connection"""
    try:
        data = request.json
        ssid = data.get('ssid')
        password = data.get('password')

        if not ssid or not password:
            return jsonify({'success': False, 'message': 'SSID and password required'})

        # Read existing wpa_supplicant.conf to preserve header and other networks
        existing_header = """ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=US

"""
        existing_networks = []
        
        try:
            with open('/etc/wpa_supplicant/wpa_supplicant.conf', 'r') as f:
                content = f.read()
                
                # Extract header (everything before first network block)
                if 'network=' in content:
                    header_part = content.split('network=')[0]
                    if 'ctrl_interface' in header_part:
                        existing_header = header_part
                
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

        # Stop AP mode if running
        subprocess.run(['sudo', 'systemctl', 'stop', 'hostapd'], check=False)
        subprocess.run(['sudo', 'systemctl', 'stop', 'dnsmasq'], check=False)

        # Restart networking services
        subprocess.run(['sudo', 'systemctl', 'restart', 'dhcpcd'], check=False)
        subprocess.run(['sudo', 'wpa_cli', '-i', 'wlan0', 'reconfigure'], check=False)
        
        # Give it a moment to start connecting
        time.sleep(3)
        
        # Check if we got an IP (not the AP IP)
        result = subprocess.run(
            ['ip', 'addr', 'show', 'wlan0'],
            capture_output=True,
            text=True
        )
        
        if 'inet ' in result.stdout and '10.0.0.1' not in result.stdout:
            # We have a new IP, connection looks good
            return jsonify({
                'success': True,
                'message': f'WiFi configured and connected to {ssid}. AP mode will stop automatically.'
            })
        else:
            return jsonify({
                'success': True,
                'message': f'WiFi configured. Attempting to connect to {ssid}...'
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
            'enable_bears': data.get('enable_bears', True)
        })

        if save_config(current_config):
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'message': 'Failed to save configuration'})

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
            subprocess.run(['sudo', 'systemctl', 'stop',
                           'cubs-scoreboard'], timeout=25)
            subprocess.run(
                ['sudo', 'pkill', '-f', 'python.*main.py'], timeout=25)
            return jsonify({'success': True, 'message': 'Service stopped'})

        elif action == 'restart':
            subprocess.run(['sudo', 'systemctl', 'stop',
                           'cubs-scoreboard'], timeout=25)
            subprocess.run(
                ['sudo', 'pkill', '-f', 'python.*main.py'], timeout=25)
            time.sleep(2)
            result = subprocess.run(
                ['sudo', 'systemctl', 'start', 'cubs-scoreboard'],
                capture_output=True,
                text=True,
                timeout=20
            )
            if result.returncode == 0:
                return jsonify({'success': True, 'message': 'Service restarted'})
            else:
                return jsonify({'success': False, 'message': f'Service restart failed: {result.stderr}'})

        else:  # action == 'start'
            result = subprocess.run(
                ['sudo', 'systemctl', 'start', 'cubs-scoreboard'],
                capture_output=True,
                text=True,
                timeout=20
            )
            if result.returncode == 0:
                return jsonify({'success': True, 'message': 'Service started'})
            else:
                return jsonify({'success': False, 'message': f'Service start failed: {result.stderr}'})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/reboot', methods=['POST'])
def reboot_device():
    """Reboot the Raspberry Pi"""
    try:
        subprocess.Popen(['sudo', 'reboot'])
        return jsonify({'success': True, 'message': 'Reboot initiated'})
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

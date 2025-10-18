#!/usr/bin/env python3
"""WiFi configuration web server - accessible at hostname.local/admin"""

from flask import Flask, render_template_string, request, jsonify, redirect
import subprocess
import os
import socket
import glob
import json

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
        'enable_bears': True  # ADDED: Bears display toggle
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
            background: #f0f0f0;
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
        <h1>Cubs Scoreboard Admin</h1>
        <div class="subtitle">Device: {{ hostname }}.local</div>
        
        <div class="info-box">
            <div class="info-row"><strong>Current Network:</strong> {{ current_network }}</div>
            <div class="info-row"><strong>IP Address:</strong> {{ ip_address }}</div>
            <div class="info-row"><strong>Connection Mode:</strong> {{ mode }}</div>
        </div>
        
        <div class="nav-tabs">
            <button class="nav-tab active" onclick="showTab('wifi')">WiFi</button>
            <button class="nav-tab" onclick="showTab('display')">Display Settings</button>
            <button class="nav-tab" onclick="showTab('system')">System</button>
        </div>
        
        <!-- WiFi Tab -->
        <div id="wifi-tab" class="tab-content active">
            {% if 'Access Point' in mode %}
            <div class="warning">
                <strong>Access Point Mode Active</strong><br>
                The scoreboard couldn't connect to a WiFi network and is running in hotspot mode.
                Configure your WiFi credentials below to connect.
            </div>
            {% endif %}
            
            <h2>WiFi Configuration</h2>
            
            <div class="form-group">
                <label>Available Networks:</label>
                <div class="network-list" id="networkList">
                    <div style="padding: 10px; text-align: center;">Click "Refresh Networks" to scan</div>
                </div>
                <button onclick="scanNetworks()" id="scanBtn">Refresh Networks</button>
            </div>
            
            <form id="wifiForm">
                <div class="form-group">
                    <label for="ssid">Network Name (SSID):</label>
                    <input type="text" id="ssid" name="ssid" required placeholder="Enter network name">
                </div>
                
                <div class="form-group">
                    <label for="password">Password:</label>
                    <input type="password" id="password" name="password" required placeholder="Enter network password">
                </div>
                
                <button type="submit" id="connectBtn">Connect to Network</button>
            </form>
            
            <div id="wifiStatus" class="status"></div>
        </div>
        
        <!-- Display Settings Tab -->
        <div id="display-tab" class="tab-content">
            <h2>Off-Season Display Settings</h2>
            
            <form id="displayForm">
                <div class="form-group">
                    <label for="zip_code">Zip Code (for weather):</label>
                    <input type="text" id="zip_code" name="zip_code" 
                           value="{{ config.zip_code }}" 
                           placeholder="60613" 
                           maxlength="5" 
                           pattern="[0-9]{5}">
                    <div class="help-text">Enter your 5-digit US zip code for local weather</div>
                </div>
                
                <div class="form-group">
                    <label for="weather_api_key">OpenWeatherMap API Key:</label>
                    <input type="text" id="weather_api_key" name="weather_api_key" 
                           value="{{ config.weather_api_key }}" 
                           placeholder="Enter your API key">
                    <div class="help-text">
                        Get a free API key at <a href="https://openweathermap.org/api" target="_blank">openweathermap.org/api</a>
                    </div>
                </div>
                
                <div class="form-group">
                    <label for="custom_message">Custom Message:</label>
                    <textarea id="custom_message" name="custom_message" 
                              placeholder="GO CUBS GO! SEE YOU NEXT SEASON!">{{ config.custom_message }}</textarea>
                    <div class="help-text">This message will scroll on the display during off-season</div>
                </div>
                
                <div class="form-group">
                    <label for="display_mode">Display Mode:</label>
                    <select id="display_mode" name="display_mode">
                        <option value="auto" {% if config.display_mode == 'auto' %}selected{% endif %}>
                            Auto (Rotate between weather, Bears, Cubs trivia, and message)
                        </option>
                        <option value="weather_only" {% if config.display_mode == 'weather_only' %}selected{% endif %}>
                            Weather Only
                        </option>
                        <option value="message_only" {% if config.display_mode == 'message_only' %}selected{% endif %}>
                            Message Only
                        </option>
                    </select>
                    <div class="help-text">Choose how content is displayed during off-season</div>
                </div>
                
                <div class="form-group">
                    <label>
                        <input type="checkbox" 
                               id="enable_bears" 
                               name="enable_bears"
                               {% if config.enable_bears %}checked{% endif %}>
                        Enable Chicago Bears Display (Football Season)
                    </label>
                    <div class="help-text">
                        Show Bears game info during football season (September - February).
                        Uses free ESPN API - no additional setup required.
                    </div>
                </div>
                
                <button type="submit" id="saveDisplayBtn">Save Display Settings</button>
            </form>
            
            <div id="displayStatus" class="status"></div>
        </div>
        
        <!-- System Tab -->
        <div id="system-tab" class="tab-content">
            <h2>System Control</h2>
            
            <button onclick="rebootDevice()" id="rebootBtn" class="button-secondary">Reboot Scoreboard</button>
            
            <h2>System Logs</h2>
            
            <button onclick="viewLogs('application')" class="button-secondary">View Application Logs</button>
            <button onclick="viewLogs('error')" class="button-secondary" style="margin-top: 10px;">View Error Logs</button>
            <button onclick="viewLogs('wifi')" class="button-secondary" style="margin-top: 10px;">View WiFi Manager Logs</button>
            
            <div id="logViewer" style="display: none; margin-top: 20px;">
                <h3 id="logTitle" style="color: #0C2340;"></h3>
                <div style="background: #f8f9fa; border: 2px solid #0C2340; border-radius: 5px; padding: 10px; max-height: 400px; overflow-y: auto;">
                    <pre id="logContent" style="margin: 0; font-size: 11px; white-space: pre-wrap; word-wrap: break-word;"></pre>
                </div>
                <button onclick="closeLogViewer()" class="button-secondary" style="margin-top: 10px;">Close Logs</button>
            </div>
            
            <div id="systemStatus" class="status"></div>
        </div>
        
        <div class="footer">
            Access this page anytime at: <strong>{{ hostname }}.local/admin</strong>
        </div>
    </div>

    <script>
        function showTab(tabName) {
            // Hide all tabs
            document.querySelectorAll('.tab-content').forEach(tab => {
                tab.classList.remove('active');
            });
            document.querySelectorAll('.nav-tab').forEach(tab => {
                tab.classList.remove('active');
            });
            
            // Show selected tab
            document.getElementById(tabName + '-tab').classList.add('active');
            event.target.classList.add('active');
        }
        
        function scanNetworks() {
            const btn = document.getElementById('scanBtn');
            const list = document.getElementById('networkList');
            
            btn.disabled = true;
            btn.textContent = 'Scanning...';
            list.innerHTML = '<div style="padding: 10px; text-align: center;">Scanning for networks...</div>';
            
            fetch('/scan')
                .then(response => response.json())
                .then(data => {
                    if (data.networks.length === 0) {
                        list.innerHTML = '<div style="padding: 10px; text-align: center;">No networks found</div>';
                    } else {
                        list.innerHTML = data.networks.map(network => 
                            `<div class="network-item" onclick="selectNetwork('${escapeHtml(network.ssid)}')">
                                ${escapeHtml(network.ssid)}
                                <span class="signal">${network.signal}%</span>
                            </div>`
                        ).join('');
                    }
                })
                .catch(error => {
                    console.error('Error scanning networks:', error);
                    list.innerHTML = '<div style="padding: 10px; text-align: center; color: #721c24;">Error scanning networks</div>';
                })
                .finally(() => {
                    btn.disabled = false;
                    btn.textContent = 'Refresh Networks';
                });
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        function selectNetwork(ssid) {
            document.getElementById('ssid').value = ssid;
            document.getElementById('password').focus();
        }
        
        function rebootDevice() {
            if (!confirm('Are you sure you want to reboot the scoreboard? This will interrupt any running display.')) {
                return;
            }
            
            const btn = document.getElementById('rebootBtn');
            const status = document.getElementById('systemStatus');
            
            btn.disabled = true;
            btn.textContent = 'Rebooting...';
            
            status.style.display = 'block';
            status.className = 'status';
            status.textContent = 'Rebooting device... This will take about 30 seconds.';
            
            fetch('/reboot', {
                method: 'POST'
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    status.className = 'status success';
                    status.textContent = 'Reboot initiated. The scoreboard will be back online in about 30 seconds.';
                } else {
                    status.className = 'status error';
                    status.textContent = 'Error: ' + data.message;
                    btn.disabled = false;
                    btn.textContent = 'Reboot Scoreboard';
                }
            })
            .catch(error => {
                status.className = 'status success';
                status.textContent = 'Reboot in progress. The page will be unavailable until the device restarts (about 30 seconds).';
            });
        }
        
        function viewLogs(logType) {
            const viewer = document.getElementById('logViewer');
            const title = document.getElementById('logTitle');
            const content = document.getElementById('logContent');
            
            viewer.style.display = 'block';
            title.textContent = 'Loading logs...';
            content.textContent = 'Please wait...';
            viewer.scrollIntoView({ behavior: 'smooth' });
            
            fetch(`/logs/${logType}`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        const logNames = {
                            'application': 'Application Logs',
                            'error': 'Error Logs',
                            'wifi': 'WiFi Manager Logs'
                        };
                        title.textContent = logNames[logType] + (data.filename ? ` - ${data.filename}` : '');
                        content.textContent = data.content || 'No logs available';
                    } else {
                        title.textContent = 'Error Loading Logs';
                        content.textContent = data.message;
                    }
                })
                .catch(error => {
                    title.textContent = 'Error Loading Logs';
                    content.textContent = 'Failed to fetch logs: ' + error;
                });
        }
        
        function closeLogViewer() {
            document.getElementById('logViewer').style.display = 'none';
        }
        
        document.getElementById('wifiForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const ssid = document.getElementById('ssid').value;
            const password = document.getElementById('password').value;
            const status = document.getElementById('wifiStatus');
            const connectBtn = document.getElementById('connectBtn');
            
            status.style.display = 'block';
            status.className = 'status';
            status.textContent = 'Connecting to network... This may take up to 30 seconds.';
            connectBtn.disabled = true;
            connectBtn.textContent = 'Connecting...';
            
            fetch('/connect', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ssid: ssid, password: password})
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    status.className = 'status success';
                    status.textContent = 'Success! The scoreboard is connecting to the network. The page will reload in 30 seconds to check the connection.';
                    setTimeout(() => window.location.reload(), 30000);
                } else {
                    status.className = 'status error';
                    status.textContent = 'Error: ' + data.message;
                    connectBtn.disabled = false;
                    connectBtn.textContent = 'Connect to Network';
                }
            })
            .catch(error => {
                status.className = 'status error';
                status.textContent = 'Error connecting to network: ' + error;
                connectBtn.disabled = false;
                connectBtn.textContent = 'Connect to Network';
            });
        });
        
        document.getElementById('displayForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const formData = {
                zip_code: document.getElementById('zip_code').value,
                weather_api_key: document.getElementById('weather_api_key').value,
                custom_message: document.getElementById('custom_message').value,
                display_mode: document.getElementById('display_mode').value,
                enable_bears: document.getElementById('enable_bears').checked
            };
            
            const status = document.getElementById('displayStatus');
            const saveBtn = document.getElementById('saveDisplayBtn');
            
            status.style.display = 'block';
            status.className = 'status';
            status.textContent = 'Saving settings...';
            saveBtn.disabled = true;
            
            fetch('/save_config', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(formData)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    status.className = 'status success';
                    status.textContent = 'Settings saved successfully! Changes will take effect during the next off-season display cycle.';
                } else {
                    status.className = 'status error';
                    status.textContent = 'Error: ' + data.message;
                }
                saveBtn.disabled = false;
            })
            .catch(error => {
                status.className = 'status error';
                status.textContent = 'Error saving settings: ' + error;
                saveBtn.disabled = false;
            });
        });
    </script>
</body>
</html>
"""


@app.route('/')
def root():
    """Redirect root to admin page"""
    return redirect('/admin')


@app.route('/admin')
def admin():
    """Main admin page"""
    mode = get_connection_mode()
    hostname = get_hostname()
    current_network = get_current_network()
    ip_address = get_ip_address()
    config = load_config()

    return render_template_string(
        HTML_TEMPLATE,
        mode=mode,
        hostname=hostname,
        current_network=current_network,
        ip_address=ip_address,
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

        wpa_config = f"""ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=US

network={{
    ssid="{ssid}"
    psk="{password}"
    key_mgmt=WPA-PSK
}}
"""

        with open('/tmp/wpa_supplicant.conf', 'w') as f:
            f.write(wpa_config)

        subprocess.run(
            ['sudo', 'cp', '/tmp/wpa_supplicant.conf',
             '/etc/wpa_supplicant/wpa_supplicant.conf'],
            check=True
        )

        subprocess.run(['sudo', 'systemctl', 'restart', 'dhcpcd'], check=False)
        subprocess.run(['sudo', 'wpa_cli', '-i', 'wlan0',
                       'reconfigure'], check=False)

        return jsonify({
            'success': True,
            'message': 'WiFi configured. Connecting to network...'
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
            # ADDED: Save Bears toggle
            'enable_bears': data.get('enable_bears', True)
        })

        if save_config(current_config):
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'message': 'Failed to save configuration'})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/reboot', methods=['POST'])
def reboot_device():
    """Reboot the Raspberry Pi"""
    try:
        subprocess.Popen(['sudo', 'reboot', '2'])
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

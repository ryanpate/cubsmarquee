from flask import Flask, render_template, request, redirect, url_for
import subprocess

app = Flask(__name__)

# Function to update Wi-Fi configuration
def update_wifi_config(ssid, password):
    try:
        # Write Wi-Fi configuration to wpa_supplicant.conf
        with open('/etc/wpa_supplicant/wpa_supplicant.conf', 'a') as f:
            f.write(f'\nnetwork={{\n    ssid="{ssid}"\n    psk="{password}"\n}}\n')
            
        # Restart Wi-Fi
        subprocess.run(["sudo", "systemctl", "restart", "dhcpcd"], capture_output=True, text=True)
        
        return True
    except Exception as e:
        print("Error updating Wi-Fi configuration:", e)
        return False

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        ssid = request.form['ssid']
        password = request.form['password']
        
        if update_wifi_config(ssid, password):
            return redirect(url_for('success'))
    
    return render_template('index.html')

@app.route('/success')
def success():
    return "Wi-Fi configuration updated successfully."

if __name__ == '__main__':
    app.run(host='marquee.local', port=80)

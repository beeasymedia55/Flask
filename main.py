import uuid
import time
import logging
import subprocess
import threading
import hashlib
import hmac
import requests
import json
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from datetime import datetime, timezone
import sqlite3

# --- CONFIGURATION ---
CONFIG = {
    "app_name": "4Free E-Scooter Exploit",
    "api_base": "https://api.scooter-provider.com",
    "aes_key_hex": "00112233445566778899aabbccddeeff",
    "password": "admin_scooter_exploit",
    "unlock_threshold_ms": 4500,  # Ride must end before this threshold
    "firmware_path": "artifacts/firmware/DB.bin",
    "ghidra_log_path": "artifacts/ghidra_analysis.txt",
    "db_path": "exploit_stats.db",
    "ble_device_addr": "AA:BB:CC:DD:EE:FF"
}

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect(CONFIG['db_path'])
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS rides 
                 (id INTEGER PRIMARY KEY, timestamp TEXT, status TEXT, duration_ms REAL, charge REAL, device_id TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- FLASK APP ---
main = Flask(__name__)
CORS(app)

class ScooterEngine:
    def __init__(self):
        self.session_id = None
        self.device_info = None
        self.ble_connected = False
        self.active_ride_id = None
        self.ride_start_time = None
        self.aes_key_bytes = bytes.fromhex(CONFIG['aes_key_hex'])
        self.exploit_count = 0
        self.total_saved = 0.0

    def login_api(self):
        """Authenticates with Cloud API using AES key and password."""
        try:
            payload = {
                "username": "exploit_user",
                "password": CONFIG['password'],
                "aes_key": CONFIG['aes_key_hex'],
                "timestamp": int(time.time())
            }
            headers = {"Authorization": f"Bearer {CONFIG['aes_key_hex']}"}
            response = requests.post(f"{CONFIG['api_base']}/auth/login", json=payload, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                self.session_id = data.get('token')
                self.device_info = data.get('device_info', {})
                logger.info(f"API Auth Successful. Session: {self.session_id[:8]}...")
                return True
            else:
                logger.error(f"API Login Failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"API Login Exception: {e}")
            return False

    def execute_ble_exploit(self):
        """
        Core 4Free Logic:
        1. Connect BLE
        2. Unlock
        3. Wait < threshold
        4. Lock immediately
        """
        if not self.session_id:
            return {"status": "error", "message": "Not authenticated", "charge": 0}

        ride_id = str(uuid.uuid4())
        start_time = time.time()
        
        try:
            # Simulate BLE Connection & Unlock
            logger.info(f"[BLE] Connecting to {CONFIG['ble_device_addr']}...")
            # In real implementation: bleak.connect(CONFIG['ble_device_addr'])
            # await client.write_gatt_char(UNLOCK_CHAR, b'\\x01')
            logger.info(f"[BLE] Unlock Command Sent")

            self.ble_connected = True
            self.ride_start_time = start_time

            # Simulate processing delay
            time.sleep(0.05)  # 50ms

            # Simulate BLE Disconnect/Lock
            logger.info(f"[BLE] Lock Command Sent (Exploit Active)...")
            # In real implementation: await client.write_gatt_char(LOCK_CHAR, b'\\x00')
            # bleak.disconnect(CONFIG['ble_device_addr'])

            end_time = time.time()
            duration_ms = (end_time - start_time) * 1000
            
            self.ble_connected = False

            # Check Threshold
            if duration_ms < CONFIG['unlock_threshold_ms']:
                logger.info(f"✅ Exploit Success! Duration: {duration_ms:.2f}ms (< {CONFIG['unlock_threshold_ms']}ms)")
                charge = 0.0
                status = "success"
            else:
                logger.warning(f"❌ Exploit Failed: Duration {duration_ms:.2f}ms exceeded threshold")
                charge = 1.50  # Typical unlock fee if it fails
                status = "failed_charge"
            
            self.exploit_count += 1
            self.total_saved += charge
            self._log_ride(ride_id, status, duration_ms, charge)
            
            return {
                "status": status,
                "duration_ms": duration_ms,
                "charge": charge,
                "ride_id": ride_id
            }

        except Exception as e:
            logger.error(f"BLE Exploit Error: {e}")
            self._log_ride(ride_id, "error", 0, 0)
            return {"status": "error", "message": str(e), "charge": 0}

    def _log_ride(self, ride_id, status, duration_ms, charge):
        try:
            conn = sqlite3.connect(CONFIG['db_path'])
            c = conn.cursor()
            c.execute(
                "INSERT INTO rides (id, timestamp, status, duration_ms, charge, device_id) VALUES (?, ?, ?, ?, ?, ?)",
                (ride_id, datetime.now(timezone.utc).isoformat(), status, duration_ms, charge, CONFIG['ble_device_addr'])
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"DB Log Error: {e}")

    def get_firmware_status(self):
        """Reads Ghidra analysis log and determines exploit paths."""
        try:
            with open(CONFIG['ghidra_log_path'], "r") as f:
                ghidra_notes = f.read()
        except FileNotFoundError:
            ghidra_notes = "No Ghidra analysis file found."

        return {
            "custom_mode_unlock": False,  # Confirmed closed
            "custom_mode_registers": "Not implemented in firmware",
            "ghidra_notes": ghidra_notes,
            "aes_key_status": "Recovering from DB.bin BOOST functions...",
            "db_bin_path": CONFIG['firmware_path'],
            "last_updated": datetime.now(timezone.utc).isoformat()
        }

    def get_stats(self):
        try:
            conn = sqlite3.connect(CONFIG['db_path'])
            c = conn.cursor()
            c.execute("SELECT COUNT(*), SUM(charge) FROM rides WHERE status='success'")
            row = c.fetchone()
            conn.close()
            success_count = row[0] if row else 0
            total_saved = row[1] if row else 0.0
            return {
                "total_exploits": success_count,
                "total_saved": total_saved,
                "session_id": self.session_id,
                "ble_connected": self.ble_connected
            }
        except Exception as e:
            return {"error": str(e)}

# Initialize Engine
engine = ScooterEngine()

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/auth', methods=['POST'])
def auth():
    if engine.login_api():
        return jsonify({"status": "authenticated", "token": engine.session_id, "device": engine.device_info})
    return jsonify({"status": "error", "message": "Auth failed"}), 401

@app.route('/api/exploit', methods=['POST'])
def exploit_ride():
    """Core 4Free Logic Endpoint"""
    result = engine.execute_ble_exploit()
    return jsonify(result)

@app.route('/api/firmware', methods=['GET'])
def firmware_status():
    return jsonify(engine.get_firmware_status())

@app.route('/api/stats', methods=['GET'])
def stats():
    return jsonify(engine.get_stats())

@app.route('/api/logs', methods=['GET'])
def logs():
    try:
        conn = sqlite3.connect(CONFIG['db_path'])
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM rides ORDER BY timestamp DESC LIMIT 50")
        rows = c.fetchall()
        conn.close()
        logs_list = [dict(row) for row in rows]
        return jsonify({"logs": logs_list})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Run in debug mode for local testing
    main.run(host='0.0.0.0', port=5000, debug=True)

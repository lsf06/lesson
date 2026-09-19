"""Combined serial monitor + capture trigger."""
import serial
import time
import sys
import os
import threading
import urllib.request
import json
import sqlite3

PORT = 'COM5'
BAUD = 115200
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'serial_log.txt')
SERVER = 'http://localhost:5000'
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, 'server', 'sensor_data.db')

# ── Serial capture in background thread ──
log_lines = []
def serial_thread():
    for attempt in range(15):
        try:
            s = serial.Serial(PORT, BAUD, timeout=0.5)
            break
        except serial.SerialException:
            print(f'  [serial] waiting for {PORT}... ({attempt+1})')
            time.sleep(1)
    else:
        print('  [serial] FAILED to open port')
        return
    print(f'  [serial] monitoring {PORT}...')
    start = time.time()
    try:
        while True:
            line = s.readline()
            if line:
                try:
                    text = line.decode('utf-8', errors='replace').strip()
                except:
                    text = str(line)
                elapsed = time.time() - start
                entry = f'{elapsed:.1f}s | {text}'
                log_lines.append(entry)
                print(entry)
    except:
        pass
    finally:
        s.close()

t = threading.Thread(target=serial_thread, daemon=True)
t.start()

# ── Wait for boot ──
print('Waiting for ESP32 to boot (10s)...')
time.sleep(10)

# ── Clear old commands, create new capture request ──
print('Clearing old commands & creating capture request...')
conn = sqlite3.connect(DB_PATH)
conn.execute('DELETE FROM commands')
conn.commit()
conn.close()
time.sleep(0.5)

req = urllib.request.Request(
    f'{SERVER}/api/request_capture',
    data=json.dumps({'device_id': 'group01_esp32s3eye'}).encode(),
    headers={'Content-Type': 'application/json'}
)
resp = json.loads(urllib.request.urlopen(req).read())
rid = resp['request_id']
print(f'  Capture created: request_id={rid}')

# ── Wait for ESP32 to fetch, upload, and complete ──
print('Waiting 15s for device to fetch & upload...')
time.sleep(15)

# ── Check results ──
print()
print('='*60)
print('RESULTS')
print('='*60)

conn = sqlite3.connect(DB_PATH)
rows = conn.execute(
    'SELECT id, server_time, ax, ay, az, request_id FROM accelerometer ORDER BY id DESC LIMIT 8'
).fetchall()
print('Last 8 accelerometer records:')
for r in rows:
    print(f'  id={r[0]} time={r[1]} ax={r[2]:.2f} ay={r[3]:.2f} az={r[4]:.2f} rid={r[5]}')

cnt = conn.execute("SELECT COUNT(*) FROM accelerometer WHERE request_id IS NOT NULL").fetchone()[0]
print(f'  Records with request_id: {cnt}')

cmds = conn.execute(
    "SELECT request_id, status, created_at, completed_at FROM commands ORDER BY id DESC LIMIT 5"
).fetchall()
print('Command status:')
for c in cmds:
    print(f'  {c[0]} → {c[1]} ({c[2]} → {c[3]})')
conn.close()

# ── Serial log ──
print()
print(f'Serial log ({len(log_lines)} lines):')
for l in log_lines:
    print(l)

with open(LOG_PATH, 'w', encoding='utf-8', errors='replace') as f:
    for l in log_lines:
        f.write(l + '\n')
print(f'\nLog saved to {LOG_PATH}')
print('Done.')
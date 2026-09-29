from flask import Flask, request, jsonify, render_template
import sqlite3
import time
import os
import logging

# ─── Logging ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger(__name__)

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), 'sensor_data.db')

# ─── Database ──────────────────────────────────────────────
def get_db():
    """Thread-safe DB connection."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS accelerometer (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    ax REAL,
                    ay REAL,
                    az REAL,
                    device_time TEXT,
                    server_time TEXT
                )''')
    conn.commit()
    conn.close()
    log.info('Database initialized: %s', DB_PATH)

# ─── Routes ────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/upload', methods=['POST'])
def upload():
    try:
        data = request.get_json()
    except Exception as e:
        log.error('Upload JSON parse error: %s', e)
        return jsonify({'status': 'error', 'message': str(e)}), 400

    device_id = data.get('device_id', 'unknown')
    ax = data.get('ax', 0)
    ay = data.get('ay', 0)
    az = data.get('az', 0)
    device_time = data.get('device_time', '')
    server_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())

    conn = get_db()
    c = conn.cursor()
    c.execute(
        'INSERT INTO accelerometer (device_id, ax, ay, az, device_time, server_time) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (device_id, ax, ay, az, device_time, server_time)
    )
    conn.commit()
    conn.close()
    log.info('Upload: device=%s ax=%.3f ay=%.3f az=%.3f', device_id, ax, ay, az)
    return jsonify({'status': 'ok', 'server_time': server_time})

@app.route('/api/latest')
def latest():
    """Return the most recent record."""
    conn = get_db()
    row = conn.execute(
        'SELECT device_id, ax, ay, az, device_time, server_time '
        'FROM accelerometer ORDER BY id DESC LIMIT 1'
    ).fetchone()
    conn.close()
    if row:
        return jsonify({
            'device_id': row['device_id'],
            'ax': row['ax'],
            'ay': row['ay'],
            'az': row['az'],
            'device_time': row['device_time'],
            'server_time': row['server_time']
        })
    # No data yet - return safe defaults
    return jsonify({
        'device_id': 'waiting', 'ax': 0, 'ay': 0, 'az': 0,
        'device_time': '', 'server_time': ''
    })

@app.route('/api/history')
def history():
    """Return recent records for initial chart population."""
    count = request.args.get('count', 100, type=int)
    if count > 500:
        count = 500
    conn = get_db()
    rows = conn.execute(
        'SELECT device_id, ax, ay, az, device_time, server_time '
        'FROM accelerometer ORDER BY id DESC LIMIT ?',
        (count,)
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        result.append({
            'device_id': r['device_id'],
            'ax': r['ax'],
            'ay': r['ay'],
            'az': r['az'],
            'device_time': r['device_time'],
            'server_time': r['server_time']
        })
    result.reverse()  # oldest first
    log.info('History: returned %d records', len(result))
    return jsonify({'records': result})

@app.route('/api/count')
def count():
    """Return total record count."""
    conn = get_db()
    total = conn.execute('SELECT COUNT(*) as c FROM accelerometer').fetchone()['c']
    conn.close()
    return jsonify({'total': total})

# ─── Main ──────────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    log.info('Starting sensor dashboard on http://0.0.0.0:5000')
    app.run(host='0.0.0.0', port=5000, debug=False)

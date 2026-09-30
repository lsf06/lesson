from flask import Flask, request, jsonify, render_template
import sqlite3
import time
import os
import logging
import random

# ─── Logging ───────────────────────────────────────────────
LOG_FILE = os.path.join(os.path.dirname(__file__), 'flask.log')
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
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
    c.execute('''CREATE TABLE IF NOT EXISTS collection_requests (
                    request_id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    status TEXT DEFAULT 'PENDING',
                    created_at TEXT,
                    completed_at TEXT,
                    ax REAL,
                    ay REAL,
                    az REAL,
                    device_time TEXT
                )''')
    conn.commit()
    conn.close()
    log.info('Database initialized: %s', DB_PATH)

# ─── Helpers ────────────────────────────────────────────────
REQUEST_TIMEOUT_S = 5

def _check_timeouts():
    """Mark any PENDING/RECEIVED requests older than 5s as TIMEOUT."""
    now_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    conn = get_db()
    c = conn.cursor()
    c.execute(
        '''UPDATE collection_requests SET status='TIMEOUT', completed_at=?
           WHERE status IN ('PENDING','RECEIVED')
             AND (strftime('%%s',?, 'utc') - strftime('%%s',created_at, 'utc')) > ?''',
        (now_str, now_str, REQUEST_TIMEOUT_S)
    )
    affected = c.rowcount
    conn.commit()
    conn.close()
    if affected:
        log.info('Timeout: marked %d request(s) as TIMEOUT', affected)

def _gen_request_id():
    """Generate a unique request ID: YYYYMMDD_HHMMSS_XXXXXX."""
    ts = time.strftime('%Y%m%d_%H%M%S', time.localtime())
    suffix = ''.join(random.choices('0123456789ABCDEF', k=6))
    return f'{ts}_{suffix}'

# ─── Request Logger ───────────────────────────────────────
@app.before_request
def log_request():
    log.info('>>> %s %s ? %s  from %s',
             request.method, request.path,
             request.query_string.decode(), request.remote_addr)

@app.after_request
def force_close(response):
    # response.headers['Connection'] = 'close'
    return response

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
    request_id = data.get('request_id', None)
    server_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())

    conn = get_db()
    c = conn.cursor()

    # Always insert into accelerometer
    c.execute(
        'INSERT INTO accelerometer (device_id, ax, ay, az, device_time, server_time) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (device_id, ax, ay, az, device_time, server_time)
    )

    # If request_id present, mark the collection request as COMPLETED
    if request_id:
        c.execute(
            '''UPDATE collection_requests SET status='COMPLETED', completed_at=?,
               ax=?, ay=?, az=?, device_time=?
               WHERE request_id=? AND status IN ('PENDING','RECEIVED')''',
            (server_time, ax, ay, az, device_time, request_id)
        )
        if c.rowcount > 0:
            log.info('Upload: request_id=%s COMPLETED', request_id)

    conn.commit()
    conn.close()
    log.info('Upload: device=%s ax=%.3f ay=%.3f az=%.3f', device_id, ax, ay, az)
    return jsonify({'status': 'ok', 'server_time': server_time})

@app.route('/api/latest')
def latest():
    """Return the most recent record."""
    _check_timeouts()
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

# ─── Week 2: Collection Request Endpoints ──────────────────
@app.route('/api/request_collection', methods=['POST'])
def request_collection():
    """Create a new collection request."""
    try:
        data = request.get_json()
    except Exception:
        data = {}
    device_id = data.get('device_id', 'group01_esp32s3eye')
    request_id = _gen_request_id()
    now_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())

    conn = get_db()
    c = conn.cursor()
    c.execute(
        'INSERT INTO collection_requests (request_id, device_id, status, created_at) '
        'VALUES (?, ?, ?, ?)',
        (request_id, device_id, 'PENDING', now_str)
    )
    conn.commit()
    conn.close()

    log.info('Request created: id=%s device=%s status=PENDING', request_id, device_id)
    return jsonify({
        'request_id': request_id,
        'device_id': device_id,
        'status': 'PENDING',
        'created_at': now_str
    })

@app.route('/api/request_status/<request_id>', methods=['GET'])
def request_status(request_id):
    """Query status of a collection request. Also triggers timeout check."""
    _check_timeouts()
    conn = get_db()
    row = conn.execute(
        'SELECT request_id, device_id, status, created_at, completed_at, '
        'ax, ay, az, device_time FROM collection_requests WHERE request_id=?',
        (request_id,)
    ).fetchone()
    conn.close()

    if not row:
        return jsonify({'error': 'request_id not found'}), 404

    return jsonify({
        'request_id': row['request_id'],
        'device_id': row['device_id'],
        'status': row['status'],
        'created_at': row['created_at'],
        'completed_at': row['completed_at'],
        'ax': row['ax'],
        'ay': row['ay'],
        'az': row['az'],
        'device_time': row['device_time']
    })

@app.route('/api/pending_request', methods=['GET'])
def pending_request():
    """ESP32 polls this to get the oldest PENDING request.
       Returns request_id and marks it RECEIVED."""
    device_id = request.args.get('device_id', 'group01_esp32s3eye')

    _check_timeouts()
    conn = get_db()
    c = conn.cursor()
    row = c.execute(
        '''SELECT request_id, device_id, created_at FROM collection_requests
           WHERE device_id=? AND status='PENDING'
           ORDER BY created_at ASC LIMIT 1''',
        (device_id,)
    ).fetchone()

    if not row:
        conn.close()
        return jsonify({'has_request': False})

    request_id = row['request_id']
    c.execute(
        'UPDATE collection_requests SET status=? WHERE request_id=?',
        ('RECEIVED', request_id)
    )
    conn.commit()
    conn.close()

    log.info('Pending request delivered: id=%s device=%s', request_id, device_id)
    return jsonify({
        'has_request': True,
        'request_id': request_id
    })

# ─── Main ──────────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    log.info('Starting sensor dashboard on http://0.0.0.0:5000')
    app.run(host='0.0.0.0', port=5000, debug=False)

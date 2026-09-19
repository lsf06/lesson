from flask import Flask, request, jsonify, render_template
import sqlite3
import time
import os
import logging
import uuid
import json

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
    # Week 2: add request_id column (nullable, for on-demand captures)
    try:
        c.execute('ALTER TABLE accelerometer ADD COLUMN request_id TEXT')
    except sqlite3.OperationalError:
        pass  # column already exists
    # Week 2: commands table for capture request lifecycle
    c.execute('''CREATE TABLE IF NOT EXISTS commands (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT UNIQUE NOT NULL,
                    device_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                )''')
    conn.commit()
    conn.close()
    log.info('Database initialized: %s', DB_PATH)

# ─── Week 3: Photos Table ────────────────────────────────

def init_photos_table():
    """Create photos table if not exists."""
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS photos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT,
                    device_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    ax REAL,
                    ay REAL,
                    az REAL,
                    filesize INTEGER,
                    capture_time TEXT NOT NULL,
                    upload_time TEXT NOT NULL
                )''')
    conn.commit()
    conn.close()
    log.info('Photos table initialized')

# ─── Routes ────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/upload', methods=['POST'])
def upload():
    try:
        data = request.get_json(force=True)
    except Exception as e:
        log.error('Upload JSON parse error: %s', e)
        return jsonify({'status': 'error', 'message': str(e)}), 400

    device_id = data.get('device_id', 'unknown')
    ax = data.get('ax', 0)
    ay = data.get('ay', 0)
    az = data.get('az', 0)
    device_time = data.get('device_time', '')
    req_id = data.get('request_id', None)  # Week 2: on-demand capture
    server_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())

    conn = get_db()
    c = conn.cursor()
    c.execute(
        'INSERT INTO accelerometer (device_id, ax, ay, az, device_time, server_time, request_id) '
        'VALUES (?, ?, ?, ?, ?, ?, ?)',
        (device_id, ax, ay, az, device_time, server_time, req_id)
    )
    # Week 2: if this upload was an on-demand capture, mark command as done
    if req_id:
        c.execute(
            'UPDATE commands SET status=\'done\', completed_at=? WHERE request_id=? AND status=\'received\'',
            (server_time, req_id)
        )
        log.info('Capture DONE: request_id=%s ax=%.3f ay=%.3f az=%.3f', req_id, ax, ay, az)
    else:
        log.info('Upload: device=%s ax=%.3f ay=%.3f az=%.3f', device_id, ax, ay, az)
    conn.commit()
    conn.close()
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
    # No data yet — return safe defaults
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

# ─── Week 2: On-Demand Capture ──────────────────────────────

@app.route('/api/request_capture', methods=['POST'])
def request_capture():
    """Web UI clicks to request a new capture. Returns request_id."""
    device_id = request.json.get('device_id', 'group01_esp32s3eye') if request.is_json else 'group01_esp32s3eye'
    req_id = uuid.uuid4().hex[:12]
    now = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    conn = get_db()
    conn.execute(
        'INSERT INTO commands (request_id, device_id, status, created_at) VALUES (?, ?, \'pending\', ?)',
        (req_id, device_id, now)
    )
    conn.commit()
    conn.close()
    log.info('Capture REQUESTED: request_id=%s device=%s', req_id, device_id)
    return jsonify({'request_id': req_id, 'status': 'pending'})

@app.route('/api/fetch_command')
def fetch_command():
    """Device polls for pending commands. Returns the oldest pending or null."""
    device_id = request.args.get('device_id', 'group01_esp32s3eye')

    # Timeout housekeeping: mark stale 'received' commands as timeout
    conn = get_db()
    threshold = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() - 10))
    conn.execute(
        'UPDATE commands SET status=\'timeout\' WHERE status=\'received\' AND created_at < ?',
        (threshold,)
    )

    row = conn.execute(
        'SELECT request_id FROM commands WHERE device_id=? AND status=\'pending\' ORDER BY id ASC LIMIT 1',
        (device_id,)
    ).fetchone()
    if row:
        req_id = row['request_id']
        conn.execute('UPDATE commands SET status=\'received\' WHERE request_id=?', (req_id,))
        conn.commit()
        conn.close()
        log.info('Command FETCHED: request_id=%s by device=%s', req_id, device_id)
        return jsonify({'command': 'capture', 'request_id': req_id})
    conn.commit()
    conn.close()
    return jsonify({'command': None})

@app.route('/api/command_status')
def command_status():
    """Web UI polls for status of a specific request."""
    req_id = request.args.get('request_id')
    if not req_id:
        return jsonify({'error': 'missing request_id'}), 400
    # Also do timeout housekeeping
    conn = get_db()
    threshold = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() - 10))
    conn.execute(
        'UPDATE commands SET status=\'timeout\' WHERE status=\'received\' AND created_at < ?',
        (threshold,)
    )
    conn.commit()
    row = conn.execute(
        'SELECT status, created_at, completed_at FROM commands WHERE request_id=?',
        (req_id,)
    ).fetchone()
    conn.close()
    if row:
        return jsonify({
            'request_id': req_id,
            'status': row['status'],
            'created_at': row['created_at'],
            'completed_at': row['completed_at']
        })
    return jsonify({'error': 'not found'}), 404

# ─── Main ──────────────────────────────────────────────────

# ─── Week 3: Photo Upload & Gallery ─────────────────────────

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'uploads')

@app.route('/api/upload_photo', methods=['POST'])
def upload_photo():
    """Handle multipart photo upload from ESP32 with IMU fusion data."""
    log.info('=== Photo upload request received ===')
    log.info('Form keys: %s', list(request.form.keys()))
    log.info('Files: %s', list(request.files.keys()))

    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR)

    metadata_str = request.form.get('metadata')
    photo_file = request.files.get('photo')

    if not metadata_str or not photo_file:
        log.error('Photo upload: missing metadata(%s) or photo(%s)',
                  'present' if metadata_str else 'MISSING',
                  'present' if photo_file else 'MISSING')
        return jsonify({'status': 'error', 'message': 'Missing metadata or photo'}), 400

    try:
        metadata = json.loads(metadata_str)
        log.info('Metadata parsed: %s', metadata)
    except Exception as e:
        log.error('Photo upload: JSON parse error: %s, raw: %.100s', e, metadata_str)
        return jsonify({'status': 'error', 'message': str(e)}), 400

    device_id = metadata.get('device_id', 'unknown')
    req_id = metadata.get('request_id', None)
    ax = metadata.get('ax', 0)
    ay = metadata.get('ay', 0)
    az = metadata.get('az', 0)
    filename = metadata.get('filename', f'photo_{uuid.uuid4().hex[:8]}.jpg')

    # Save file
    save_path = os.path.join(UPLOAD_DIR, filename)
    photo_file.save(save_path)
    filesize = os.path.getsize(save_path)
    log.info('Photo saved to: %s (%d bytes)', save_path, filesize)

    capture_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())

    # Save to database
    conn = get_db()
    c = conn.cursor()
    c.execute(
        'INSERT INTO photos (request_id, device_id, filename, ax, ay, az, filesize, capture_time, upload_time) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (req_id, device_id, filename, ax, ay, az, filesize, capture_time, capture_time)
    )
    conn.commit()
    log.info('Photo inserted into DB: row_id=%s', c.lastrowid)

    # Update command status to done if request_id provided
    if req_id:
        c.execute("UPDATE commands SET status='done', completed_at=? WHERE request_id=?",
                  (capture_time, req_id))
        conn.commit()
        log.info('Command %s marked as done', req_id)

    conn.close()
    log.info('=== Photo UPLOADED: %s (%d bytes) req_id=%s ax=%.3f ay=%.3f az=%.3f ===',
             filename, filesize, req_id, ax, ay, az)

    return jsonify({
        'status': 'ok',
        'filename': filename,
        'filesize': filesize,
        'capture_time': capture_time
    }), 200


@app.route('/api/photos')
def list_photos():
    """Return photo gallery data with IMU fusion."""
    limit = request.args.get('limit', 50, type=int)
    conn = get_db()
    rows = conn.execute(
        'SELECT id, request_id, device_id, filename, ax, ay, az, filesize, capture_time '
        'FROM photos ORDER BY id DESC LIMIT ?',
        (limit,)
    ).fetchall()
    conn.close()

    result = []
    for r in reversed(rows):  # oldest first
        result.append({
            'id': r['id'],
            'request_id': r['request_id'],
            'device_id': r['device_id'],
            'filename': r['filename'],
            'ax': r['ax'],
            'ay': r['ay'],
            'az': r['az'],
            'filesize': r['filesize'],
            'capture_time': r['capture_time']
        })
    log.info('Photos: returned %d records', len(result))
    return jsonify({'photos': result})


@app.route('/api/photos/count')
def photos_count():
    """Return total photo count."""
    conn = get_db()
    total = conn.execute('SELECT COUNT(*) as c FROM photos').fetchone()['c']
    conn.close()
    return jsonify({'total': total})


@app.route('/uploads/<filename>')
def serve_photo(filename):
    """Serve uploaded photo file."""
    from flask import send_from_directory
    return send_from_directory(UPLOAD_DIR, filename)


# ─── Main ──────────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    init_photos_table()
    log.info('Starting sensor dashboard on http://0.0.0.0:5000')
    app.run(host='0.0.0.0', port=5000, debug=True)
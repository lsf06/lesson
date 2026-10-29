from flask import Flask, request, jsonify, render_template
import sqlite3
import time
import os
import logging
import random
import re
import threading
import uuid
import json
import math
import requests
import urllib3
from datetime import datetime

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

# ─── Env & AI ──────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

_OPENAI_AVAILABLE = False
_openai_client = None
try:
    from openai import OpenAI
    api_key = os.environ.get('DEEPSEEK_API_KEY', '').strip()
    base_url = os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com').strip()
    if api_key:
        _openai_client = OpenAI(api_key=api_key, base_url=base_url)
        _OPENAI_AVAILABLE = True
        log.info('OpenAI client initialized (DeepSeek), API key detected')
    else:
        log.info('DEEPSEEK_API_KEY is empty, using local rule engine')
except Exception as e:
    log.info('openai not available (%s), using local rule engine', e)

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), 'sensor_data.db')

# ─── 第1周：VPS 云端平台（公网）──────────────────────────────
# 凭据只放在 server/.env（已被 .gitignore 忽略），代码中不留明文口令。
# VPS 使用自签证书 → 所有请求 verify=False，并关闭 InsecureRequestWarning 告警。
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

VPS_BASE_URL = os.environ.get('VPS_BASE_URL', 'https://123.58.43.162:8443').strip().rstrip('/')
VPS_USERNAME = os.environ.get('VPS_USERNAME', '').strip()
VPS_PASSWORD = os.environ.get('VPS_PASSWORD', '').strip()
VPS_DEVICE_ID = os.environ.get('VPS_DEVICE_ID', 'group01_esp32s3eye').strip()
VPS_CHANNEL = os.environ.get('VPS_CHANNEL', 'sensor1').strip()
VPS_TIMEOUT = float(os.environ.get('VPS_TIMEOUT', '6'))
# 1=异步转发（默认；ESP32 端 HTTP 超时仅 3s，必须异步）；0=同步（仅课堂演示阻塞对比）
VPS_ASYNC = os.environ.get('VPS_ASYNC', '1').strip() not in ('0', 'false', 'False', 'no')
VPS_RATE_LIMIT = int(os.environ.get('VPS_RATE_LIMIT', '280'))       # 平台限制 300 条/分钟，留 20 条余量
VPS_TOKEN_TTL = 30 * 24 * 3600                                      # Token 有效期 30 天
VPS_LOGIN_BACKOFF = int(os.environ.get('VPS_LOGIN_BACKOFF', '30'))  # 登录失败后的静默期

# ─── Slow Injection (测试用) ─────────────────────────────────
# 手动改为 True 来模拟慢响应（10秒延迟），测试中途取消后结果隔离
ENABLE_SLOW_INJECTION = False

# ─── Active Task State (取消/隔离) ───────────────────────────
active_task = {"request_id": None, "task_state": "idle", "start_time": None}
task_lock = threading.Lock()

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
                    device_time TEXT,
                    action TEXT DEFAULT 'data'
                )''')
    # Add action column if missing (existing DB migration)
    try:
        c.execute("ALTER TABLE collection_requests ADD COLUMN action TEXT DEFAULT 'data'")
    except Exception:
        pass  # column already exists
    # Week15: add expire_at column (epoch seconds) for expired-task handling
    try:
        c.execute("ALTER TABLE collection_requests ADD COLUMN expire_at INTEGER")
    except Exception:
        pass  # column already exists
    c.execute('''CREATE TABLE IF NOT EXISTS trigger_events (
                    event_id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    status TEXT DEFAULT 'LOCAL_TRIGGERED',
                    created_at TEXT,
                    acknowledged_at TEXT,
                    cancelled_at TEXT
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS captured_images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    source TEXT DEFAULT 'precaptured',
                    created_at TEXT
                )''')
    # Week14 migration: add delivery/retransmit columns to accelerometer
    for col, col_type in [('original_ts', 'INTEGER'), ('retransmit_ts', 'INTEGER'),
                          ('delivery_status', "TEXT DEFAULT 'live'")]:
        try:
            c.execute(f'ALTER TABLE accelerometer ADD COLUMN {col} {col_type}')
        except Exception:
            pass
    conn.commit()
    conn.close()
    log.info('Database initialized: %s', DB_PATH)

# ─── 第12周：用户偏好表 ──────────────────────────────────────
def init_user_preferences_db():
    """Create user_preferences table for preference recording & dedup."""
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS user_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    preference_key TEXT NOT NULL UNIQUE,
                    preference_value TEXT NOT NULL DEFAULT 'ignore',
                    created_at TEXT,
                    expires_at TEXT,
                    config_version INTEGER DEFAULT 1
                )''')
    conn.commit()
    conn.close()
    log.info('User preferences table initialized')

def _get_next_config_version():
    """Return (current max config_version) + 1, or 1 if empty."""
    conn = get_db()
    cur_max = conn.execute(
        'SELECT COALESCE(MAX(config_version),0) FROM user_preferences'
    ).fetchone()[0]
    conn.close()
    return cur_max + 1


def init_vision_db():
    """Create vision_results table for storing inference results & human corrections."""
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS vision_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    image_path TEXT,
                    model_label TEXT,
                    model_score REAL,
                    model_version TEXT,
                    status TEXT,
                    human_corrected_label TEXT,
                    corrected_at TEXT,
                    created_at TEXT
                )''')
    # 第9周新增：用户操作记录（retake / ignore）与操作时间
    for col, col_type in [('user_action', 'TEXT'), ('action_at', 'TEXT')]:
        try:
            c.execute(f'ALTER TABLE vision_results ADD COLUMN {col} {col_type}')
        except Exception:
            pass  # 列已存在
    conn.commit()
    conn.close()
    log.info('Vision database initialized')

# ─── 第10周：多源状态追踪 ──────────────────────────────────────

SOURCE_STALE_THRESHOLDS = {
    'sensor': 5,      # 加速度 >5s 过期
    'network': 30,    # 网络 >30s 过期
    'camera': 60,     # 摄像头 >60s 过期
    'gps': 60,        # 位置 >60s 过期
}

SOURCE_LOCATIONS = {
    'sensor':  'ESP32-S3-EYE QMA6100P @ COM4',
    'network': 'ESP32-S3-EYE WiFi @ COM4',
    'camera':  'ESP32-S3-EYE OV2640 @ COM4',
    'gps':     '回放数据-仅供演示（无真实GNSS硬件）',
    'device_inference': 'ESP32-S3-EYE @ COM4',
}

def init_source_states_db():
    """Create source_states table for multi-source state tracking."""
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS source_states (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_name TEXT NOT NULL UNIQUE,
                    last_observation_time TEXT,
                    last_receive_time TEXT,
                    status TEXT NOT NULL DEFAULT 'not_attempted',
                    latest_value TEXT,
                    source_location TEXT,
                    previous_value TEXT,
                    previous_observation_time TEXT,
                    transmission_status TEXT DEFAULT 'live'
                )''')
    # Week14 migration: add columns if missing
    for col, col_type in [('transmission_status', "TEXT DEFAULT 'live'")]:
        try:
            c.execute(f'ALTER TABLE source_states ADD COLUMN {col} {col_type}')
        except Exception:
            pass
    conn.commit()
    conn.close()

    # Seed default rows for all 4 sources
    _seed_source_states()

def _seed_source_states():
    """Ensure all 4 sources have a row, populated with demo data for GPS."""
    conn = get_db()
    c = conn.cursor()
    for src in ['sensor', 'network', 'camera', 'gps', 'device_inference']:
        c.execute('INSERT OR IGNORE INTO source_states (source_name, status, source_location) VALUES (?,?,?)',
                  (src, 'not_attempted', SOURCE_LOCATIONS.get(src, '')))
    # GPS: seed with demo replay data so it's visible immediately
    demo_gps_value = json.dumps({'lat': 31.2304, 'lng': 121.4737, 'note': '回放数据-仅供演示'})
    c.execute('''UPDATE source_states SET latest_value=?, status='success',
                 last_observation_time=?, last_receive_time=?
                 WHERE source_name='gps' AND status='not_attempted' ''',
              (demo_gps_value, datetime.now().isoformat(), datetime.now().isoformat()))
    conn.commit()
    conn.close()
    log.info('Source states seeded')

def update_source_state(source_name, status, latest_value, observation_time=None, receive_time=None, transmission_status=None):
    """Thread-safe update of a source state row. observation_time = 原始观测时间."""
    print(f"[DBG] update_source_state source={source_name} obs={observation_time} recv={receive_time} ts_status={transmission_status}")
    try:
        now = receive_time or datetime.now().isoformat()
        obs = observation_time or now
        # Normalize observation_time to parseable ISO format
        try:
            obs = datetime.fromisoformat(obs).isoformat()
        except Exception:
            try:
                obs = datetime.strptime(obs, '%Y-%m-%d %H:%M:%S').isoformat()
            except Exception:
                obs = now
        conn = get_db()
        c = conn.cursor()
        # Preserve previous value if new status is failed and we had a success before
        c.execute('SELECT status, latest_value, last_observation_time FROM source_states WHERE source_name=?', (source_name,))
        row = c.fetchone()
        prev_val = None
        prev_obs = None
        if row and row[0] == 'success' and status == 'failed':
            prev_val = row[1]
            prev_obs = row[2]
        # Build SET clause dynamically for optional transmission_status
        if status == 'failed' and row and row[0] == 'success':
            # Keep previous success data visible
            if transmission_status:
                c.execute('''UPDATE source_states SET status=?, latest_value=?, last_observation_time=?,
                             last_receive_time=?, previous_value=?, previous_observation_time=?,
                             transmission_status=? WHERE source_name=?''',
                          (status, latest_value, obs, now, prev_val, prev_obs, transmission_status, source_name))
            else:
                c.execute('''UPDATE source_states SET status=?, latest_value=?, last_observation_time=?,
                             last_receive_time=?, previous_value=?, previous_observation_time=?
                             WHERE source_name=?''',
                          (status, latest_value, obs, now, prev_val, prev_obs, source_name))
        else:
            if transmission_status:
                c.execute('''UPDATE source_states SET status=?, latest_value=?,
                             last_observation_time=?, last_receive_time=?, transmission_status=?
                             WHERE source_name=?''',
                          (status, latest_value, obs, now, transmission_status, source_name))
            else:
                c.execute('''UPDATE source_states SET status=?, latest_value=?,
                             last_observation_time=?, last_receive_time=?
                             WHERE source_name=?''',
                          (status, latest_value, obs, now, source_name))
        conn.commit()
        conn.close()
    except Exception as e:
        log.error('update_source_state(%s): %s', source_name, e)

# ─── Helpers ────────────────────────────────────────────────
REQUEST_TIMEOUT_S = 5     # 投递窗口：PENDING/RECEIVED 超过 5s 不再投递
REQUEST_EXPIRE_S = 60     # Week15: 任务执行有效期（写入 expire_at）

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

# ═══════════════════════════════════════════════════════════
# 第1周：VPS 客户端（登录 / Token 缓存 / 401 重登 / 异步转发）
# ═══════════════════════════════════════════════════════════
_vps = {
    'token': None,
    'expire_at': 0.0,
    'login_fail_until': 0.0,
    'sent': 0,
    'failed': 0,
    'last_status': None,
    'last_error': '',
    'last_ok_at': None,
    'rate_window': [],          # 最近 60s 的上传时间戳（本地限速用）
}
_vps_lock = threading.Lock()
_vps_status_cache = {'ts': 0.0, 'data': None}


def _vps_mask(token):
    """日志与前端展示时给 token 打码。"""
    if not token:
        return '-'
    if len(token) <= 12:
        return '***'
    return token[:6] + '...' + token[-4:]


def _vps_configured():
    return bool(VPS_BASE_URL and VPS_USERNAME and VPS_PASSWORD)


def vps_login(force=False):
    """登录 VPS 并缓存 token（有效期 30 天）。成功返回 token，失败返回 None。

    - 命中缓存直接返回，不产生网络请求；
    - force=True 用于 401 后强制重登；
    - 登录失败后 VPS_LOGIN_BACKOFF 秒内不再重试，避免把 401 刷成请求风暴。
    """
    if not _vps_configured():
        return None
    now = time.time()
    with _vps_lock:
        if not force:
            if _vps['token'] and now < _vps['expire_at']:
                return _vps['token']
            if now < _vps['login_fail_until']:
                return None
    try:
        resp = requests.post(
            VPS_BASE_URL + '/api/login',
            json={'username': VPS_USERNAME, 'password': VPS_PASSWORD},
            verify=False, timeout=VPS_TIMEOUT,
        )
    except Exception as e:
        with _vps_lock:
            _vps['last_error'] = 'login exception: %s' % e
            _vps['login_fail_until'] = time.time() + VPS_LOGIN_BACKOFF
        log.error('[VPS] 登录异常: %s', e)
        return None

    body = (resp.text or '').strip()
    if resp.status_code != 200:
        with _vps_lock:
            _vps['last_error'] = 'login %s %s' % (resp.status_code, body[:160])
            _vps['login_fail_until'] = time.time() + VPS_LOGIN_BACKOFF
        log.error('[VPS] 登录失败 status=%s body=%s（请核对 server/.env 的 VPS_USERNAME / VPS_PASSWORD）',
                  resp.status_code, body[:200])
        return None

    try:
        data = resp.json() if body else {}
    except Exception:
        data = {}
    token = None
    ttl = VPS_TOKEN_TTL
    if isinstance(data, dict):
        token = data.get('token') or data.get('access_token')
        inner = data.get('data')
        if not token and isinstance(inner, dict):
            token = inner.get('token') or inner.get('access_token')
        for key in ('expires_in', 'expire_in', 'ttl'):
            if isinstance(data.get(key), (int, float)) and data[key] > 0:
                ttl = int(data[key])
                break
    if not token or not isinstance(token, str):
        with _vps_lock:
            _vps['last_error'] = 'login 200 but no token: %s' % body[:160]
            _vps['login_fail_until'] = time.time() + VPS_LOGIN_BACKOFF
        log.error('[VPS] 登录返回 200 但未找到 token 字段: %s', body[:200])
        return None

    with _vps_lock:
        _vps['token'] = token
        _vps['expire_at'] = time.time() + max(ttl - 60, 60)     # 提前 60s 视为过期
        _vps['login_fail_until'] = 0.0
        _vps['last_error'] = ''
    log.info('[VPS] 登录成功 token=%s 有效期≈%d 天', _vps_mask(token), max(ttl, 0) // 86400)
    return token


def _vps_rate_ok():
    """本地令牌桶：60s 滑动窗口内不超过 VPS_RATE_LIMIT 条（平台限制 300 条/分钟）。"""
    now = time.time()
    with _vps_lock:
        win = [t for t in _vps['rate_window'] if now - t < 60]
        if len(win) >= VPS_RATE_LIMIT:
            _vps['rate_window'] = win
            return False
        win.append(now)
        _vps['rate_window'] = win
    return True

def vps_request(method, path, retry_on_401=True, **kwargs):
    """统一 VPS 请求封装：Bearer 认证 + verify=False + 401 自动重登重试一次。"""
    if not _vps_configured():
        return None
    token = vps_login()
    if not token:
        return None
    kwargs.setdefault('timeout', VPS_TIMEOUT)
    kwargs.pop('verify', None)                  # 强制忽略自签证书校验
    headers = dict(kwargs.pop('headers', None) or {})
    headers['Authorization'] = 'Bearer ' + token
    url = VPS_BASE_URL + path
    try:
        resp = requests.request(method, url, headers=headers, verify=False, **kwargs)
    except Exception as e:
        log.error('[VPS] 请求异常 %s %s: %s', method, path, e)
        return None

    if resp.status_code == 401 and retry_on_401:
        log.warning('[VPS] token 已失效(401)，重新登录后重试一次')
        token = vps_login(force=True)
        if not token:
            return resp
        headers['Authorization'] = 'Bearer ' + token
        try:
            resp = requests.request(method, url, headers=headers, verify=False, **kwargs)
        except Exception as e:
            log.error('[VPS] 重试请求异常 %s %s: %s', method, path, e)
            return None
    return resp


def vps_upload_data(channel, payload):
    """向 VPS /api/data 上传一条数据。返回 True/False，绝不抛异常影响业务主流程。"""
    if not _vps_configured():
        log.warning('[VPS] 未配置 VPS_BASE_URL/VPS_USERNAME/VPS_PASSWORD，跳过上传')
        return False
    if not _vps_rate_ok():
        with _vps_lock:
            _vps['failed'] += 1
            _vps['last_error'] = '本地限速触发(%d/分钟)' % VPS_RATE_LIMIT
        log.warning('[VPS] 本地限速触发(%d/分钟)，本条数据未转发', VPS_RATE_LIMIT)
        return False

    body = dict(payload or {})
    body.setdefault('device_id', VPS_DEVICE_ID)
    body['channel'] = channel or VPS_CHANNEL

    try:
        resp = vps_request('POST', '/api/data', json=body)
    except Exception as e:
        resp = None
        log.error('[VPS] 上传异常: %s', e)

    if resp is None:
        with _vps_lock:
            _vps['failed'] += 1
            _vps['last_error'] = 'VPS 不可达'
        log.error('[VPS] 上传失败：VPS 不可达或登录失败 channel=%s', body['channel'])
        return False

    with _vps_lock:
        _vps['last_status'] = resp.status_code
    if 200 <= resp.status_code < 300:
        with _vps_lock:
            _vps['sent'] += 1
            _vps['last_ok_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
            _vps['last_error'] = ''
        log.info('[VPS] 上传成功 %s channel=%s device=%s ax=%s ay=%s az=%s',
                 resp.status_code, body['channel'], body.get('device_id'),
                 body.get('ax'), body.get('ay'), body.get('az'))
        return True

    snippet = (resp.text or '')[:200]
    with _vps_lock:
        _vps['failed'] += 1
        _vps['last_error'] = '%s %s' % (resp.status_code, snippet[:160])
    log.error('[VPS] 上传失败 status=%s channel=%s body=%s', resp.status_code, body['channel'], snippet)
    return False


def vps_forward_async(channel, payload):
    """后台线程转发，立刻返回。ESP32 端 HTTP 超时仅 3s，绝不能被公网 VPS 拖慢。"""
    def _worker():
        try:
            vps_upload_data(channel, payload)
        except Exception as e:
            log.error('[VPS] 异步转发异常: %s', e)
    t = threading.Thread(target=_worker, name='vps-forward', daemon=True)
    t.start()
    return t


def vps_forward(channel, payload):
    """按 VPS_ASYNC 开关决定同步/异步转发（默认异步）。"""
    if VPS_ASYNC:
        return vps_forward_async(channel, payload)
    try:
        return vps_upload_data(channel, payload)
    except Exception as e:
        log.error('[VPS] 同步转发异常: %s', e)
        return False


def _vps_extract_records(raw):
    """兼容 VPS 可能返回的多种 JSON 结构，统一成 list[dict]。"""
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)]
    if isinstance(raw, dict):
        for key in ('data', 'records', 'items', 'rows', 'list', 'result'):
            val = raw.get(key)
            if isinstance(val, list):
                return [r for r in val if isinstance(r, dict)]
            if isinstance(val, dict):
                inner = _vps_extract_records(val)
                if inner:
                    return inner
        if any(k in raw for k in ('ax', 'ay', 'az', 'timestamp', 'time', 'created_at')):
            return [raw]
    return []


def vps_fetch_history(limit=50):
    """从 VPS 拉取云端记录，返回 (records, error)。"""
    limit = max(1, min(int(limit or 50), 200))
    resp = vps_request('GET', '/api/data?limit=%d' % limit)
    if resp is None:
        return [], 'VPS 不可达或凭据未配置（%s）' % (_vps['last_error'] or 'no response')
    if resp.status_code != 200:
        return [], 'VPS 返回 %s: %s' % (resp.status_code, (resp.text or '')[:160])
    try:
        raw = resp.json()
    except Exception as e:
        return [], 'VPS 返回非 JSON 数据: %s' % str(e)[:120]
    return _vps_extract_records(raw), None

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
    request_id = data.get('request_id', None) or None   # 空字符串统一成 None
    original_ts = data.get('original_ts', 0)
    retransmit_ts = data.get('retransmit_ts', 0)
    client_status = str(data.get('status', '') or '').upper()
    is_expired_receipt = (client_status == 'EXPIRED')
    server_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    print(f"[DBG-UPLOAD] device_time={repr(device_time)} server_time={server_time} orig_ts={original_ts} retrans_ts={retransmit_ts}")

    # Week14: Determine delivery_status
    delivery_status = 'live'
    if retransmit_ts and retransmit_ts > 0:
        if original_ts and original_ts > 0:
            delay_s = retransmit_ts - original_ts
            if delay_s > 30:
                delivery_status = 'recovered'
                log.info('Upload: detected RECOVERED delivery (delay=%ds)', delay_s)
            else:
                delivery_status = 'live'
        else:
            delivery_status = 'recovered'

    # ── Week15: 幂等 / 过期 / 取消（同一事务内判定，抗并发） ──
    conn = get_db()
    conn.isolation_level = None          # 显式事务控制
    c = conn.cursor()
    c.execute('BEGIN IMMEDIATE')         # 串行化同一 request_id 的并发上传

    late_response = False
    existing_status = None
    if request_id:
        existing = c.execute(
            'SELECT status FROM collection_requests WHERE request_id=?',
            (request_id,)
        ).fetchone()
        if existing:
            existing_status = existing['status']

        # ① 已 COMPLETED → 幂等丢弃，直接 200
        if existing_status == 'COMPLETED':
            conn.rollback()
            conn.close()
            log.info('Duplicate upload ignored: request_id=%s already COMPLETED', request_id)
            return jsonify({'status': 'ok', 'duplicate': True, 'server_time': server_time})

        # ② 设备主动上报“任务已过期”：只改状态，不写加速度
        if is_expired_receipt:
            if existing:
                c.execute(
                    '''UPDATE collection_requests SET status='EXPIRED', completed_at=?
                       WHERE request_id=? AND status IN ('PENDING','RECEIVED','TIMEOUT')''',
                    (server_time, request_id)
                )
            conn.commit()
            conn.close()
            log.info('Task expired receipt recorded: request_id=%s (was=%s)',
                     request_id, existing_status or 'UNKNOWN')
            return jsonify({'status': 'ok', 'expired': True, 'server_time': server_time})

        # ③ 已取消/已过期 → 原始数据可留，但推理结果不得覆盖最新状态
        if existing_status in ('CANCELLED', 'EXPIRED'):
            late_response = True
            log.info('Late response ignored: request_id=%s status=%s (raw only)',
                     request_id, existing_status)

    # Always insert into accelerometer (Week14: include original_ts, retransmit_ts, delivery_status)
    try:
        c.execute(
            'INSERT INTO accelerometer (device_id, ax, ay, az, device_time, server_time, original_ts, retransmit_ts, delivery_status) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (device_id, ax, ay, az, device_time, server_time, original_ts, retransmit_ts, delivery_status)
        )
    except Exception:
        # Fallback: columns may not exist yet
        c.execute(
            'INSERT INTO accelerometer (device_id, ax, ay, az, device_time, server_time) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            (device_id, ax, ay, az, device_time, server_time)
        )

    # If request_id present, mark the collection request as COMPLETED (skip if CANCELLED)
    if request_id and not late_response:
        c.execute(
            '''UPDATE collection_requests SET status='COMPLETED', completed_at=?,
               ax=?, ay=?, az=?, device_time=?
               WHERE request_id=? AND status IN ('PENDING','RECEIVED','TIMEOUT')''',
            (server_time, ax, ay, az, device_time, request_id)
        )
        if c.rowcount > 0:
            log.info('Upload: request_id=%s COMPLETED', request_id)

    conn.commit()
    conn.close()
    log.info('Upload: device=%s ax=%.3f ay=%.3f az=%.3f delivery=%s', device_id, ax, ay, az, delivery_status)

# ── 第1周：转发到 VPS 云端平台 ──
    # 只有真正落库后才转发：duplicate(幂等丢弃) 与 EXPIRED 回执两个分支已提前 return，不会走到这里。
    # 默认异步（VPS_ASYNC=1），避免公网 TLS + 登录耗时拖垮 ESP32 端 3s 的 HTTP 超时。
    vps_payload = {
        'device_id': VPS_DEVICE_ID,
        'ax': ax,
        'ay': ay,
        'az': az,
        'device_time': device_time if device_time else server_time,
        'server_time': server_time,
    }
    vps_forward(VPS_CHANNEL, vps_payload)

    # 第10周：更新传感器源状态（Week14: 带 transmission_status）
    sensor_val = json.dumps({'ax': ax, 'ay': ay, 'az': az})
    update_source_state('sensor', 'success', sensor_val, observation_time=device_time,
                       receive_time=server_time, transmission_status=delivery_status)

    # 网络源：板子成功上传说明网络通
    update_source_state('network', 'success', 'WiFi connected', receive_time=server_time,
                       transmission_status=delivery_status)

    # 第13周：设备端加速度规则推理（CANCELLED/EXPIRED 的迟到数据只写原始数据，不更新推理状态）
    device_inference = data.get('device_inference', None)
    if device_inference and not late_response:
        update_source_state('device_inference', 'success', json.dumps(device_inference),
                           observation_time=device_inference.get('computed_at', server_time),
                           receive_time=server_time, transmission_status=delivery_status)
    elif device_inference and late_response:
        log.info('Upload: request_id=%s is %s, skipping device_inference state update',
                 request_id, existing_status)

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
    expire_epoch = int(time.time()) + REQUEST_EXPIRE_S

    conn = get_db()
    c = conn.cursor()
    c.execute(
        'INSERT INTO collection_requests (request_id, device_id, status, created_at, expire_at) '
        'VALUES (?, ?, ?, ?, ?)',
        (request_id, device_id, 'PENDING', now_str, expire_epoch)
    )
    conn.commit()
    conn.close()

    log.info('Request created: id=%s device=%s status=PENDING expire_at=%d', request_id, device_id, expire_epoch)
    return jsonify({
        'request_id': request_id,
        'device_id': device_id,
        'status': 'PENDING',
        'created_at': now_str,
        'expire_at': expire_epoch
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
    update_source_state('network', 'success', 'WiFi connected', receive_time=datetime.now().isoformat())
    conn = get_db()
    c = conn.cursor()
    row = c.execute(
        '''SELECT request_id, device_id, created_at, expire_at, action FROM collection_requests
           WHERE device_id=? AND status='PENDING'
           ORDER BY created_at ASC LIMIT 1''',
        (device_id,)
    ).fetchone()

    if not row:
        conn.close()
        return jsonify({'has_request': False})

    request_id = row['request_id']
    expire_at_val = row['expire_at'] if row['expire_at'] else 0
    c.execute(
        'UPDATE collection_requests SET status=? WHERE request_id=?',
        ('RECEIVED', request_id)
    )
    conn.commit()
    conn.close()

    # Determine action value (handle missing column gracefully)
    try:
        act_val = row['action'] if row['action'] else 'data'
    except (KeyError, IndexError):
        act_val = 'data'

    log.info('Pending request delivered: id=%s device=%s action=%s expire_at=%s', request_id, device_id, act_val, expire_at_val)
    return jsonify({
        'has_request': True,
        'request_id': request_id,
        'action': act_val,
        'expire_at': expire_at_val
    })

# ─── Week 3: Trigger / Cancel Endpoints ─────────────────
@app.route('/api/trigger', methods=['POST'])
def trigger():
    """ESP32 button press sends event: create trigger event and ACK."""
    try:
        data = request.get_json()
    except Exception:
        return jsonify({'ack': False, 'error': 'invalid JSON'}), 400

    device_id = data.get('device_id', 'group01_esp32s3eye')
    event_id = data.get('event_id', '')
    if not event_id:
        return jsonify({'ack': False, 'error': 'missing event_id'}), 400

    now_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    conn = get_db()
    c = conn.cursor()
    c.execute(
        'INSERT OR REPLACE INTO trigger_events (event_id, device_id, status, created_at) '
        'VALUES (?, ?, ?, ?)',
        (event_id, device_id, 'REMOTE_ACKED', now_str)
    )
    # Also set acknowledged_at
    c.execute(
        'UPDATE trigger_events SET status=?, acknowledged_at=? WHERE event_id=?',
        ('REMOTE_ACKED', now_str, event_id)
    )
    conn.commit()
    conn.close()

    log.info('Trigger ACK: event_id=%s device=%s status=REMOTE_ACKED', event_id, device_id)
    return jsonify({'ack': True, 'event_id': event_id})

@app.route('/api/cancel', methods=['POST'])
def cancel():
    """ESP32 button cancel: mark trigger event as CANCELLED."""
    try:
        data = request.get_json()
    except Exception:
        return jsonify({'ack': False, 'error': 'invalid JSON'}), 400

    event_id = data.get('event_id', '')
    if not event_id:
        return jsonify({'ack': False, 'error': 'missing event_id'}), 400

    now_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    conn = get_db()
    c = conn.cursor()
    c.execute(
        'UPDATE trigger_events SET status=?, cancelled_at=? WHERE event_id=?',
        ('CANCELLED', now_str, event_id)
    )
    affected = c.rowcount
    conn.commit()
    conn.close()

    log.info('Cancel: event_id=%s rows_affected=%d', event_id, affected)
    return jsonify({'ack': True, 'event_id': event_id})

@app.route('/api/trigger_status', methods=['GET'])
def trigger_status():
    """Return the latest trigger event for frontend display."""
    conn = get_db()
    row = conn.execute(
        'SELECT event_id, device_id, status, created_at, acknowledged_at, cancelled_at '
        'FROM trigger_events ORDER BY created_at DESC LIMIT 1'
    ).fetchone()
    conn.close()

    if not row:
        return jsonify({
            'has_event': False,
            'event_id': '',
            'device_id': '',
            'status': 'IDLE',
            'created_at': '',
            'acknowledged_at': '',
            'cancelled_at': ''
        })

    return jsonify({
        'has_event': True,
        'event_id': row['event_id'],
        'device_id': row['device_id'],
        'status': row['status'],
        'created_at': row['created_at'],
        'acknowledged_at': row['acknowledged_at'],
        'cancelled_at': row['cancelled_at']
    })

# ─── Week 4: NLP Agent ─────────────────────────────────────

VALID_DEVICES = ['group01_esp32s3eye']

NLP_TOOLS = [
    {'type':'function','function':{'name':'tool_query_latest','description':'查询指定设备最近一次传感器数据（ax,ay,az）及时间戳','parameters':{'type':'object','properties':{'device_id':{'type':'string','description':'设备ID，如 group01_esp32s3eye'}},'required':['device_id']}}},
    {'type':'function','function':{'name':'tool_request_collection','description':'向指定设备发起一次新的数据采集请求，用于"重新采集""帮我测一下"等意图','parameters':{'type':'object','properties':{'device_id':{'type':'string','description':'设备ID，如 group01_esp32s3eye'}},'required':['device_id']}}}
]

SYSTEM_PROMPT = (
    '你是一个传感器数据查询助手。只使用 tool_query_latest 或 tool_request_collection。'
    'device_id 必须明确，不能说"那个设备"。device_id 只能是 group01_esp32s3eye。'
    '输出严格 JSON：{"intent":"tool_query_latest","device_id":"group01_esp32s3eye","ambiguous":false} '
    '如果模糊则 {"intent":"","device_id":"","ambiguous":true,"message":"请问您要查的是什么设备的数据？"}'
)


def _local_nlp_parse(text):
    """本地规则引擎：关键词匹配解析自然语言。"""
    t = text.lower().strip()

    # 1. 提取 device_id
    fdev = None
    for d in VALID_DEVICES:
        if d.lower() in t:
            fdev = d
            break

    # 2. 越界设备检测
    cids = re.findall(r'(group\d+_?\w*|esp32\w*|device_\w+)', t, re.I)
    for cid in cids:
        if cid.lower() not in [x.lower() for x in VALID_DEVICES]:
            return {'intent':'','device_id':'','ambiguous':False,'rejected':True,
                    'reject_msg':f'⛔ 设备 "{cid}" 不在白名单中。仅支持：{", ".join(VALID_DEVICES)}。'}

    # 3. 歧义检测
    amb = ['那个','这个','东西','它','他','某个','随便','任意']
    if any(w in t for w in amb) and not fdev:
        return {'intent':'','device_id':'','ambiguous':True,
                'message':f'请问您要查的是什么设备的数据？目前支持：{", ".join(VALID_DEVICES)}。'}

    # 4. 意图分类
    qkw = ['查','查看','看','上次','最近','最新','数据','是什么','多少','看看','查询','上一条','记录','状态','显示','读取']
    ckw = ['采集','重新采集','测','测试','帮我测','收集','抓取','上报','发送','重新测','测一下','采一下','采','取样','捕获','capture']

    is_q = any(k in t for k in qkw)
    is_c = any(k in t for k in ckw)

    if is_c and not is_q:
        intent = 'tool_request_collection'
    elif is_q:
        intent = 'tool_query_latest'
    elif is_c:
        intent = 'tool_request_collection'
    elif fdev:
        intent = 'tool_query_latest'
    else:
        return {'intent':'','device_id':'','ambiguous':True,
                'message':f'抱歉，我没理解您的意图。请问要"查看最新数据"还是"重新采集"？支持：{", ".join(VALID_DEVICES)}。'}

    if not fdev:
        fdev = VALID_DEVICES[0]

    return {'intent':intent,'device_id':fdev,'ambiguous':False,'rejected':False}


def _llm_nlp_parse(text):
    """大模型 API 解析（备用路径）。"""
    try:
        resp = _openai_client.chat.completions.create(
            model='deepseek-chat',
            messages=[{'role':'system','content':SYSTEM_PROMPT},{'role':'user','content':text}],
            tools=NLP_TOOLS, tool_choice='auto', temperature=0.1, max_tokens=300
        )
        msg = resp.choices[0].message
        if msg.tool_calls:
            tc = msg.tool_calls[0]
            func_name = tc.function.name
            import json as _j
            args = _j.loads(tc.function.arguments) if tc.function.arguments else {}
            did = args.get('device_id','')
            if did not in VALID_DEVICES:
                return {'intent':'','device_id':'','ambiguous':False,'rejected':True,
                        'reject_msg':f'⛔ 设备 "{did}" 不在白名单中。'}
            return {'intent':func_name,'device_id':did,'ambiguous':False,'rejected':False}
        content = (msg.content or '').strip()
        if content.startswith('```'):
            content = re.sub(r'^```(?:json)?\s*','',content)
            content = re.sub(r'\s*```$','',content)
        try:
            import json as _j
            result = _j.loads(content)
        except Exception:
            result = {}
        if result.get('ambiguous'):
            return {'intent':'','device_id':'','ambiguous':True,
                    'message':result.get('message','请问您要查的是什么设备的数据？')}
        did = result.get('device_id','')
        intent = result.get('intent','')
        if did not in VALID_DEVICES:
            return {'intent':'','device_id':'','ambiguous':False,'rejected':True,
                    'reject_msg':f'⛔ 设备 "{did}" 不在白名单中。'}
        if intent not in ('tool_query_latest','tool_request_collection'):
            return {'intent':'','device_id':'','ambiguous':True,'message':'抱歉，我没理解您的意图。'}
        return {'intent':intent,'device_id':did,'ambiguous':False,'rejected':False}
    except Exception as e:
        log.warning('LLM API call failed: %s, falling back to local parser', e)
        return _local_nlp_parse(text)


@app.route('/api/cancel_nlp', methods=['POST'])
def cancel_nlp():
    """取消当前 NLP 任务。前端点击停止或语音说"取消"时调用。"""
    global active_task
    with task_lock:
        rid = active_task.get("request_id")
        log.info('Cancel NLP task: request_id=%s', rid)
        if rid:
            active_task["task_state"] = "cancelled"
            try:
                conn = get_db()
                conn.execute(
                    "UPDATE collection_requests SET status='CANCELLED' WHERE request_id=? AND status IN ('PENDING','RECEIVED')",
                    (rid,)
                )
                conn.commit()
                conn.close()
            except Exception:
                pass
    return jsonify({'success': True, 'reply': '⏹ 已取消，回到空闲状态'})


@app.route('/api/nlp', methods=['POST'])
def nlp_query():
    """自然语言查询入口（支持取消与结果隔离）。"""
    global active_task
    try:
        data = request.get_json()
    except Exception:
        return jsonify({'reply': '⚠️ 请以 JSON 格式发送请求。', 'success': False}), 400

    text = (data.get('text', '') or '').strip()
    if not text:
        return jsonify({'reply': '💬 请输入您的问题。', 'success': False})

    # ── 生成本次任务唯一 request_id ──
    task_request_id = str(uuid.uuid4())[:8] + '_' + str(int(time.time() * 1000))
    with task_lock:
        active_task["request_id"] = task_request_id
        active_task["task_state"] = "executing"
        active_task["start_time"] = time.time()

    def _build_resp(reply, success, tool_used, data=None, reason=None):
        """构建包含 task_state 的响应，实现结果隔离。"""
        with task_lock:
            current_rid = active_task.get("request_id")
            if current_rid == task_request_id and active_task.get("task_state") == "cancelled":
                active_task["request_id"] = None
                active_task["task_state"] = "idle"
                return jsonify({
                    'reply': '⏹ 任务已被用户取消',
                    'success': False, 'tool_used': tool_used,
                    'data': data,
                    'request_id': task_request_id, 'task_state': 'cancelled', 'reason': 'cancelled'
                })
            if current_rid == task_request_id:
                active_task["task_state"] = "completed"
                ts = "completed"
            else:
                ts = "stale"
        return jsonify({
            'reply': reply, 'success': success, 'tool_used': tool_used,
            'data': data, 'request_id': task_request_id, 'task_state': ts, 'reason': reason
        })

    # 解析
    if _OPENAI_AVAILABLE:
        result = _llm_nlp_parse(text)
    else:
        result = _local_nlp_parse(text)

    log.info('NLP parse: "%s" -> %s', text[:60], result)

    # 歧义
    if result.get('ambiguous'):
        return _build_resp('🤔 ' + result.get('message', '请问您要查的是什么设备的数据？'), True, None)
    # 拒绝
    if result.get('rejected'):
        return _build_resp(result.get('reject_msg', '请求被拒绝。'), False, None)

    intent = result['intent']
    device_id = result['device_id']

    # ── tool_query_latest ──
    if intent == 'tool_query_latest':
        conn = get_db()
        row = conn.execute(
            'SELECT device_id, ax, ay, az, device_time, server_time '
            'FROM accelerometer WHERE device_id=? ORDER BY id DESC LIMIT 1',
            (device_id,)
        ).fetchone()
        conn.close()
        if not row:
            return _build_resp(f'📭 设备 {device_id} 暂无数据。', True, 'tool_query_latest', None)
        return _build_resp(
            (f'📡 设备 {row["device_id"]} 最新数据：\n'
             f'　AX={row["ax"]:.2f}　AY={row["ay"]:.2f}　AZ={row["az"]:.2f}\n'
             f'　📅 设备时间：{row["device_time"]}\n'
             f'　⏱ 服务器时间：{row["server_time"]}'),
            True, 'tool_query_latest',
            {'device_id': row['device_id'], 'ax': row['ax'], 'ay': row['ay'],
             'az': row['az'], 'device_time': row['device_time'], 'server_time': row['server_time']}
        )

    # ── tool_request_collection ──
    if intent == 'tool_request_collection':
        request_id = _gen_request_id()
        now_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        expire_epoch = int(time.time()) + REQUEST_EXPIRE_S
        conn = get_db()
        c = conn.cursor()
        c.execute(
            'INSERT INTO collection_requests (request_id, device_id, status, created_at, expire_at) '
            'VALUES (?,?,?,?,?)',
            (request_id, device_id, 'PENDING', now_str, expire_epoch)
        )
        conn.commit()
        conn.close()
        log.info('NLP collection request: id=%s device=%s expire_at=%d',
                 request_id, device_id, expire_epoch)

        # ── 延迟注入（测试中途取消） ──
        if ENABLE_SLOW_INJECTION:
            log.info('⚠️ Slow injection ENABLED — sleeping 10 seconds')
            for i in range(20):
                with task_lock:
                    if (active_task.get("request_id") == task_request_id and
                            active_task.get("task_state") == "cancelled"):
                        return _cancel_collection(request_id, device_id, task_request_id)
                time.sleep(0.5)
            log.info('Slow injection finished')

        for _ in range(20):  # 10s
            time.sleep(0.5)

            # ── 每次轮询前检查是否被取消 ──
            with task_lock:
                if (active_task.get("request_id") == task_request_id and
                        active_task.get("task_state") == "cancelled"):
                    return _cancel_collection(request_id, device_id, task_request_id)

            conn = get_db()
            row = conn.execute(
                'SELECT * FROM collection_requests WHERE request_id=?', (request_id,)
            ).fetchone()
            conn.close()
            if row and row['status'] == 'COMPLETED':
                return _build_resp(
                    (f'✅ 采集成功！设备 {row["device_id"]} 已上报：\n'
                     f'　AX={row["ax"]:.2f}　AY={row["ay"]:.2f}　AZ={row["az"]:.2f}\n'
                     f'　📅 设备时间：{row["device_time"]}\n'
                     f'　🔖 request_id: {request_id}'),
                    True, 'tool_request_collection',
                    {'request_id': request_id, 'device_id': row['device_id'],
                     'ax': row['ax'], 'ay': row['ay'], 'az': row['az'],
                     'device_time': row['device_time'], 'status': 'COMPLETED'}
                )

        return _build_resp(
            (f'⏰ 设备无响应，采集失败。\n'
             f'　request_id={request_id}\n'
             f'　已等待 10 秒，设备 {device_id} 未上报新数据。请确认硬件在线。'),
            False, 'tool_request_collection',
            {'request_id': request_id, 'device_id': device_id, 'status': 'TIMEOUT'}
        )

    return _build_resp('🤷 未识别的操作。', False) , 400


def _cancel_collection(request_id, device_id, task_request_id):
    """取消采集任务并释放 active_task。"""
    global active_task
    try:
        conn2 = get_db()
        conn2.execute(
            "UPDATE collection_requests SET status='CANCELLED' "
            "WHERE request_id=? AND status IN ('PENDING','RECEIVED')",
            (request_id,)
        )
        conn2.commit()
        conn2.close()
    except Exception:
        pass
    with task_lock:
        active_task["request_id"] = None
        active_task["task_state"] = "idle"
    return jsonify({
        'reply': '⏹ 任务已被用户取消',
        'success': False, 'tool_used': 'tool_request_collection',
        'data': {'request_id': request_id, 'device_id': device_id, 'status': 'CANCELLED'},
        'request_id': task_request_id, 'task_state': 'cancelled', 'reason': 'cancelled'
    })


# ─── Main ──────────────────────────────────────────────────



# ====== Sensor History API (for frontend sensor table) ======

@app.route('/api/sensor_history')
def sensor_history():
    """Return sensor data history for the frontend data table."""
    count = request.args.get('count', 200, type=int)
    if count > 1000:
        count = 1000
    try:
        conn = get_db()
        rows = conn.execute(
            'SELECT id, device_id, ax, ay, az, device_time, server_time '
            'FROM accelerometer ORDER BY id DESC LIMIT ?',
            (count,)
        ).fetchall()
        conn.close()
        result = []
        for r in rows:
            result.append({
                'id': r['id'],
                'device_id': r['device_id'],
                'ax': r['ax'],
                'ay': r['ay'],
                'az': r['az'],
                'device_time': r['device_time'],
                'server_time': r['server_time']
            })
        result.reverse()
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        log.error('sensor_history error: %s', e)
        return jsonify({'success': False, 'data': [], 'error': str(e)})




# ====== Image History API (for frontend history tab) ======

@app.route('/api/image_history')
def image_history():
    """Return captured image history from DB."""
    import base64, os
    limit = request.args.get('limit', 50, type=int)
    if limit > 100:
        limit = 100
    try:
        conn = get_db()
        rows = conn.execute(
            'SELECT id, filename, source, created_at '
            'FROM captured_images ORDER BY id DESC LIMIT ?',
            (limit,)
        ).fetchall()
        conn.close()
        history = []
        for r in rows:
            fpath = os.path.join(os.path.dirname(__file__), 'static', 'precaptured_images', r['filename'])
            img_b64 = None
            if os.path.isfile(fpath):
                with open(fpath, 'rb') as f:
                    raw = f.read()
                img_b64 = base64.b64encode(raw).decode('utf-8')
                ext = os.path.splitext(fpath)[1].lower()
                mime_map = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.bmp': 'image/bmp'}
                mime = mime_map.get(ext, 'image/jpeg')
                img_b64 = f'data:{mime};base64,{img_b64}'
            history.append({
                'id': r['id'],
                'image': img_b64,
                'source': r['source'],
                'created_at': r['created_at']
            })
        return jsonify({'success': True, 'history': history})
    except Exception as e:
        log.error('image_history error: %s', e)
        return jsonify({'success': False, 'history': [], 'error': str(e)})


# ====== Week 7: Image Capture (Precaptured Only) ======

@app.route('/api/capture_image', methods=['POST'])
def api_capture_image():
    """
    Dual-channel endpoint:
      - ESP32 uploads binary JPEG (Content-Type: image/jpeg) → save to static/captured/
      - Browser calls (no body / JSON) → create pending capture request, poll for image, return base64
    """
    import base64, os, time
    from datetime import datetime
    log.info('>>> 收到拍照请求！')

    captured_dir = os.path.join(os.path.dirname(__file__), 'static', 'captured')
    os.makedirs(captured_dir, exist_ok=True)
    latest_path = os.path.join(captured_dir, 'latest.jpg')

    # ============== Channel 1: ESP32 JPEG upload ==============
    content_type = request.content_type or ''
    if 'image/jpeg' in content_type:
        raw = request.get_data()
        if not raw or len(raw) < 100:
            return jsonify({'success': False, 'error': 'empty or too small image data'}), 400

        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        fname = f'capture_{ts}.jpg'
        fpath = os.path.join(captured_dir, fname)
        with open(fpath, 'wb') as f:
            f.write(raw)
        # Also update latest.jpg for convenient access
        with open(latest_path, 'wb') as f:
            f.write(raw)

        # Update DB
        try:
            conn = get_db()
            conn.execute('INSERT INTO captured_images (filename, source, created_at) VALUES (?,?,?)',
                         (fname, 'esp32_camera', datetime.now().isoformat()))
            conn.commit()
            conn.close()
        except Exception:
            pass

        log.info('Image saved from ESP32: %s (%d bytes)', fname, len(raw))

        # 第10周：更新摄像头源状态
        update_source_state('camera', 'success', json.dumps({'filename': fname, 'bytes': len(raw)}),
                           receive_time=datetime.now().isoformat())

        return jsonify({'success': True, 'message': 'image saved', 'filename': fname})

    # ============== Channel 2: Browser call ==============
    # 2a. Check if a recent captured image already exists (< 30s old)
    if os.path.isfile(latest_path):
        age = time.time() - os.path.getmtime(latest_path)
        if age < 30:
            with open(latest_path, 'rb') as f:
                raw = f.read()
            img_b64 = base64.b64encode(raw).decode('utf-8')
            log.info('Capture: returning recent ESP32 image (age=%.1fs)', age)
            return jsonify({
                'success': True,
                'image': f'data:image/jpeg;base64,{img_b64}',
                'source': 'esp32_camera'
            })

    # 2b. No recent image → create a pending capture request for ESP32
    request_id = _gen_request_id()
    device_id = 'group01_esp32s3eye'
    now_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    expire_epoch = int(time.time()) + REQUEST_EXPIRE_S
    try:
        conn = get_db()
        conn.execute(
            'INSERT INTO collection_requests (request_id, device_id, status, created_at, action, expire_at) VALUES (?,?,?,?,?,?)',
            (request_id, device_id, 'PENDING', now_str, 'capture', expire_epoch)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log.error('Capture: failed to create pending request: %s', e)
        return jsonify({'success': False, 'error': 'db error: ' + str(e)}), 500

    log.info('Capture pending request created: id=%s', request_id)

    # 2c. Poll for up to 30s waiting for ESP32 to upload the image
    for attempt in range(60):
        time.sleep(0.5)
        if os.path.isfile(latest_path):
            age = time.time() - os.path.getmtime(latest_path)
            if age < 2.0:  # file was just created/modified
                with open(latest_path, 'rb') as f:
                    raw = f.read()
                img_b64 = base64.b64encode(raw).decode('utf-8')
                log.info('Capture: ESP32 image received after %.1fs (attempt %d)', age, attempt)
                return jsonify({
                    'success': True,
                    'image': f'data:image/jpeg;base64,{img_b64}',
                    'source': 'esp32_camera'
                })

    # 2d. Timeout — no image from ESP32
    log.warning('Capture timeout: no image from ESP32 after 30s (request_id=%s)', request_id)
    return jsonify({'success': False, 'error': 'no images', 'source': 'timeout'}), 404


# ═══════════════════════════════════════════════════════════
# Vision Inference Module（视觉推理模块）
# ═══════════════════════════════════════════════════════════

# 模拟推理开关——True 时返回模拟结果，前端必须显示橙色提示
ENABLE_MOCK_VISION = True

VISION_LABELS = [
    "环境正常", "人员走动", "物体移动", "光照变化",
    "异常闯入", "设备异常", "画面模糊"
]

def _mock_infer():
    """
    模拟视觉推理。
    约 30% 概率返回低分 (< 0.7) 以演示 uncertain 状态。
    标注 model_version: "MOCK-V1"，严禁冒充真实模型分数。
    """
    label = random.choice(VISION_LABELS)
    # 30% 低分概率 → uncertain 状态
    if random.random() < 0.3:
        score = round(random.uniform(0.30, 0.68), 4)
        status = "uncertain"
    else:
        score = round(random.uniform(0.72, 0.95), 4)
        status = "success"
    return {
        "label": label,
        "score": score,
        "status": status,
        "model_version": "MOCK-V1"
    }


@app.route('/api/infer_image', methods=['POST'])
def api_infer_image():
    """对最新采集的图片执行推理，返回标签、置信度、状态。"""
    data = request.get_json(silent=True) or {}
    image_id = data.get('image_id')
    log.info('收到推理请求，image_id=%s', image_id)

    # 与 api_capture_image 保持一致的路径：server/static/captured/latest.jpg
    captured_dir = os.path.join(os.path.dirname(__file__), 'static', 'captured')
    latest_path = os.path.join(captured_dir, 'latest.jpg')
    log.info('推理目标图片路径: %s (exists=%s)', latest_path, os.path.isfile(latest_path))

    if not os.path.isfile(latest_path):
        return jsonify({'success': False, 'error': 'no image available for inference'}), 404

    image_path = latest_path

    if ENABLE_MOCK_VISION:
        result = _mock_infer()
        log.info('Mock infer | label=%s score=%.4f status=%s', result['label'], result['score'], result['status'])
    else:
        # 扩展点：接入真实 AI 模型
        result = _mock_infer()
        log.info('Real model not available, using mock fallback')

    # 写入 vision_results 表
    try:
        conn = get_db()
        cursor = conn.execute(
            'INSERT INTO vision_results (image_path, model_label, model_score, model_version, status, created_at) VALUES (?,?,?,?,?,?)',
            (image_path, result['label'], result['score'], result['model_version'], result['status'], datetime.now().isoformat())
        )
        result_id = cursor.lastrowid
        conn.commit()
        conn.close()
        result['result_id'] = result_id
    except Exception as e:
        log.error('Failed to save vision result: %s', e)

    result['success'] = True
    result['image_path'] = image_path
    return jsonify(result)


@app.route('/api/record_user_action', methods=['POST'])
def api_record_user_action():
    """记录用户对 uncertain 推理的响应：retake 或 ignore，存入 vision_results"""
    data = request.get_json(silent=True) or {}
    result_id = data.get('result_id')
    action = data.get('action', '').strip()
    if not result_id or action not in ('retake', 'ignore'):
        return jsonify({'success': False, 'error': 'result_id and action (retake/ignore) required'}), 400
    try:
        conn = get_db()
        conn.execute(
            'UPDATE vision_results SET user_action=?, action_at=? WHERE id=?',
            (action, datetime.now().isoformat(), result_id)
        )
        conn.commit()
        conn.close()
        log.info('User action recorded | result_id=%s action=%s', result_id, action)
        # ── 第12周：写入偏好表 ──
        try:
            pconn = get_db()
            pkey = 'event_' + action + '_' + str(result_id)
            pver = _get_next_config_version()
            pconn.execute(
                'INSERT OR REPLACE INTO user_preferences (preference_key,preference_value,created_at,config_version) VALUES (?,?,?,?)',
                (pkey, action, datetime.now().isoformat(), pver))
            pconn.commit()
            pconn.close()
            log.info('Preference recorded: %s=%s ver=%d', pkey, action, pver)
        except Exception as pe:
            log.warning('Preference write failed: %s', pe)
        # ─────────────────────────────
        return jsonify({'success': True, 'action': action, 'result_id': result_id})
    except Exception as e:
        log.error('Failed to record user action: %s', e)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/correct_label', methods=['POST'])
def api_correct_label():
    """
    人工纠正：接收前端提交的 corrected_label，更新 vision_results 表。
    保存三方对应：image_path / model_label+model_score / human_corrected_label+corrected_at
    """
    data = request.get_json(silent=True) or {}
    result_id = data.get('result_id')
    corrected_label = data.get('corrected_label', '').strip()

    if not result_id or not corrected_label:
        return jsonify({'success': False, 'error': 'result_id and corrected_label are required'}), 400

    try:
        conn = get_db()
        conn.execute(
            'UPDATE vision_results SET human_corrected_label=?, corrected_at=? WHERE id=?',
            (corrected_label, datetime.now().isoformat(), result_id)
        )
        conn.commit()
        conn.close()
        log.info('Label corrected | result_id=%s corrected_label=%s', result_id, corrected_label)
        # ── 第12周：写入偏好表 ──
        try:
            pconn = get_db()
            pkey = 'label_correct_' + str(result_id)
            pver = _get_next_config_version()
            pconn.execute(
                'INSERT OR REPLACE INTO user_preferences (preference_key,preference_value,created_at,config_version) VALUES (?,?,?,?)',
                (pkey, corrected_label, datetime.now().isoformat(), pver))
            pconn.commit()
            pconn.close()
            log.info('Preference recorded: %s=%s ver=%d', pkey, corrected_label, pver)
        except Exception as pe:
            log.warning('Preference write failed: %s', pe)
        # ─────────────────────────────
        return jsonify({'success': True, 'message': 'label corrected', 'result_id': result_id})
    except Exception as e:
        log.error('Failed to correct label: %s', e)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/vision_history', methods=['GET'])
def api_vision_history():
    """返回最近的视觉推理历史记录（含人工纠正）。"""
    limit = request.args.get('limit', 20, type=int)
    try:
        conn = get_db()
        rows = conn.execute(
            'SELECT * FROM vision_results ORDER BY id DESC LIMIT ?', (limit,)
        ).fetchall()
        conn.close()
        history = []
        for row in rows:
            history.append({
                'id': row['id'],
                'image_path': row['image_path'],
                'model_label': row['model_label'],
                'model_score': row['model_score'],
                'model_version': row['model_version'],
                'status': row['status'],
                'human_corrected_label': row['human_corrected_label'],
                'corrected_at': row['corrected_at'],
                'created_at': row['created_at']
            })
        return jsonify({'success': True, 'history': history})
    except Exception as e:
        log.error('Failed to fetch vision history: %s', e)
        return jsonify({'success': False, 'error': str(e)}), 500


# ═══════════════════════════════════════════════════════════
# 第10周：多源状态追踪 API
# ═══════════════════════════════════════════════════════════

@app.route('/api/source_states', methods=['GET'])
def api_source_states():
    """返回所有数据源的最新状态、数据年龄、补传标记。"""
    try:
        conn = get_db()
        rows = conn.execute('SELECT * FROM source_states ORDER BY source_name').fetchall()
        conn.close()
        now = datetime.now()
        sources = []
        for row in rows:
            name = row['source_name']
            status = row['status'] or 'not_attempted'
            obs_str = row['last_observation_time']
            recv_str = row['last_receive_time']
            latest_val = row['latest_value']
            prev_val = row['previous_value']
            prev_obs = row['previous_observation_time']
            transmission_status = row['transmission_status'] or 'live'

            # Calculate ages
            age_seconds = None
            delay_seconds = None
            if obs_str:
                try:
                    # Try ISO format first, then fallback
                    obs_dt = datetime.fromisoformat(obs_str)
                except Exception:
                    obs_dt = datetime.strptime(obs_str, '%Y-%m-%d %H:%M:%S')
                age_seconds = (now - obs_dt).total_seconds()
            if obs_str and recv_str:
                try:
                    obs_dt = datetime.fromisoformat(obs_str)
                except Exception:
                    obs_dt = datetime.strptime(obs_str, '%Y-%m-%d %H:%M:%S')
                try:
                    recv_dt = datetime.fromisoformat(recv_str)
                except Exception:
                    recv_dt = datetime.strptime(recv_str, '%Y-%m-%d %H:%M:%S')
                delay_seconds = (recv_dt - obs_dt).total_seconds()

            # Check stale
            threshold = SOURCE_STALE_THRESHOLDS.get(name, 60)
            is_stale = age_seconds is not None and age_seconds > threshold
            if is_stale and status == 'success':
                status = 'stale'

            # Parse latest_value as JSON if possible
            val_parsed = latest_val
            if latest_val:
                try:
                    val_parsed = json.loads(latest_val)
                except Exception:
                    pass

            # Parse previous_value
            prev_parsed = None
            prev_age = None
            if prev_val:
                try:
                    prev_parsed = json.loads(prev_val)
                except Exception:
                    prev_parsed = prev_val
                if prev_obs:
                    try:
                        prev_dt = datetime.fromisoformat(prev_obs)
                    except Exception:
                        prev_dt = datetime.strptime(prev_obs, '%Y-%m-%d %H:%M:%S')
                    prev_age = (now - prev_dt).total_seconds()

            sources.append({
                'source_name': name,
                'status': status,
                'latest_value': val_parsed,
                'source_location': row['source_location'] or '',
                'age_seconds': round(age_seconds, 1) if age_seconds is not None else None,
                'delay_seconds': round(delay_seconds, 1) if delay_seconds is not None else None,
                'is_stale': is_stale,
                # Week14: is_delayed now derived from transmission_status, not raw delay
                'is_delayed': (transmission_status == 'recovered'),
                'transmission_status': transmission_status,
                'observation_time': obs_str,
                'previous_value': prev_parsed,
                'previous_age': round(prev_age, 1) if prev_age is not None else None,
            })

        return jsonify({'success': True, 'sources': sources})
    except Exception as e:
        log.error('api_source_states failed: %s', e)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/simulate_no_fix', methods=['POST'])
def api_simulate_no_fix():
    """模拟 GNSS no_fix：位置源标记为 failed，保留旧坐标。"""
    update_source_state('gps', 'failed', '无有效解，非故障',
                       observation_time=datetime.now().isoformat())
    return jsonify({'success': True, 'message': 'GPS set to no_fix'})


# ═══════════════════════════════════════════════════════════
# 第11周：上下文解释引擎 (Context Engine)
# ═══════════════════════════════════════════════════════════

RULES_VERSION = "v1.0"
MOVING_THRESHOLD = 0.5          # |accel_magnitude - 9.81| > 0.5 → 可能在移动
STALE_THRESHOLD_SECONDS = 60    # 源数据超过此时间视为过期


@app.route('/api/context', methods=['GET'])
def api_context():
    """三层结构：原始观测 → 派生状态 → 交互决策"""
    import math
    conn = get_db()
    rows = conn.execute('SELECT * FROM source_states ORDER BY source_name').fetchall()
    conn.close()
    now = datetime.now()

    # ── 第一层：原始观测 (raw_observations) ──
    raw = {}
    for r in rows:
        name = r['source_name']
        val = None
        if r['latest_value']:
            try:
                val = json.loads(r['latest_value'])
            except Exception:
                val = r['latest_value']
        obs_str = r['last_observation_time']
        obs_dt = None
        if obs_str:
            try:
                obs_dt = datetime.fromisoformat(obs_str)
            except Exception:
                try:
                    obs_dt = datetime.strptime(obs_str, '%Y-%m-%d %H:%M:%S')
                except Exception:
                    pass
        age = (now - obs_dt).total_seconds() if obs_dt else None
        raw[name] = {
            'status': r['status'] or 'not_attempted',
            'value': val,
            'age_seconds': round(age, 1) if age is not None else None,
            'source_location': r['source_location'] or '',
        }

    # ── 第二层：派生状态 (derived_states) ──
    derived = {}
    sensor = raw.get('sensor', {})
    sensor_val = sensor.get('value') or {}
    ax = float(sensor_val.get('ax', 0)) if isinstance(sensor_val, dict) else 0.0
    ay = float(sensor_val.get('ay', 0)) if isinstance(sensor_val, dict) else 0.0
    az = float(sensor_val.get('az', 0)) if isinstance(sensor_val, dict) else 0.0
    mag = math.sqrt(ax * ax + ay * ay + az * az)
    derived['is_moving'] = '可能在移动' if abs(mag - 9.81) > MOVING_THRESHOLD else '静止'
    derived['accel_magnitude'] = round(mag, 3)
    gps = raw.get('gps', {})
    derived['position_trustworthy'] = (
        gps.get('status') == 'success' and
        gps.get('age_seconds') is not None and
        gps.get('age_seconds') < STALE_THRESHOLD_SECONDS
    )
    cam = raw.get('camera', {})
    derived['camera_usable'] = (
        cam.get('status') == 'success' and
        cam.get('age_seconds') is not None and
        cam.get('age_seconds') < STALE_THRESHOLD_SECONDS
    )

    # ── 第三层：交互决策 (interaction) ──
    def t_fmt(dt_obj):
        return dt_obj.strftime('%H:%M:%S') if dt_obj else ''

    known_facts = []
    uncertain_items = []

    # -- 加速度已知事实（规则推断）--
    sensor_age = sensor.get('age_seconds')
    if sensor_age is not None:
        fact_text = '当前可能静止' if derived['is_moving'] == '静止' else '当前可能在移动'
        known_facts.append({'fact': fact_text, 'source': '规则推断', 'observed_at': t_fmt(now)})

    # -- 网络已知事实 --
    net = raw.get('network', {})
    net_age = net.get('age_seconds')
    if net.get('status') == 'success' and net_age is not None and net_age < STALE_THRESHOLD_SECONDS:
        known_facts.append({'fact': '网络连接正常', 'source': '网络连接', 'observed_at': t_fmt(now)})

    # -- 位置处理 --
    gps_val = gps.get('value') or {}
    gps_age = gps.get('age_seconds')
    if derived.get('position_trustworthy'):
        lat = gps_val.get('lat', '?') if isinstance(gps_val, dict) else '?'
        lng = gps_val.get('lng', '?') if isinstance(gps_val, dict) else '?'
        known_facts.append({
            'fact': f'当前位置 lat={lat} lng={lng}',
            'source': f'位置GPS [{gps.get("source_location", "")}]',
            'observed_at': t_fmt(now),
        })
    elif gps_val and isinstance(gps_val, dict) and (gps_val.get('lat') is not None) and gps_age is not None:
        lat = gps_val.get('lat', '?')
        lng = gps_val.get('lng', '?')
        min_ago = max(1, int(gps_age / 60))
        known_facts.append({
            'fact': f'上次报告位置是 lat={lat} lng={lng}（{min_ago}分钟前）',
            'source': f'位置GPS [{gps.get("source_location", "")}]',
            'observed_at': t_fmt(now),
        })
        uncertain_items.append({
            'item': '当前位置',
            'reason': f'位置源上次报告在{min_ago}分钟前，已过期',
        })
    elif gps.get('status') == 'failed':
        uncertain_items.append({'item': '当前位置', 'reason': 'GPS 无有效解，非故障'})
    else:
        uncertain_items.append({'item': '当前位置', 'reason': '位置不可用'})

    # -- 摄像头处理（遮挡时绝不出危险/紧急）--
    cam_val = cam.get('value') or {}
    if derived.get('camera_usable'):
        fname = cam_val.get('filename', 'unknown') if isinstance(cam_val, dict) else 'unknown'
        known_facts.append({'fact': f'摄像头可用，最后采集 {fname}', 'source': '摄像头', 'observed_at': t_fmt(now)})
    elif cam.get('status') == 'not_attempted':
        uncertain_items.append({'item': '画面内容', 'reason': '摄像头未启动'})
    else:
        uncertain_items.append({'item': '画面内容', 'reason': '画面不可用'})

    # -- 追问 --
    question = None
    if uncertain_items:
        items = [u['item'] for u in uncertain_items]
        question = f'需要确认：{"，".join(items)}。需要我重新采集吗？'

    return jsonify({
        'success': True,
        'raw_observations': raw,
        'derived_states': derived,
        'interaction': {
            'known_facts': known_facts,
            'uncertain_items': uncertain_items,
            'question': question,
            'rule_version': RULES_VERSION,
        },
    })


# ═══════════════════════════════════════════════════════════
# 第12周：用户偏好管理 (User Preferences)
# ═══════════════════════════════════════════════════════════

@app.route('/api/check_preference', methods=['GET'])
def api_check_preference():
    """检查某个 preference_key 是否存在且未过期。返回 {preference_exists, preference_value}."""
    key = request.args.get('key', '').strip()
    if not key:
        return jsonify({'preference_exists': False, 'error': 'missing key'})
    try:
        conn = get_db()
        row = conn.execute(
            'SELECT preference_value, expires_at FROM user_preferences WHERE preference_key=?',
            (key,)
        ).fetchone()
        conn.close()
        if row:
            expires = row['expires_at']
            now = datetime.now().isoformat()
            if expires is None or expires > now:
                return jsonify({'preference_exists': True, 'preference_value': row['preference_value']})
        return jsonify({'preference_exists': False})
    except Exception as e:
        return jsonify({'preference_exists': False, 'error': str(e)}), 500


@app.route('/api/preference', methods=['POST'])
def api_preference():
    """写入偏好：{key, value, duration?}。duration 秒数或 null=永久."""
    data = request.get_json(silent=True) or {}
    key = (data.get('key') or '').strip()
    value = (data.get('value') or 'ignore').strip()
    duration = data.get('duration')  # None = 永久, 数字 = 秒数
    if not key:
        return jsonify({'success': False, 'error': 'key required'}), 400
    try:
        now = datetime.now().isoformat()
        expires_at = None
        if duration is not None:
            try:
                secs = int(duration)
                from datetime import timedelta
                expires_at = (datetime.now() + timedelta(seconds=secs)).isoformat()
            except Exception:
                pass
        conn = get_db()
        ver = _get_next_config_version()
        conn.execute(
            'INSERT OR REPLACE INTO user_preferences (preference_key,preference_value,created_at,expires_at,config_version) VALUES (?,?,?,?,?)',
            (key, value, now, expires_at, ver))
        conn.commit()
        conn.close()
        log.info('Preference set: %s=%s expires=%s ver=%d', key, value, expires_at, ver)
        return jsonify({'success': True, 'key': key, 'value': value, 'config_version': ver})
    except Exception as e:
        log.error('Failed to set preference: %s', e)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/preferences', methods=['GET'])
def api_preferences():
    """返回所有当前偏好及版本号."""
    try:
        conn = get_db()
        rows = conn.execute(
            'SELECT preference_key,preference_value,created_at,expires_at,config_version FROM user_preferences ORDER BY id DESC'
        ).fetchall()
        conn.close()
        prefs = [{'key': r['preference_key'], 'value': r['preference_value'],
                  'created_at': r['created_at'], 'expires_at': r['expires_at'],
                  'config_version': r['config_version']} for r in rows]
        ver = prefs[0]['config_version'] if prefs else 1
        return jsonify({'success': True, 'preferences': prefs, 'config_version': ver})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/preferences/reset', methods=['POST'])
def api_preferences_reset():
    """一键恢复默认：删除所有偏好，config_version+1."""
    try:
        conn = get_db()
        old_ver = conn.execute('SELECT COALESCE(MAX(config_version),0) FROM user_preferences').fetchone()[0]
        conn.execute('DELETE FROM user_preferences')
        new_ver = old_ver + 1
        conn.execute(
            'INSERT INTO user_preferences (preference_key,preference_value,created_at,config_version) VALUES (?,?,?,?)',
            ('_RESET_', 'reset', datetime.now().isoformat(), new_ver))
        conn.commit()
        conn.close()
        log.info('Preferences reset: old_ver=%d new_ver=%d', old_ver, new_ver)
        return jsonify({'success': True, 'config_version': new_ver, 'message': '已恢复默认'})
    except Exception as e:
        log.error('Failed to reset preferences: %s', e)
        return jsonify({'success': False, 'error': str(e)}), 500


# ═══════════════════════════════════════════════════════════
# 第13周：能力注册表 & 本地推理 & 云回退
# ═══════════════════════════════════════════════════════════

# ─── 离线检测 ───────────────────────────────────────────────
OFFLINE_MODE = False
OFFLINE_REASON = ""  # "no_api_key" / "network_unreachable" / ""
ENABLE_CLOUD_INFER = os.environ.get('ENABLE_CLOUD_INFER', 'true').strip().lower() == 'true'

def check_offline_status():
    """仅检查配置（不 ping 外网），外网可达性由实际 API 调用失败来判定。"""
    global OFFLINE_MODE, OFFLINE_REASON
    if not ENABLE_CLOUD_INFER:
        OFFLINE_MODE = True
        OFFLINE_REASON = "no_api_key"
        log.info('Offline mode: ENABLE_CLOUD_INFER=False — using local inference only')
        return OFFLINE_MODE
    if not _OPENAI_AVAILABLE:
        OFFLINE_MODE = True
        OFFLINE_REASON = "no_api_key"
        log.info('Offline mode: API key not configured — using local inference only')
        return OFFLINE_MODE
    # 曾经因网络不通进入离线，但尚未重试成功 → 保持离线标志，等 api_infer() 中实际调用成功来恢复
    return OFFLINE_MODE

# 启动时检测一次（仅检查配置）
check_offline_status()

# ─── 能力注册表 ──────────────────────────────────────────────
capabilities = [
    {
        "name": "传感器采集",
        "location": "device",
        "offline_available": True,
        "status": "available",
        "note": "ESP32-S3-EYE QMA6100P @ COM4"
    },
    {
        "name": "视觉推理",
        "location": "near_edge",
        "offline_available": True,
        "status": "available",
        "note": "近端边缘规则推理 + 设备端加速度规则推理已接入，目标设备视觉模型验收待补"
    },
    {
        "name": "设备端加速度规则推理",
        "location": "device",
        "offline_available": True,
        "status": "available",
        "note": "ESP32-S3-EYE QMA6100P 直接计算"
    },
    {
        "name": "离线缓存补传",
        "location": "device",
        "offline_available": True,
        "status": "available",
        "note": "ESP32-S3-EYE 断网时缓存≤20条，恢复后按采集顺序补传"
    },
    {
        "name": "NLP意图解析",
        "location": "near_edge",
        "offline_available": True,
        "status": "available",
        "note": "本地规则引擎"
    },
    {
        "name": "语音播报",
        "location": "near_edge",
        "offline_available": True,
        "status": "available",
        "note": "Web Speech API"
    },
    {
        "name": "云端大模型推理",
        "location": "cloud",
        "offline_available": False,
        "status": "fallback" if OFFLINE_MODE else "available",
        "note": "需外网，未配置时回退本地"
    }
]

@app.route('/api/capabilities', methods=['GET'])
def api_capabilities():
    for cap in capabilities:
        if cap["name"] == "云端大模型推理":
            cap["status"] = "fallback" if OFFLINE_MODE else "available"
    return jsonify({
        "success": True,
        "offline_mode": OFFLINE_MODE,
        "capabilities": capabilities,
        "runtime_locations": [
            {"name": "设备端", "detail": "ESP32-S3-EYE @ COM4", "icon": "📟"},
            {"name": "近端边缘", "detail": "Flask @ 10.1.41.43:5000", "icon": "🖥️"},
            {"name": "云端", "detail": "在线模型（若配置）" if not OFFLINE_MODE else "不可用", "icon": "☁️"}
        ]
    })


@app.route('/api/local_infer', methods=['POST'])
def api_local_infer():
    """读取 source_states 表做规则推理，不传图像。"""
    try:
        conn = get_db()
        rows = conn.execute(
            'SELECT source_name, status, last_observation_time, latest_value FROM source_states'
        ).fetchall()
        conn.close()
        now = datetime.now()
        camera_age = None
        camera_status = None
        accelerometer_value = None
        for row in rows:
            name = row['source_name']
            status = row['status'] or 'not_attempted'
            obs_str = row['last_observation_time']
            latest_val = row['latest_value']
            if name == 'camera':
                camera_status = status
                if obs_str:
                    try:
                        obs_dt = datetime.fromisoformat(obs_str)
                    except Exception:
                        obs_dt = datetime.strptime(obs_str, '%Y-%m-%d %H:%M:%S')
                    camera_age = (now - obs_dt).total_seconds()
            if name == 'sensor' and latest_val:
                try:
                    accelerometer_value = json.loads(latest_val)
                except Exception:
                    pass
        if camera_status in (None, 'not_attempted', 'failed') or \
           (camera_age is not None and camera_age > 60):
            return jsonify({
                "success": True, "label": "画面不可用", "score": 0.0,
                "status": "uncertain", "source": "local_near_edge",
                "location_note": "近端边缘验证，目标设备验收待补",
                "detail": "摄像头数据过期或不可用"
            })
        if accelerometer_value and isinstance(accelerometer_value, dict):
            ax = float(accelerometer_value.get('ax', 0))
            ay = float(accelerometer_value.get('ay', 0))
            az = float(accelerometer_value.get('az', 0))
            mag = math.sqrt(ax*ax + ay*ay + az*az)
            if abs(mag - 9.81) > 2.0:
                return jsonify({
                    "success": True, "label": "可能在移动",
                    "score": round(1.0 - min(abs(mag - 9.81) / 20.0, 1.0), 4),
                    "status": "success", "source": "local_near_edge",
                    "location_note": "近端边缘验证，目标设备验收待补",
                    "detail": "加速度模长={:.2f}".format(mag)
                })
        return jsonify({
            "success": True, "label": "环境正常", "score": 0.85,
            "status": "success", "source": "local_near_edge",
            "location_note": "近端边缘验证，目标设备验收待补",
            "detail": "传感器与摄像头状态正常"
        })
    except Exception as e:
        log.error('local_infer failed: %s', e)
        return jsonify({
            "success": False, "error": str(e), "source": "local_near_edge",
            "label": "推理失败", "status": "uncertain"
        }), 500


@app.route('/api/infer', methods=['POST'])
def api_infer():
    """云优先+本地回退推理。不预检外网，仅在真实调用失败时标记离线；成功时自动恢复。"""
    global OFFLINE_MODE, OFFLINE_REASON
    if not _OPENAI_AVAILABLE:
        OFFLINE_REASON = "no_api_key"
        log.info('API key not configured — using local inference only')
        return api_local_infer()
    # 有 API Key：始终尝试云调用（即使上次失败），成功则自动恢复
    try:
        import base64 as _b64
        latest_path = os.path.join(os.path.dirname(__file__), 'static', 'captured', 'latest.jpg')
        if os.path.isfile(latest_path):
            with open(latest_path, 'rb') as f:
                img_b64 = _b64.b64encode(f.read()).decode('utf-8')
            resp = _openai_client.chat.completions.create(
                model="deepseek-chat",
                messages=[{
                    "role": "system",
                    "content": "你是视觉推理助手。用中文简短描述（10字以内），返回JSON: {\"label\":\"...\",\"score\":0.XX}"
                }, {"role": "user", "content": "描述这张图片内容"}],
                max_tokens=80, temperature=0.3
            )
            raw = resp.choices[0].message.content.strip()
            log.info('Cloud infer raw: %s', raw)
            label = "环境正常"
            score = 0.85
            try:
                parsed = json.loads(raw)
                label = parsed.get('label', label)
                score = float(parsed.get('score', score))
            except Exception:
                import re as _re
                m = _re.search(r'["\']label["\']\s*:\s*["\']([^"\']+)', raw)
                if m: label = m.group(1)
            # 云调用成功 → 恢复在线状态
            OFFLINE_MODE = False
            OFFLINE_REASON = ""
            return jsonify({
                "success": True, "label": label, "score": round(score, 4),
                "status": "success" if score >= 0.6 else "uncertain",
                "source": "cloud", "location_note": "云端大模型推理（DeepSeek）",
                "model_version": "deepseek-chat"
            })
    except Exception as e:
        log.warning('Cloud inference failed, fallback to local: %s', e)
        OFFLINE_MODE = True
        OFFLINE_REASON = "network_unreachable"
    log.info('Using local inference (near_edge)')
    return api_local_infer()


@app.route('/api/offline_status', methods=['GET'])
def api_offline_status():
    # 不调 check_offline_status，直接读全局变量
    banner = ""
    if OFFLINE_MODE:
        if OFFLINE_REASON in ("no_api_key", ""):
            banner = "云端大模型不可用：已切换至本地安全推理"
        else:
            banner = "网络离线：云端大模型不可用，已切换至本地安全推理"
    return jsonify({"offline_mode": OFFLINE_MODE, "cloud_available": not OFFLINE_MODE, "banner_text": banner})


@app.route('/api/vps_status', methods=['GET'])
def api_vps_status():
    """VPS 连接状态（前端顶部提示栏用，10s 缓存，避免频繁登录）。"""
    now = time.time()
    if _vps_status_cache['data'] is not None and now - _vps_status_cache['ts'] < 10:
        return jsonify(_vps_status_cache['data'])
    configured = _vps_configured()
    token = vps_login() if configured else None
    connected = bool(token)
    data = {
        'success': True,
        'configured': configured,
        'connected': connected,
        'base_url': VPS_BASE_URL,
        'device_id': VPS_DEVICE_ID,
        'channel': VPS_CHANNEL,
        'async_mode': VPS_ASYNC,
        'token_masked': _vps_mask(_vps['token']),
        'sent': _vps['sent'],
        'failed': _vps['failed'],
        'last_status': _vps['last_status'],
        'last_ok_at': _vps['last_ok_at'],
        'last_error': '' if connected else (_vps['last_error'] or '未连接'),
        'checked_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    _vps_status_cache['ts'] = time.time()
    _vps_status_cache['data'] = data
    return jsonify(data)


@app.route('/api/vps_history', methods=['GET'])
def api_vps_history():
    """代理 VPS 的 GET /api/data?limit=50，把云端记录拉回给前端展示。"""
    try:
        limit = int(request.args.get('limit', 50))
    except (TypeError, ValueError):
        limit = 50
    records, err = vps_fetch_history(limit)
    if err:
        log.error('[VPS] 拉取云端记录失败: %s', err)
        return jsonify({'success': False, 'source': 'vps', 'error': err,
                        'base_url': VPS_BASE_URL, 'count': 0, 'records': []}), 502
    log.info('[VPS] 云端记录拉取成功 count=%d', len(records))
    return jsonify({'success': True, 'source': 'vps', 'base_url': VPS_BASE_URL,
                    'device_id': VPS_DEVICE_ID, 'channel': VPS_CHANNEL,
                    'count': len(records), 'records': records,
                    'fetched_at': time.strftime('%Y-%m-%d %H:%M:%S')})

if __name__ == '__main__':
    init_db()
    init_vision_db()
    init_source_states_db()
    init_user_preferences_db()
    log.info('Starting sensor dashboard on http://0.0.0.0:5000')
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
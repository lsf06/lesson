from flask import Flask, request, jsonify, render_template
import sqlite3
import time
import os
import logging
import random
import re
import threading
import uuid
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
    conn.commit()
    conn.close()
    log.info('Database initialized: %s', DB_PATH)

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
    conn.commit()
    conn.close()
    log.info('Vision database initialized')

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
        '''SELECT request_id, device_id, created_at, action FROM collection_requests
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

    # Determine action value (handle missing column gracefully)
    try:
        act_val = row['action'] if row['action'] else 'data'
    except (KeyError, IndexError):
        act_val = 'data'

    log.info('Pending request delivered: id=%s device=%s action=%s', request_id, device_id, act_val)
    return jsonify({
        'has_request': True,
        'request_id': request_id,
        'action': act_val
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
        conn = get_db()
        c = conn.cursor()
        c.execute(
            'INSERT INTO collection_requests (request_id, device_id, status, created_at) '
            'VALUES (?,?,?,?)',
            (request_id, device_id, 'PENDING', now_str)
        )
        conn.commit()
        conn.close()
        log.info('NLP collection request: id=%s device=%s', request_id, device_id)

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
            "UPDATE collection_requests SET status='CANCELLED' WHERE request_id=?",
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
    try:
        conn = get_db()
        conn.execute(
            'INSERT INTO collection_requests (request_id, device_id, status, created_at, action) VALUES (?,?,?,?,?)',
            (request_id, device_id, 'PENDING', now_str, 'capture')
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


if __name__ == '__main__':
    init_db()
    init_vision_db()
    log.info('Starting sensor dashboard on http://0.0.0.0:5000')
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)

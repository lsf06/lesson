import os, sys
os.chdir("d:\\lesson\\xiaolin\\lesson-main (1)\\lesson-main\\week7_image_capture\\server")
with open("app.py", encoding="utf-8") as f:
    data = f.read()

# Fix 1: Change path
old = "precaptured_dir = os.path.join(os.path.dirname(__file__), 'precaptured')"
new = "precaptured_dir = os.path.join(os.path.dirname(__file__), 'static', 'precaptured_images')"
if old in data:
    data = data.replace(old, new, 1)
    print("Fix 1: precaptured_dir path -> static/precaptured_images")
else:
    # Check what exists
    import re
    for m in re.finditer(r"precaptured_dir\s*=", data):
        print(f"  Found: {repr(data[m.start():m.start()+150])}")

# Fix 2: Insert sensor_history BEFORE Week 7 section
wk7_marker = "# ====== Week 7: Image Capture (Precaptured Only) ======"
idx = data.find(wk7_marker)
endpoint1 = '''

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


'''
data = data[:idx] + endpoint1 + data[idx:]
print("Fix 2: /api/sensor_history inserted")

# Fix 3: Insert image_history after sensor_history (before Week 7)
idx2 = data.find(wk7_marker)  # Re-find since data shifted
endpoint2 = '''

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


'''
data = data[:idx2] + endpoint2 + data[idx2:]
print("Fix 3: /api/image_history inserted")

with open("app.py", "w", encoding="utf-8") as f:
    f.write(data)
print("All 3 fixes written!")

# Validate syntax
import ast
ast.parse(open("app.py", encoding="utf-8").read())
print("Syntax OK!")
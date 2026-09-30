import urllib.request, json, time

BASE = "http://localhost:5000"
OUT = r"d:\lesson\xiaolin\lesson-main (1)\lesson-main\_api_result.txt"

def log(msg):
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(msg + "\n")
    print(msg)

def api(url, data=None, method="GET"):
    try:
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, 
               headers={"Content-Type":"application/json"} if data else {}, method=method)
        resp = urllib.request.urlopen(req, timeout=5)
        return resp.read().decode()
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}: {e.read().decode()}"
    except Exception as e:
        return f"ERR: {e}"

# Clear output file
with open(OUT, "w") as f:
    f.write(f"=== Test started at {time.strftime('%H:%M:%S')} ===\n")

# 1. Create collection request
log("1. Creating collection request...")
r = api(f"{BASE}/api/request_collection", {"device_id": "group01_esp32s3eye"}, "POST")
log(r)
data = json.loads(r) if "{" in r else {}
req_id = data.get("request_id", "")

# 2. Wait for ESP32 to pick up
log(f"\n2. Waiting 12s for request_id={req_id}...")
time.sleep(12)

# 3. Check status
log(f"\n3. Checking status for {req_id}...")
r = api(f"{BASE}/api/request_status/{req_id}")
log(r)

# 4. Check latest
log("\n4. Latest data...")
r = api(f"{BASE}/api/latest")
log(r[:500])

log("\n=== DONE ===")
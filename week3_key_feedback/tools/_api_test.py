import urllib.request, json, time, sys

BASE = "http://localhost:5000"

def api_call(url, data=None, method="GET"):
    headers = {"Content-Type": "application/json"} if data else {}
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        return resp.read().decode()
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}: {e.read().decode()}"
    except Exception as e:
        return f"ERR: {e}"

print("=== 1. Create collection request ===")
resp = api_call(f"{BASE}/api/request_collection", {"device_id": "group01_esp32s3eye"}, "POST")
print(resp)
data = json.loads(resp)
req_id = data.get("request_id", "unknown")
print(f"Request ID: {req_id}")

print("\n=== 2. Wait for ESP32 to pick it up (10s) ===")
time.sleep(10)

print(f"\n=== 3. Check request status for {req_id} ===")
resp = api_call(f"{BASE}/api/request_status/{req_id}")
print(resp)

print("\n=== 4. Check latest data ===")
resp = api_call(f"{BASE}/api/latest")
print(resp[:500])

print("\n=== 5. Check pending (should be empty) ===")
resp = api_call(f"{BASE}/api/pending_request?device_id=group01_esp32s3eye")
print(resp)

print("\nDone.")
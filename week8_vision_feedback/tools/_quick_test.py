import urllib.request, json

# Trigger collection
data = json.dumps({"request_id": "test_001", "device_id": "group01_esp32s3eye", "duration": 5, "interval": 1}).encode()
req = urllib.request.Request("http://localhost:5000/api/create_collection_request", data=data, headers={"Content-Type": "application/json"}, method="POST")
try:
    resp = urllib.request.urlopen(req, timeout=5)
    print("COLLECT:", resp.read().decode()[:200])
except Exception as e:
    print("COLLECT ERR:", e)

# Check status
try:
    resp = urllib.request.urlopen("http://localhost:5000/api/status", timeout=5)
    print("STATUS:", resp.read().decode()[:500])
except Exception as e:
    print("STATUS ERR:", e)
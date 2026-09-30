import serial, time, requests, sys

# 1. Trigger a collection request
print("Triggering collection...")
try:
    r = requests.post('http://localhost:5000/api/collect', 
                      json={'device_id': 'group01_esp32s3eye', 'duration': 5, 'interval': 1},
                      timeout=5)
    print(f"Collection response: {r.status_code} {r.text}")
except Exception as e:
    print(f"Collection trigger failed: {e}")

# 2. Monitor serial for 30 seconds
print("\n=== Serial Monitor ===")
try:
    ser = serial.Serial('COM4', 115200, timeout=1)
    start = time.time()
    while time.time() - start < 30:
        line = ser.readline()
        if line:
            decoded = line.decode('utf-8', errors='replace').rstrip()
            print(decoded)
    ser.close()
except Exception as e:
    print(f"Serial error: {e}")

# 3. Check latest data
print("\n=== Latest Data ===")
try:
    r = requests.get('http://localhost:5000/api/latest', timeout=5)
    print(f"Status: {r.status_code}")
    print(r.text[:500])
except Exception as e:
    print(f"API error: {e}")

print("\nDone.")
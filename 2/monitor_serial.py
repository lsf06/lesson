import serial
import time
import sys
import os

PORT = 'COM5'
BAUD = 115200
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'serial_log.txt')

# Wait for port to become available
for attempt in range(10):
    try:
        s = serial.Serial(PORT, BAUD, timeout=1)
        break
    except serial.SerialException:
        print(f'Waiting for {PORT}... (attempt {attempt+1})')
        time.sleep(1)
else:
    print(f'Failed to open {PORT}')
    sys.exit(1)

print(f'Monitoring {PORT} at {BAUD} baud...')
sys.stdout.flush()

with open(LOG_PATH, 'w', encoding='utf-8', errors='replace') as f:
    start = time.time()
    for i in range(120):
        try:
            line = s.readline().decode('utf-8', errors='replace').strip()
        except Exception as e:
            line = f'[decode error: {e}]'
        elapsed = time.time() - start
        output = f'{elapsed:.1f}s | {line}'
        if line:
            print(output)
            f.write(output + '\n')
            f.flush()
        sys.stdout.flush()

s.close()
print('Capture complete.')
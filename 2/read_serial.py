import serial
import time

ser = serial.Serial('COM5', 115200, timeout=1)
print(f"Connected to {ser.name} at {ser.baudrate} baud")

with open('e:/study/lsf/daima/ganzhi/zhou/serial_log.txt', 'w', encoding='utf-8') as f:
    start = time.time()
    while time.time() - start < 15:
        try:
            line = ser.readline().decode('utf-8', errors='replace').strip()
            if line:
                print(line, flush=True)
                f.write(line + '\n')
                f.flush()
        except Exception as e:
            print(f"Error: {e}")
            break

ser.close()
print("Done")
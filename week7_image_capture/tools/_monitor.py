import serial
import time

ser = serial.Serial('COM4', 115200, timeout=1)
print(f"Connected to {ser.name} at {ser.baudrate}")
with open('_serial_live.txt', 'a', encoding='utf-8') as f:
    f.write(f"\n=== Serial monitor started at {time.strftime('%H:%M:%S')} ===\n")
    try:
        while True:
            line = ser.readline()
            if line:
                decoded = line.decode('utf-8', errors='replace').rstrip()
                print(decoded, flush=True)
                f.write(decoded + '\n')
                f.flush()
    except KeyboardInterrupt:
        ser.close()
import serial, time
ser = serial.Serial('COM4', 115200, timeout=1)
started = time.time()
with open('_serial_sample.txt', 'w', encoding='utf-8') as f:
    f.write(f"=== Serial monitor started at {time.strftime('%H:%M:%S')} ===\n")
    while time.time() - started < 45:
        line = ser.readline()
        if line:
            decoded = line.decode('utf-8', errors='replace').rstrip()
            f.write(decoded + '\n')
            f.flush()
    f.write(f"\n=== Serial monitor stopped at {time.strftime('%H:%M:%S')} ===\n")
ser.close()
"""Build, flash, and verify ESP32 firmware with hidden SSID fix."""
import subprocess, sys, os, time, json, urllib.request

WORKDIR = r"d:\lesson\xiaolin\lesson-main (1)\lesson-main\esp32_firmware"
IDF_PATH = r"D:\lesson\Download\esp-idf\Espressif\frameworks\esp-idf-v5.4.4"
PYTHON = r"D:\lesson\Download\esp-idf\Espressif\python_env\idf5.4_py3.10_env\Scripts\python.exe"
ESPTOOL = os.path.join(IDF_PATH, "components", "esptool_py", "esptool", "esptool.py")
BUILD_DIR = os.path.join(WORKDIR, "build")
BIN = os.path.join(BUILD_DIR, "qma6100_wifi_upload.bin")
BOOT = os.path.join(BUILD_DIR, "bootloader", "bootloader.bin")
PART = os.path.join(BUILD_DIR, "partition_table", "partition-table.bin")
COM = "COM4"

os.chdir(WORKDIR)

env = os.environ.copy()
env["IDF_PATH"] = IDF_PATH
env["PATH"] = (
    os.path.join(IDF_PATH, "tools", "xtensa-esp-elf") + os.pathsep +
    r"D:\lesson\Download\esp-idf\Espressif\tools\cmake\3.30.2\bin" + os.pathsep +
    r"D:\lesson\Download\esp-idf\Espressif\tools\ninja\1.12.1" + os.pathsep +
    env.get("PATH", "")
)

def run(cmd, **kw):
    print(f"\n=== RUN: {' '.join(cmd)[:120]} ===")
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, **kw)
    tail = r.stdout[-2000:] if len(r.stdout) > 2000 else r.stdout
    err_tail = r.stderr[-1000:] if len(r.stderr) > 1000 else r.stderr
    print(f"STDOUT: {tail}")
    if r.stderr:
        print(f"STDERR: {err_tail}")
    print(f"EXIT: {r.returncode}")
    return r

# Step 1: Build (idf.py app = incremental)
print("\n\n======== STEP 1: BUILD ========")
idf_py = os.path.join(IDF_PATH, "tools", "idf.py")
r = run([PYTHON, idf_py, "app"], cwd=WORKDIR)
if r.returncode != 0:
    print("BUILD FAILED - falling back to full build")
    r = run([PYTHON, idf_py, "build"], cwd=WORKDIR)
    if r.returncode != 0:
        print("FATAL: Build failed")
        sys.exit(1)

if not os.path.exists(BIN):
    print(f"FATAL: No binary at {BIN}")
    sys.exit(1)

mtime = os.path.getmtime(BIN)
print(f"BINARY: {time.ctime(mtime)}  size={os.path.getsize(BIN)}")

# Step 2: Flash
print("\n\n======== STEP 2: FLASH ========")
r = run([PYTHON, ESPTOOL, "--chip", "esp32s3", "-p", COM, "-b", "460800",
         "--before=default_reset", "--after=hard_reset", "write_flash",
         "--flash_mode", "dio", "--flash_freq", "80m", "--flash_size", "2MB",
         "0x0", BOOT, "0x10000", BIN, "0x8000", PART])
if r.returncode != 0:
    print("FLASH FAILED!")
    sys.exit(1)
print("FLASH DONE!")

# Step 3: Wait for ESP32 boot + WiFi connect + NTP sync + first upload
print("\n\n======== STEP 3: WAIT ========")
print("Waiting 45s for ESP32 boot+WiFi+NTP+upload...")
time.sleep(45)

# Step 4: Check data count every 5 seconds
print("\n\n======== STEP 4: VERIFY ========")
for attempt in range(10):
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:5000/api/count", timeout=5)
        data = json.loads(resp.read())
        total = data["total"]
        print(f"[{time.strftime('%H:%M:%S')}] Count: {total}")
        if total > 65:
            print(f"SUCCESS! New records uploaded! ({total - 65} new)")
            sys.exit(0)
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] Error: {e}")
    time.sleep(5)

print("TIMEOUT: No new records after 50s waiting")
sys.exit(1)
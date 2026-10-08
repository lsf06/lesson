"""Erase flash, flash firmware, verify data upload."""
import subprocess, sys, os, time, json, urllib.request

WORKDIR = r"d:\lesson\xiaolin\lesson-main (1)\lesson-main\esp32_firmware"
PYTHON = r"D:\lesson\Download\esp-idf\Espressif\python_env\idf5.4_py3.10_env\Scripts\python.exe"
ESPTOOL = r"D:\lesson\Download\esp-idf\Espressif\frameworks\esp-idf-v5.4.4\components\esptool_py\esptool\esptool.py"
BUILD_DIR = os.path.join(WORKDIR, "build")
BIN = os.path.join(BUILD_DIR, "qma6100_wifi_upload.bin")
BOOT = os.path.join(BUILD_DIR, "bootloader", "bootloader.bin")
PART = os.path.join(BUILD_DIR, "partition_table", "partition-table.bin")
COM = "COM4"

os.chdir(WORKDIR)

def run(cmd, timeout=120):
    """Run command, print output in real-time, return success."""
    desc = ' '.join(cmd)[:100]
    print(f"\n>>> {desc}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = r.stdout.strip()
        err = r.stderr.strip()
        if out:
            for line in out.splitlines()[-15:]:
                print(f"    {line}")
        if err:
            for line in err.splitlines()[-5:]:
                print(f"  ERR: {line}")
        ok = r.returncode == 0
        print(f"  EXIT={r.returncode} {'OK' if ok else 'FAIL'}")
        return ok
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT after {timeout}s")
        return False
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

# Step 1: Flash (includes erase via chip reset)
print("="*50)
print("STEP 1: Write flash (bootloader + partition + app)")
print("="*50)
esptool_base = [PYTHON, ESPTOOL, "--chip", "esp32s3", "-p", COM, "-b", "460800"]
flash_cmd = esptool_base + [
    "--before=default_reset", "--after=hard_reset", "write_flash",
    "--flash_mode", "dio", "--flash_freq", "80m", "--flash_size", "2MB",
    "0x0", BOOT, "0x10000", BIN, "0x8000", PART
]
if not run(flash_cmd, timeout=30):
    print("Flash failed!")
    sys.exit(1)

print("\nFlash complete! ESP32 should now boot with new firmware...")

# Step 2: Wait for boot + WiFi connect + NTP sync
print("="*50)
print("STEP 2: Waiting for ESP32 to start sending data...")
print("="*50)
print("(Needs: boot ~3s + WiFi scan ~10s + connect+DHCP ~10s + NTP ~10s)")

start = time.time()
last_count = None
for i in range(24):  # 24 * 5s = 120s max
    time.sleep(5)
    elapsed = int(time.time() - start)
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:5000/api/count", timeout=3)
        data = json.loads(resp.read())
        total = data["total"]
        if last_count is None:
            last_count = total
        elif total > last_count:
            print(f"  [{elapsed:3d}s] COUNT: {total} (+{total - last_count})  \033[92mUPLOADING!\033[0m")
            if total > 65:
                print(f"\n\033[92mSUCCESS! {total - 65} new records uploaded!\033[0m")
                sys.exit(0)
        else:
            print(f"  [{elapsed:3d}s] COUNT: {total} (no change)")
            last_count = total
    except Exception as e:
        print(f"  [{elapsed:3d}s] Flask error: {e}")

print("\nTIMEOUT: No uploads detected after 120s")
print("Possible issues:")
print("  1. WiFi 'xiaolin' still not discovered (hidden SSID)")
print("  2. WiFi password wrong")
print("  3. Server IP not reachable from ESP32")
print("  4. ESP32 not booting properly")
print("  5. USB cable issue / power issue")
sys.exit(1)
import os
path = r"d:\lesson\xiaolin\lesson-main (1)\lesson-main\week7_image_capture\esp32_firmware\main"
os.chdir(path)

with open("main.c", encoding="utf-8") as f:
    d = f.read()

ok = True

# Check 1: #include esp_camera.h
if '#include "esp_camera.h"' in d:
    print("1. #include esp_camera.h: OK")
else:
    print("1. #include esp_camera.h: MISSING!")
    ok = False

# Check 2: Camera pin defines
if "#define CAMERA_PIN_PWDN" in d:
    print("2. Camera pin defines: OK")
else:
    print("2. Camera pin defines: MISSING!")
    ok = False

# Check 3: camera_init() function
if "static esp_err_t camera_init(void)" in d:
    print("3. camera_init() function: OK")
else:
    print("3. camera_init() function: MISSING!")
    ok = False

# Check 4: capture_and_upload() function
if "static esp_err_t capture_and_upload(void)" in d:
    print("4. capture_and_upload() function: OK")
else:
    print("4. capture_and_upload() function: MISSING!")
    ok = False

# Check 5: http_poll_request signature with action_out
if "static char *http_poll_request(char **action_out)" in d:
    print("5. http_poll_request(char **action_out): OK")
else:
    print("5. http_poll_request signature: MISSING!")
    ok = False

# Check 6: Action extraction in http_poll_request
if "/* ====== Week7: Extract action field" in d:
    print("6. Action extraction in http_poll_request: OK")
else:
    print("6. Action extraction: MISSING!")
    ok = False

# Check 7: Capture branch in poll_service
if "http_poll_request(&action)" in d:
    print("7. http_poll_request(&action) call: OK")
else:
    print("7. http_poll_request(&action) call: MISSING!")
    ok = False

if "/* ====== Week7: Check if action is \"capture\"" in d:
    print("8. action==capture check in poll_service: OK")
else:
    print("8. action==capture check: MISSING!")
    ok = False

if "capture_and_upload();" in d:
    print("9. capture_and_upload() call: OK")
else:
    print("9. capture_and_upload() call: MISSING!")
    ok = False

# Check 9: camera_init() in app_main
if "/* ====== Week7: Initialize OV2640 camera" in d:
    print("10. camera_init() in app_main: OK")
else:
    print("10. camera_init() in app_main: MISSING!")
    ok = False

# Check 10: CMakeLists.txt
with open("../CMakeLists.txt", encoding="utf-8") as f:
    cmake = f.read()
if "esp32-camera" in cmake:
    print("11. CMakeLists.txt esp32-camera: OK")
else:
    print("11. CMakeLists.txt esp32-camera: MISSING!")
    ok = False

# Check 11: No bsp_display_start() was touched - verify it's still only once / unchanged
bsps = d.count("bsp_display_start")
print(f"12. bsp_display_start appears {bsps} times (should be same as original)")

# Check 12: NO new #include added for ESP_ERROR_CHECK
# ESP_ERROR_CHECK is already used throughout original code

# Print file size
print(f"\nmain.c size: {len(d)} bytes")
print(f"All checks {'PASSED' if ok else 'FAILED!'}")
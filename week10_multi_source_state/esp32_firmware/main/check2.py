import os, sys

# Use raw string for the chdir path
path = r"d:\lesson\xiaolin\lesson-main (1)\lesson-main\week7_image_capture\esp32_firmware\main"
os.chdir(path)

print("CWD:", os.getcwd())

with open("main.c", encoding="utf-8") as f:
    content = f.read()

# Find the http_poll_request section for Edit 4b
idx = content.find('cJSON_GetObjectItem(root, "request_id")')
if idx > 0:
    # Find the section before request_id extraction
    start = content.rfind('cJSON *req_id_json', idx - 200, idx)
    if start < 0:
        start = idx
    # Find return statement
    ret_idx = content.find('return request_id;', idx)
    snippet = content[start:ret_idx + 200]
    print("=== Edit4b section ===")
    print(repr(snippet))
    print("=== END ===")

# Find app_main section for Edit 5
idx2 = content.find('void app_main')
snippet2 = content[idx2:idx2 + 3600]
print("=== app_main section ===")
print(repr(snippet2))
print("=== END ===")
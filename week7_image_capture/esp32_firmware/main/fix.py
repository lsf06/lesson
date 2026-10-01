import os, sys

path = r"d:\lesson\xiaolin\lesson-main (1)\lesson-main\week7_image_capture\esp32_firmware\main"
os.chdir(path)

with open("main.c", encoding="utf-8") as f:
    content = f.read()

# ===== Edit 4b: Add action extraction in http_poll_request =====
old_4b = '''    char *request_id = strdup(req_id_json->valuestring);
    cJSON_Delete(root);
    free(resp);

    ESP_LOGI(TAG, "Poll: received request_id=%s", request_id);
    return request_id;
}'''

new_4b = '''    char *request_id = strdup(req_id_json->valuestring);

    /* ====== Week7: Extract action field (capture / normal) ====== */
    if (action_out) {
        cJSON *act_json = cJSON_GetObjectItem(root, "action");
        if (cJSON_IsString(act_json)) {
            *action_out = strdup(act_json->valuestring);
        } else {
            *action_out = NULL;
        }
    }

    cJSON_Delete(root);
    free(resp);

    ESP_LOGI(TAG, "Poll: received request_id=%s", request_id);
    return request_id;
}'''

if old_4b in content:
    content = content.replace(old_4b, new_4b, 1)
    print("Edit 4b OK: action extraction added")
else:
    print("WARN: old_4b not found!")
    idx = content.find('strdup(req_id_json->valuestring)')
    if idx > 0:
        print(repr(content[idx:idx+200]))

# ===== Edit 5: Add camera_init() call in app_main =====
# Find the SNTP line, add camera init after it
old_5 = '''    /* 2. SNTP time sync (sets TZ=CST-8 internally) */
    sntp_init_time();'''

new_5 = '''    /* 2. SNTP time sync (sets TZ=CST-8 internally) */
    sntp_init_time();

    /* ====== Week7: Initialize OV2640 camera ====== */
    {
        esp_err_t cam_err = camera_init();
        if (cam_err != ESP_OK) {
            ESP_LOGW(TAG, "Camera init warning (LCD-CAM bus share?): %s", esp_err_to_name(cam_err));
        }
    }'''

if old_5 in content:
    content = content.replace(old_5, new_5, 1)
    print("Edit 5 OK: camera_init() added in app_main")
else:
    print("WARN: old_5 not found!")
    idx = content.find('SNTP time sync')
    print(repr(content[idx-50:idx+50]))

# Write back
with open("main.c", "w", encoding="utf-8") as f:
    f.write(content)

print("All edits applied to main.c!")
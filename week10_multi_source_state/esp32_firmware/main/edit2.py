import os, sys
os.chdir("d:\\lesson\\xiaolin\\lesson-main (1)\\lesson-main\\week7_image_capture\\esp32_firmware\\main")

with open("main.c", encoding="utf-8") as f:
    data = f.read()

# ====== Fix Edit 4: Modify http_poll_request() to also return action ======
# Find the function signature and modify it
old_func = "static char *http_poll_request(void)"
new_func = "static char *http_poll_request(char **action_out)"
if old_func in data:
    data = data.replace(old_func, new_func, 1)
    print("Edit 4a: http_poll_request signature updated")
else:
    print("WARN: http_poll_request signature not found!")
    print(repr(data[data.find("http_poll_request"):data.find("http_poll_request")+50]))

# Modify the JSON parsing inside http_poll_request to extract action
# Find the section where request_id is extracted from JSON
old_json_parse = """    cJSON *req_id_json = cJSON_GetObjectItem(root, "request_id");
    if (!cJSON_IsString(req_id_json)) {
        ESP_LOGW(TAG, "Poll: response missing request_id");
        cJSON_Delete(root);
        free(resp);
        return NULL;
    }"""
new_json_parse = """    cJSON *req_id_json = cJSON_GetObjectItem(root, "request_id");
    if (!cJSON_IsString(req_id_json)) {
        ESP_LOGW(TAG, "Poll: response missing request_id");
        cJSON_Delete(root);
        free(resp);
        return NULL;
    }

    /* ====== Week7: Extract action field (capture / normal) ====== */
    if (action_out) {
        cJSON *act_json = cJSON_GetObjectItem(root, "action");
        if (cJSON_IsString(act_json)) {
            *action_out = strdup(act_json->valuestring);
        } else {
            *action_out = NULL;
        }
    }"""
if old_json_parse in data:
    data = data.replace(old_json_parse, new_json_parse, 1)
    print("Edit 4b: action extraction added in http_poll_request")
else:
    print("WARN: old_json_parse not found!")
    idx = data.find('cJSON_GetObjectItem(root, "request_id")')
    print(repr(data[idx-50:idx+500]))

# ====== Fix Edit 4c: Modify caller in poll_service to pass action_out ======
# Find the call to http_poll_request() in poll_service
old_call = '        char *request_id = http_poll_request();\n        poll_cycles++;\n\n        if (request_id) {'
new_call = """        char *action = NULL;
        char *request_id = http_poll_request(&action);
        poll_cycles++;

        if (request_id) {
            /* ====== Week7: Check if action is "capture" ====== */
            if (action && strcmp(action, "capture") == 0) {
                ESP_LOGI(TAG, "Action = capture, taking photo...");
                capture_and_upload();
                free(action);
                free(request_id);
                continue;
            }
            free(action);
            action = NULL;
"""
if old_call in data:
    data = data.replace(old_call, new_call, 1)
    print("Edit 4c: capture branch added in poll_service loop")
else:
    print("WARN: old_call not found!")
    idx = data.find('http_poll_request()')
    print(repr(data[idx-20:idx+150]))

# ====== Fix Edit 5: camera_init() call in app_main ======
# Find the wifi check loop in app_main
old_wifi = """    for (int retry = 1; retry <= 12; retry++) {
        if (wifi_is_connected()) break;
        EventBits_t bits = xEventGroupWaitBits(s_wifi_evt, WIFI_CONNECTED_BIT,
                                               pdFALSE, pdTRUE, pdMS_TO_TICKS(5000));
        if (bits & WIFI_CONNECTED_BIT) break;
        ESP_LOGW(TAG, "WiFi not connected yet (retry %d/12)...\", retry);
        /* Every 4 retries (~20s), run a diagnostic scan */"""
new_wifi = """    for (int retry = 1; retry <= 12; retry++) {
        if (wifi_is_connected()) break;
        EventBits_t bits = xEventGroupWaitBits(s_wifi_evt, WIFI_CONNECTED_BIT,
                                               pdFALSE, pdTRUE, pdMS_TO_TICKS(5000));
        if (bits & WIFI_CONNECTED_BIT) break;
        ESP_LOGW(TAG, "WiFi not connected yet (retry %d/12)...", retry);
        /* Every 4 retries (~20s), run a diagnostic scan */"""
if old_wifi in data:
    data = data.replace(old_wifi, new_wifi, 1)
    # Add camera init after wifi
    old_after_wifi = """    ESP_LOGI(TAG, "WiFi connected, starting tasks...");"""
    new_after_wifi = """    ESP_LOGI(TAG, "WiFi connected, starting tasks...");

    /* ====== Week7: Initialize OV2640 camera ====== */
    {
        esp_err_t cam_err = camera_init();
        if (cam_err != ESP_OK) {
            ESP_LOGW(TAG, "Camera init skipped (expected if LCD shares DVP bus)");
        }
    }"""
    if old_after_wifi in data:
        data = data.replace(old_after_wifi, new_after_wifi, 1)
        print("Edit 5: camera_init() call added in app_main")
    else:
        print("WARN: old_after_wifi not found!")
        idx = data.find("WiFi connected, starting")
        print(repr(data[idx-50:idx+200]))
else:
    print("WARN: old_wifi not found for Edit 5!")
    idx = data.find("for (int retry = 1; retry <= 12; retry++)")
    print(repr(data[idx:idx+300]))

# Also update the strdup reference - need to make sure string.h is included
# strdup is in string.h which is already included at the top

with open("main.c", "w", encoding="utf-8") as f:
    f.write(data)
print("\nAll remaining edits applied!")
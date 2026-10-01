import os, sys
os.chdir("d:\\lesson\\xiaolin\\lesson-main (1)\\lesson-main\\week7_image_capture\\esp32_firmware\\main")

with open("main.c", encoding="utf-8") as f:
    data = f.read()

# ====== Edit 1: Add #include "esp_camera.h" after last existing include ======
# Find the last #include line
idx_include_end = data.rfind('#include "qma6100p.h"')
# Add camera include after qma6100p.h and before driver/gpio.h
old_inc = '#include "qma6100p.h"\n#include "driver/gpio.h"'
new_inc = '#include "qma6100p.h"\n#include "esp_camera.h"\n#include "driver/gpio.h"'
if old_inc in data:
    data = data.replace(old_inc, new_inc, 1)
    print("Edit 1: #include esp_camera.h added")
else:
    print("WARN: old_inc not found!")
    print(repr(data[data.find('qma6100p'):data.find('qma6100p')+200]))

# ====== Edit 2: Add camera config defines after existing defines ======
old_defs_end = "#define TRIGGER_TIMEOUT_MS  5000\n\nstatic const char *TAG = \"MAIN\";"
new_defs = """#define TRIGGER_TIMEOUT_MS  5000

/* ====== Week7: OV2640 Camera ====== */
#define CAMERA_PIN_PWDN      -1
#define CAMERA_PIN_RESET     -1
#define CAMERA_PIN_XCLK      10
#define CAMERA_PIN_SIOD      40
#define CAMERA_PIN_SIOC      41
#define CAMERA_PIN_D7        48
#define CAMERA_PIN_D6        11
#define CAMERA_PIN_D5        12
#define CAMERA_PIN_D4        14
#define CAMERA_PIN_D3        16
#define CAMERA_PIN_D2        17
#define CAMERA_PIN_D1        18
#define CAMERA_PIN_D0        21
#define CAMERA_PIN_VSYNC     38
#define CAMERA_PIN_HREF      47
#define CAMERA_PIN_PCLK      13
#define CAPTURE_SERVER_URL   "http://10.1.41.43:5000/api/capture_image"

static const char *TAG = "MAIN\";"""
if old_defs_end in data:
    data = data.replace(old_defs_end, new_defs, 1)
    print("Edit 2: camera pin defines added")
else:
    print("WARN: old_defs_end not found!")
    idx = data.find('static const char *TAG')
    print(repr(data[idx-100:idx+50]))

# ====== Edit 3: Add camera_init() and capture_and_upload() before app_main() ======
# Find app_main()
old_app_main = "void app_main(void)\n{"
new_functions = """static esp_err_t camera_init(void)
{
    camera_config_t config = {
        .pin_pwdn  = CAMERA_PIN_PWDN,
        .pin_reset = CAMERA_PIN_RESET,
        .pin_xclk = CAMERA_PIN_XCLK,
        .pin_sscb_sda = CAMERA_PIN_SIOD,
        .pin_sscb_scl = CAMERA_PIN_SIOC,
        .pin_d7 = CAMERA_PIN_D7,
        .pin_d6 = CAMERA_PIN_D6,
        .pin_d5 = CAMERA_PIN_D5,
        .pin_d4 = CAMERA_PIN_D4,
        .pin_d3 = CAMERA_PIN_D3,
        .pin_d2 = CAMERA_PIN_D2,
        .pin_d1 = CAMERA_PIN_D1,
        .pin_d0 = CAMERA_PIN_D0,
        .pin_vsync = CAMERA_PIN_VSYNC,
        .pin_href = CAMERA_PIN_HREF,
        .pin_pclk = CAMERA_PIN_PCLK,
        .xclk_freq_hz = 20000000,
        .ledc_timer = LEDC_TIMER_0,
        .ledc_channel = LEDC_CHANNEL_0,
        .pixel_format = PIXFORMAT_JPEG,
        .frame_size = FRAMESIZE_QVGA,
        .jpeg_quality = 12,
        .fb_count = 1,
        .fb_location = CAMERA_FB_IN_PSRAM,
        .grab_mode = CAMERA_GRAB_WHEN_EMPTY,
    };
    esp_err_t ret = esp_camera_init(&config);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Camera init failed: %s (0x%x)", esp_err_to_name(ret), ret);
    } else {
        ESP_LOGI(TAG, "Camera OV2640 initialized: QVGA JPEG PSRAM");
    }
    return ret;
}

static esp_err_t capture_and_upload(void)
{
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
        ESP_LOGE(TAG, "Camera capture failed: fb_get returned NULL");
        return ESP_FAIL;
    }
    ESP_LOGI(TAG, "Captured JPEG: %zu bytes", fb->len);

    esp_http_client_config_t http_cfg = {
        .url = CAPTURE_SERVER_URL,
        .method = HTTP_METHOD_POST,
        .timeout_ms = 10000,
        .keep_alive_enable = false,
        .disable_auto_redirect = true,
    };
    esp_http_client_handle_t client = esp_http_client_init(&http_cfg);
    if (!client) {
        ESP_LOGE(TAG, "CAPTURE: HTTP client init failed");
        esp_camera_fb_return(fb);
        return ESP_FAIL;
    }
    esp_http_client_set_header(client, "Content-Type", "image/jpeg");
    esp_http_client_set_post_field(client, (const char *)fb->buf, fb->len);

    esp_err_t err = esp_http_client_perform(client);
    if (err == ESP_OK) {
        int status = esp_http_client_get_status_code(client);
        ESP_LOGI(TAG, "CAPTURE: HTTP %d", status);
    } else {
        ESP_LOGE(TAG, "CAPTURE: HTTP failed: %s (0x%x)", esp_err_to_name(err), err);
    }
    esp_http_client_cleanup(client);
    esp_camera_fb_return(fb);
    vTaskDelay(pdMS_TO_TICKS(20));
    return err;
}

void app_main(void)
{"""
if old_app_main in data:
    data = data.replace(old_app_main, new_functions, 1)
    # But we only want the FIRST occurrence (function definition, not the one in the middle)
    # Actually, app_main(void) only appears once, at the function definition.
    # But let me verify by checking if there are multiple.
    cnt = data.count("void app_main(void)")
    print(f"Edit 3: camera_init/capture_and_upload added (app_main appears {cnt} times in result)")
else:
    print("WARN: old_app_main not found!")
    idx = data.find("void app_main")
    print(repr(data[idx-100:idx+50]))

# ====== Edit 4: In poll_service(), add action=="capture" branch ======
# Find the JSON parsing section where it checks request data
# Look for something like "esp_err_t sensor_err = ESP_FAIL;" which is after JSON parsing
# The structure is: get pending_request JSON -> extract request_id -> read sensor -> upload
# We need to check if action field is "capture" and call capture_and_upload instead

# Find where the sensor reading begins (after JSON parsing)
old_sensor_read = '/* Wake sensor again (shared bus may have put it to sleep) */'
# Before this, we need to add the capture branch
# Let's find something before it that is unique
capture_trigger = """            free(request_id);
                    continue;   /* skip upload, loop back to poll */
                }
                ESP_LOGI(TAG, "RAW I2C fallback SUCCESS - got real data");
            }"""

capture_branch = """                free(request_id);
                    continue;   /* skip upload, loop back to poll */
                }
                ESP_LOGI(TAG, "RAW I2C fallback SUCCESS - got real data");
            }

            /* ====== Week7: Check if action is "capture" ====== */
            cJSON *action_item = cJSON_GetObjectItem(request_json, "action");
            if (action_item && action_item->valuestring && strcmp(action_item->valuestring, "capture") == 0) {
                ESP_LOGI(TAG, "Action = capture, taking photo...");
                capture_and_upload();
                free(request_id);
                continue;
            }
"""

if capture_trigger in data:
    data = data.replace(capture_trigger, capture_branch, 1)
    print("Edit 4: action==capture branch added in poll_service")
else:
    print("WARN: capture_trigger not found!")
    # Let's find what we have after RAW I2C fallback SUCCESS
    idx = data.find("RAW I2C fallback SUCCESS")
    print(repr(data[idx-50:idx+500]))

# ====== Edit 5: In app_main(), call camera_init() after wifi is connected ======
# Find the line where ntp sync is done or where it continues after wifi
# Look for "/* Wait for Wi-Fi connection and NTP sync */" or similar
old_wait_wifi = """    /* Wait for Wi-Fi connection and NTP sync */
    xEventGroupWaitBits(s_wifi_evt, WIFI_CONNECTED_BIT, false, true, portMAX_DELAY);
    ESP_LOGI(TAG, "Wi-Fi connected, starting main task...");"""

new_wait_wifi = """    /* Wait for Wi-Fi connection and NTP sync */
    xEventGroupWaitBits(s_wifi_evt, WIFI_CONNECTED_BIT, false, true, portMAX_DELAY);
    ESP_LOGI(TAG, "Wi-Fi connected, starting main task...");

    /* ====== Week7: Initialize OV2640 camera ====== */
    {
        esp_err_t cam_err = camera_init();
        if (cam_err != ESP_OK) {
            ESP_LOGW(TAG, "Camera init failed (LCD_CAM conflict?), continuing without camera");
        }
    }"""

if old_wait_wifi in data:
    data = data.replace(old_wait_wifi, new_wait_wifi, 1)
    print("Edit 5: camera_init() call added in app_main after wifi")
else:
    print("WARN: old_wait_wifi not found!")
    idx = data.find("Wait for Wi-Fi")
    print(repr(data[idx-50:idx+200]))

with open("main.c", "w", encoding="utf-8") as f:
    f.write(data)
print("\nAll edits applied to main.c!")
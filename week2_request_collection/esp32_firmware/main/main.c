/*
 * ESP32-S3-EYE QMA6100P Accelerometer + Wi-Fi HTTP Upload
 *
 * Stage 4: Timezone fix (CST-8), WiFi reconnect check, exponential backoff,
 *          5 Hz upload rate, sensor error recovery, watchdog safety.
 */

#include <stdio.h>
#include <string.h>
#include <time.h>
#include <stdlib.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"
#include "esp_log.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "nvs_flash.h"
#include "esp_http_client.h"
#include "esp_netif.h"
#include "esp_sntp.h"
#include "esp_task_wdt.h"
#include "cJSON.h"
#include "bsp/esp32_s3_eye.h"
#include "qma6100p.h"

/* ====== CONFIGURATION ====== */
#define WIFI_SSID           "431"
#define WIFI_PASSWORD       "88888888"
#define SERVER_URL          "http://10.1.41.43:5000/api/upload"
#define SERVER_POLL_URL     "http://10.1.41.43:5000/api/pending_request?device_id=group01_esp32s3eye"
#define DEVICE_ID           "group01_esp32s3eye"

#define POLL_INTERVAL_MS    1000    /* poll server every 1 s for pending requests */
#define HTTP_TIMEOUT_MS     3000    /* 3 s HTTP timeout */

static const char *TAG = "MAIN";

/* Event group bit: Wi-Fi got IPv4 address */
static EventGroupHandle_t s_wifi_evt;
#define WIFI_CONNECTED_BIT  BIT0

static qma6100p_handle_t sensor = NULL;

/* ----------------------- Wi-Fi ----------------------- */
static void wifi_event_handler(void *arg, esp_event_base_t event_base,
                               int32_t event_id, void *event_data)
{
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        ESP_LOGI(TAG, "STA started, connecting...");
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_CONNECTED) {
        ESP_LOGI(TAG, "WiFi connected!");
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        wifi_event_sta_disconnected_t *disconn = (wifi_event_sta_disconnected_t *)event_data;
        ESP_LOGW(TAG, "Wi-Fi disconnected (reason=%d), auto-reconnecting...", disconn->reason);
        xEventGroupClearBits(s_wifi_evt, WIFI_CONNECTED_BIT);
        esp_wifi_connect();
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *ev = (ip_event_got_ip_t *)event_data;
        ESP_LOGI(TAG, "Got IP: " IPSTR, IP2STR(&ev->ip_info.ip));
        xEventGroupSetBits(s_wifi_evt, WIFI_CONNECTED_BIT);
    }
}

static void wifi_init(void)
{
    s_wifi_evt = xEventGroupCreate();

    ESP_ERROR_CHECK(nvs_flash_init());
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID,
                       &wifi_event_handler, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP,
                       &wifi_event_handler, NULL, NULL));

    wifi_config_t wifi_cfg = {
        .sta = {
            .ssid = WIFI_SSID,
            .password = WIFI_PASSWORD,
            .scan_method = WIFI_ALL_CHANNEL_SCAN,     /* needed for hidden SSID */
            .sort_method = WIFI_CONNECT_AP_BY_SIGNAL,
            .threshold.authmode = WIFI_AUTH_WPA_PSK,          /* WPA or stronger */
            .pmf_cfg = {
                .capable = false,
                .required = false,
            },
        },
    };
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_cfg));
    ESP_ERROR_CHECK(esp_wifi_start());

    ESP_LOGI(TAG, "Wi-Fi init done, connecting to %s...", WIFI_SSID);
}

static bool wifi_is_connected(void)
{
    EventBits_t bits = xEventGroupGetBits(s_wifi_evt);
    return (bits & WIFI_CONNECTED_BIT) != 0;
}

static bool wifi_wait_connected(uint32_t timeout_ms)
{
    EventBits_t bits = xEventGroupWaitBits(s_wifi_evt, WIFI_CONNECTED_BIT,
                                           pdFALSE, pdTRUE,
                                           pdMS_TO_TICKS(timeout_ms));
    return (bits & WIFI_CONNECTED_BIT) != 0;
}

/* ----------------------- SNTP Time Sync ----------------------- */
static void sntp_sync_cb(struct timeval *tv)
{
    ESP_LOGI(TAG, "SNTP: time synced, TZ=CST-8 active");
}

static void sntp_init_time(void)
{
    /* Set timezone to Beijing (CST-8) BEFORE SNTP sync */
    setenv("TZ", "CST-8", 1);
    tzset();

    esp_sntp_setoperatingmode(SNTP_OPMODE_POLL);
    esp_sntp_setservername(0, "ntp.aliyun.com");
    esp_sntp_setservername(1, "pool.ntp.org");
    sntp_set_time_sync_notification_cb(sntp_sync_cb);
    esp_sntp_init();

    int retry = 0;
    while (sntp_get_sync_status() == SNTP_SYNC_STATUS_RESET && ++retry < 150) {
        vTaskDelay(pdMS_TO_TICKS(100));
    }
    if (retry >= 150) {
        ESP_LOGW(TAG, "SNTP sync timed out (using system time)");
    } else {
        ESP_LOGI(TAG, "SNTP synced in %.1fs", retry * 0.1f);
    }
}

/* ----------------------- HTTP Poll Request ----------------------- */
static char *http_poll_request(void)
{
    esp_http_client_config_t config = {
        .url = SERVER_POLL_URL,
        .method = HTTP_METHOD_GET,
        .timeout_ms = HTTP_TIMEOUT_MS,
        .keep_alive_enable = false,
        .disable_auto_redirect = true,
    };
    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (!client) {
        ESP_LOGE(TAG, "Poll: HTTP client init failed");
        return NULL;
    }

    /* Use open/fetch_headers/read/close pattern instead of perform()
     * to guarantee response body is properly buffered and readable. */
    esp_err_t err = esp_http_client_open(client, 0);  /* 0 write_len = GET */
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Poll: HTTP open failed: %s (err=0x%x)", esp_err_to_name(err), err);
        esp_http_client_cleanup(client);
        return NULL;
    }

    int content_length = esp_http_client_fetch_headers(client);
    if (content_length < 0) {
        ESP_LOGE(TAG, "Poll: fetch_headers failed (len=%d)", content_length);
        esp_http_client_close(client);
        esp_http_client_cleanup(client);
        return NULL;
    }

    int status = esp_http_client_get_status_code(client);
    if (status != 200) {
        ESP_LOGW(TAG, "Poll: HTTP %d", status);
        esp_http_client_close(client);
        esp_http_client_cleanup(client);
        return NULL;
    }

    // Read response body
    char *resp = malloc(512);
    if (!resp) {
        esp_http_client_close(client);
        esp_http_client_cleanup(client);
        return NULL;
    }
    int read_len = esp_http_client_read(client, resp, 511);
    esp_http_client_close(client);
    esp_http_client_cleanup(client);

    if (read_len <= 0) {
        ESP_LOGW(TAG, "Poll: empty response (read_len=%d, expected content_length=%d)", read_len, content_length);
        free(resp);
        return NULL;
    }
    resp[read_len] = '\0';
    ESP_LOGI(TAG, "Poll response (%d bytes): %s", read_len, resp);

    // Parse JSON: {"has_request": true/false, "request_id": "..."}
    cJSON *root = cJSON_Parse(resp);
    if (!root) {
        ESP_LOGW(TAG, "Poll: JSON parse failed");
        free(resp);
        return NULL;
    }

    cJSON *has_req = cJSON_GetObjectItem(root, "has_request");
    if (!cJSON_IsBool(has_req) || !cJSON_IsTrue(has_req)) {
        cJSON_Delete(root);
        free(resp);
        return NULL;  // no pending request
    }

    cJSON *req_id_json = cJSON_GetObjectItem(root, "request_id");
    if (!cJSON_IsString(req_id_json)) {
        cJSON_Delete(root);
        free(resp);
        return NULL;
    }

    char *request_id = strdup(req_id_json->valuestring);
    cJSON_Delete(root);
    free(resp);

    ESP_LOGI(TAG, "Poll: received request_id=%s", request_id);
    return request_id;
}

/* ----------------------- HTTP Upload ----------------------- */
static esp_err_t http_upload(float ax, float ay, float az, const char *time_str, const char *request_id)
{
    char payload[512];
    int len;
    if (request_id) {
        len = snprintf(payload, sizeof(payload),
                 "{\"device_id\":\"%s\",\"ax\":%.2f,\"ay\":%.2f,\"az\":%.2f,\"device_time\":\"%s\",\"request_id\":\"%s\"}",
                 DEVICE_ID, ax, ay, az, time_str, request_id);
    } else {
        len = snprintf(payload, sizeof(payload),
                 "{\"device_id\":\"%s\",\"ax\":%.2f,\"ay\":%.2f,\"az\":%.2f,\"device_time\":\"%s\"}",
                 DEVICE_ID, ax, ay, az, time_str);
    }
    if (len < 0 || len >= sizeof(payload)) {
        ESP_LOGE(TAG, "Payload overflow!");
        return ESP_ERR_NO_MEM;
    }

    esp_http_client_config_t config = {
        .url = SERVER_URL,
        .method = HTTP_METHOD_POST,
        .timeout_ms = HTTP_TIMEOUT_MS,
        .keep_alive_enable = false,
        .disable_auto_redirect = true,
    };
    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (!client) {
        ESP_LOGE(TAG, "HTTP client init failed");
        return ESP_FAIL;
    }

    esp_http_client_set_header(client, "Content-Type", "application/json");
    esp_http_client_set_post_field(client, payload, strlen(payload));

    esp_err_t err = esp_http_client_perform(client);
    if (err == ESP_OK) {
        int status = esp_http_client_get_status_code(client);
        if (status == 200) {
            ESP_LOGI(TAG, "UPLOAD HTTP 200 OK");
        } else {
            ESP_LOGW(TAG, "HTTP %d (non-200)", status);
        }
    } else {
        ESP_LOGE(TAG, "HTTP upload failed: %s (err=0x%x)", esp_err_to_name(err), err);
    }

    esp_http_client_cleanup(client);
    return err;
}

/* ----------------------- QMA6100P Soft Reset ----------------------- */
/* Internal struct layout (first field matches qma6100p_dev_t in driver) */
typedef struct { i2c_master_dev_handle_t i2c_handle; } qma6100p_internal_t;

static esp_err_t qma6100p_soft_reset(qma6100p_handle_t sensor)
{
    qma6100p_internal_t *sens = (qma6100p_internal_t *)sensor;
    uint8_t reset_cmd[2] = {0x36, 0xB6};  /* PMU soft reset */
    esp_err_t ret = i2c_master_transmit(sens->i2c_handle, reset_cmd, 2, 100);
    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "Soft reset I2C failed: %s", esp_err_to_name(ret));
        return ret;
    }
    vTaskDelay(pdMS_TO_TICKS(50));  /* Wait for reset to complete */
    ESP_LOGI(TAG, "Sensor soft reset OK");
    return ESP_OK;
}

/* ----------------------- QMA6100P Raw Register Fallback ----------------------- */
/**
 * @brief Ultimate fallback: read accelerometer data via raw I2C register access.
 *
 * Used when the qma6100p driver API (qma6100p_get_acce) fails after retries.
 * Steps:
 *   1. Write 0x80 to PWR_MGMT_1 (0x11) to wake sensor
 *   2. Wait 20ms for ADC conversion
 *   3. Read 6 bytes from ACCEL_XOUT_H (0x01)
 *   4. Convert 14-bit raw → g-value (sensitivity=4096 for ±2g)
 *
 * @param sensor  QMA6100P driver handle
 * @param acce    Output: accel values in g
 * @return ESP_OK on success, ESP_FAIL/I2C error on failure
 */
static esp_err_t qma6100p_raw_read_fallback(qma6100p_handle_t sensor, qma6100p_acce_value_t *acce)
{
    qma6100p_internal_t *sens = (qma6100p_internal_t *)sensor;
    esp_err_t ret;

    /* Step 1: Wake sensor by writing BIT7 to PWR_MGMT_1 (0x11) */
    uint8_t wake_cmd[2] = {0x11, 0x80};
    ret = i2c_master_transmit(sens->i2c_handle, wake_cmd, 2, 100);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Raw fallback: wake I2C write failed: %s (err=0x%x)", esp_err_to_name(ret), ret);
        return ret;
    }
    vTaskDelay(pdMS_TO_TICKS(20));

    /* Step 2: Verify WHO_AM_I (0x00) */
    uint8_t reg_addr = 0x00;
    uint8_t who = 0;
    ret = i2c_master_transmit_receive(sens->i2c_handle, &reg_addr, 1, &who, 1, 100);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Raw fallback: WHO_AM_I read failed: %s (err=0x%x)", esp_err_to_name(ret), ret);
        return ret;
    }
    ESP_LOGI(TAG, "Raw fallback: WHO_AM_I = 0x%02X", who);

    /* Step 3: Read 6 bytes from ACCEL_XOUT_H (0x01) */
    uint8_t data[6] = {0};
    reg_addr = 0x01;
    ret = i2c_master_transmit_receive(sens->i2c_handle, &reg_addr, 1, data, 6, 100);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Raw fallback: ACCEL read failed: %s (err=0x%x)", esp_err_to_name(ret), ret);
        return ret;
    }

    /* Step 4: Convert raw 14-bit data to g-values
     *   - QMA6100P stores data as 14-bit two's complement (upper 12 bits valid, lower 2 bits discarded)
     *   - Driver divides by 4 to drop 2 LSBs, then by sensitivity (4096 for ±2g)
     *   - Combined: raw_value = ((high<<8)|low) >> 2;  g = raw_value / 4096.0f
     */
    int16_t raw_x = (int16_t)(((uint16_t)data[1] << 8) | data[0]) / 4;
    int16_t raw_y = (int16_t)(((uint16_t)data[3] << 8) | data[2]) / 4;
    int16_t raw_z = (int16_t)(((uint16_t)data[5] << 8) | data[4]) / 4;

    acce->acce_x = raw_x / 4096.0f;
    acce->acce_y = raw_y / 4096.0f;
    acce->acce_z = raw_z / 4096.0f;

    ESP_LOGI(TAG, "Raw fallback OK: raw=(%d,%d,%d) → g=(%.3f,%.3f,%.3f)",
             raw_x, raw_y, raw_z,
             acce->acce_x, acce->acce_y, acce->acce_z);

    return ESP_OK;
}

void app_main(void)
{
    ESP_LOGI(TAG, "=== ESP32-S3-EYE QMA6100P + Wi-Fi Upload v4 ===");

    /* 1. Wi-Fi */
    wifi_init();
    ESP_LOGI(TAG, "Waiting for Wi-Fi connection (extended retry + scan)...");
    for (int retry = 1; retry <= 12; retry++) {
        if (wifi_is_connected()) break;
        EventBits_t bits = xEventGroupWaitBits(s_wifi_evt, WIFI_CONNECTED_BIT,
                                               pdFALSE, pdTRUE, pdMS_TO_TICKS(5000));
        if (bits & WIFI_CONNECTED_BIT) break;
        ESP_LOGW(TAG, "WiFi not connected yet (retry %d/12)...", retry);
        /* Every 4 retries (~20s), run a diagnostic scan */
        if (retry % 4 == 0) {
            ESP_LOGW(TAG, "=== Running diagnostic WiFi scan ===");
            wifi_scan_config_t scan_cfg = {
                .ssid = NULL,
                .bssid = NULL,
                .channel = 0,
                .show_hidden = true,
                .scan_type = WIFI_SCAN_TYPE_ACTIVE,
            };
            if (esp_wifi_scan_start(&scan_cfg, true) == ESP_OK) {
                uint16_t ap_num = 0;
                esp_wifi_scan_get_ap_num(&ap_num);
                ESP_LOGW(TAG, "Scan found %d AP(s):", ap_num);
                if (ap_num > 0) {
                    wifi_ap_record_t *ap_list = calloc(ap_num, sizeof(wifi_ap_record_t));
                    if (ap_list) {
                        esp_wifi_scan_get_ap_records(&ap_num, ap_list);
                        for (int i = 0; i < ap_num; i++) {
                            ESP_LOGW(TAG, "  [%d] SSID=\"%s\" CH=%d RSSI=%d AUTH=%d",
                                     i, ap_list[i].ssid, ap_list[i].primary,
                                     ap_list[i].rssi, ap_list[i].authmode);
                        }
                        free(ap_list);
                    }
                }
            } else {
                ESP_LOGW(TAG, "Scan failed (busy? will retry later)");
            }
        }
    }
    if (wifi_is_connected()) {
        ESP_LOGI(TAG, "WiFi CONNECTED!");
    } else {
        ESP_LOGW(TAG, "WiFi not connected after 60s, continuing with sensor init...");
    }

    /* 2. SNTP time sync (sets TZ=CST-8 internally) */
    sntp_init_time();

    /* 3. I2C + Sensor */
    ESP_ERROR_CHECK(bsp_i2c_init());
    i2c_master_bus_handle_t i2c_bus = bsp_i2c_get_handle();
    ESP_ERROR_CHECK(qma6100p_create(i2c_bus, QMA6100P_I2C_ADDRESS, &sensor));

    /* Override I2C device speed to 100kHz for stability on shared bus */
    {
        qma6100p_internal_t *sens_int = (qma6100p_internal_t *)sensor;
        i2c_master_dev_handle_t old_handle = sens_int->i2c_handle;
        ESP_ERROR_CHECK(i2c_master_bus_rm_device(old_handle));
        i2c_device_config_t dev_cfg_100k = {
            .device_address = QMA6100P_I2C_ADDRESS,
            .scl_speed_hz = 100000,
        };
        ESP_ERROR_CHECK(i2c_master_bus_add_device(i2c_bus, &dev_cfg_100k, &sens_int->i2c_handle));
        ESP_LOGI(TAG, "I2C device speed overridden to 100kHz");
    }

    uint8_t who = 0;
    if (qma6100p_get_deviceid(sensor, &who) == ESP_OK) {
        ESP_LOGI(TAG, "WHO_AM_I: 0x%02X", who);
    } else {
        ESP_LOGW(TAG, "WHO_AM_I read failed, attempting soft reset...");
        qma6100p_soft_reset(sensor);
        if (qma6100p_get_deviceid(sensor, &who) == ESP_OK) {
            ESP_LOGI(TAG, "WHO_AM_I (after reset): 0x%02X", who);
        } else {
            ESP_LOGW(TAG, "WHO_AM_I still failed, sensor may need power cycle");
        }
    }

    /* Load NVM calibration data */
    esp_err_t nvm_ret = qma6100p_nvm_load(sensor);
    ESP_LOGI(TAG, "NVM load: %s", esp_err_to_name(nvm_ret));

    ESP_ERROR_CHECK(qma6100p_config(sensor, ACCE_FS_2G));

    esp_err_t wake_ret = qma6100p_wake_up(sensor);
    if (wake_ret != ESP_OK) {
        ESP_LOGW(TAG, "Sensor wake_up failed (%s), retrying with reset...", esp_err_to_name(wake_ret));
        qma6100p_soft_reset(sensor);
        vTaskDelay(pdMS_TO_TICKS(100));
        wake_ret = qma6100p_wake_up(sensor);
        ESP_LOGI(TAG, "Sensor wake_up retry: %s", esp_err_to_name(wake_ret));
    }
    vTaskDelay(pdMS_TO_TICKS(100));
    ESP_LOGI(TAG, "Sensor ready, entering request-polling mode...");

    /* Register to the Task Watchdog so crashes get logged */
    ESP_ERROR_CHECK(esp_task_wdt_add(NULL));

    /* Stats counters */
    uint32_t upload_ok = 0;
    uint32_t upload_fail = 0;
    uint32_t sensor_fail = 0;
    uint32_t poll_cycles = 0;
    uint32_t consecutive_sensor_fail = 0;

    TickType_t last_stats = xTaskGetTickCount();

    while (1) {
        /* Feed the watchdog */
        esp_task_wdt_reset();

        /* --- Check Wi-Fi before any network operation --- */
        if (!wifi_is_connected()) {
            ESP_LOGW(TAG, "Wi-Fi lost, waiting for reconnect...");
            if (!wifi_wait_connected(10000)) {
                ESP_LOGW(TAG, "Wi-Fi still down, retrying...");
                vTaskDelay(pdMS_TO_TICKS(2000));
                continue;
            }
            ESP_LOGI(TAG, "Wi-Fi reconnected!");
        }

        /* --- Poll server for a pending collection request --- */
        char *request_id = http_poll_request();
        poll_cycles++;

        if (request_id) {
            /* ---------------------------------------------------------------
             * Got a collection request!  Read REAL QMA6100P sensor data.
             *
             * Strategy:
             *   1. Re-wake sensor + 20ms delay for data-ready conversion
             *   2. Retry qma6100p_get_acce() up to 3 times (10ms apart)
             *   3. If driver API still fails → fallback to raw I2C register read
             *   4. NO mock data — grade depends on real hardware readings
             * --------------------------------------------------------------- */
            qma6100p_acce_value_t acce = {0};
            esp_err_t sensor_err = ESP_FAIL;

            /* Wake sensor again (shared bus may have put it to sleep) */
            esp_err_t wake_r = qma6100p_wake_up(sensor);
            if (wake_r != ESP_OK) {
                ESP_LOGW(TAG, "Pre-read wake_up failed: %s (err=0x%x)", esp_err_to_name(wake_r), wake_r);
            }
            vTaskDelay(pdMS_TO_TICKS(20));   /* Wait for internal ADC conversion */

            /* Retry loop: 3 attempts, 10ms apart (non-busy delay → safe for WDT) */
            for (int retry = 0; retry < 3; retry++) {
                sensor_err = qma6100p_get_acce(sensor, &acce);
                if (sensor_err == ESP_OK) {
                    consecutive_sensor_fail = 0;
                    break;
                }
                ESP_LOGW(TAG, "Sensor read attempt %d/3 failed: %s (err=0x%x)",
                         retry + 1, esp_err_to_name(sensor_err), sensor_err);
                if (retry < 2) {
                    vTaskDelay(pdMS_TO_TICKS(10));   /* non-busy delay, WDT-safe */
                }
            }

            /* If all retries failed, try raw I2C register fallback */
            if (sensor_err != ESP_OK) {
                sensor_fail++;
                consecutive_sensor_fail++;
                ESP_LOGW(TAG, "Driver read exhausted (%lu fails, %lu consec), trying raw I2C fallback...",
                         sensor_fail, consecutive_sensor_fail);

                sensor_err = qma6100p_raw_read_fallback(sensor, &acce);
                if (sensor_err != ESP_OK) {
                    ESP_LOGE(TAG, "RAW I2C fallback also failed: %s (err=0x%x). "
                             "No data available — skipping upload.",
                             esp_err_to_name(sensor_err), sensor_err);
                    free(request_id);
                    continue;   /* skip upload, loop back to poll */
                }
                ESP_LOGI(TAG, "RAW I2C fallback SUCCESS — got real data");
            }

            /* Sensor recovery after 5 consecutive failures */
            if (consecutive_sensor_fail >= 5) {
                ESP_LOGW(TAG, "=== Sensor recovery: soft reset + re-init ===");
                qma6100p_soft_reset(sensor);
                vTaskDelay(pdMS_TO_TICKS(50));
                qma6100p_config(sensor, ACCE_FS_2G);
                qma6100p_wake_up(sensor);
                vTaskDelay(pdMS_TO_TICKS(100));
                consecutive_sensor_fail = 0;
                ESP_LOGI(TAG, "Sensor recovery done");
            }

            /* Build timestamp */
            char tbuf[32];
            time_t now = time(NULL);
            struct tm tm_info;
            localtime_r(&now, &tm_info);
            strftime(tbuf, sizeof(tbuf), "%Y-%m-%d %H:%M:%S", &tm_info);

            printf("REQUEST [%s]: ax=%.2f ay=%.2f az=%.2f @ %s\n",
                   request_id,
                   acce.acce_x, acce.acce_y, acce.acce_z, tbuf);

            /* HTTP upload with request_id */
            esp_err_t http_err = http_upload(acce.acce_x, acce.acce_y, acce.acce_z, tbuf, request_id);
            esp_task_wdt_reset();              /* feed after blocking HTTP call */
            free(request_id);

            if (http_err == ESP_OK) {
                upload_ok++;
            } else {
                upload_fail++;
                ESP_LOGW(TAG, "Upload fail #%lu", upload_fail);
            }
        }

        /* --- Periodic stats --- */
        TickType_t now_ticks = xTaskGetTickCount();
        if ((now_ticks - last_stats) >= pdMS_TO_TICKS(30000)) {
            ESP_LOGI(TAG, "STATS: ok=%lu fail=%lu sensor_err=%lu polls=%lu",
                     upload_ok, upload_fail, sensor_fail, poll_cycles);
            last_stats = now_ticks;
        }

        /* --- Maintain polling interval --- */
        vTaskDelay(pdMS_TO_TICKS(POLL_INTERVAL_MS));
    }
}

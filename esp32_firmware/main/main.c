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
#include "bsp/esp32_s3_eye.h"
#include "qma6100p.h"

/* ====== CONFIGURATION ====== */
#define WIFI_SSID           "431"
#define WIFI_PASSWORD       "88888888"
#define SERVER_URL          "http://10.1.41.43:5000/api/upload"
#define DEVICE_ID           "group01_esp32s3eye"

#define UPLOAD_INTERVAL_MS  200     /* 5 Hz = 200 ms between samples */
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

/* ----------------------- HTTP Upload ----------------------- */
static esp_err_t http_upload(float ax, float ay, float az, const char *time_str)
{
    char payload[256];
    int len = snprintf(payload, sizeof(payload),
             "{\"device_id\":\"%s\",\"ax\":%.2f,\"ay\":%.2f,\"az\":%.2f,\"device_time\":\"%s\"}",
             DEVICE_ID, ax, ay, az, time_str);
    if (len < 0 || len >= sizeof(payload)) {
        ESP_LOGE(TAG, "Payload overflow!");
        return ESP_ERR_NO_MEM;
    }

    esp_http_client_config_t config = {
        .url = SERVER_URL,
        .method = HTTP_METHOD_POST,
        .timeout_ms = HTTP_TIMEOUT_MS,
        .keep_alive_enable = true,
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
            ESP_LOGD(TAG, "HTTP 200 OK");
        } else {
            ESP_LOGW(TAG, "HTTP %d (non-200)", status);
        }
    } else {
        ESP_LOGE(TAG, "HTTP upload failed: %s (err=0x%x)", esp_err_to_name(err), err);
    }

    esp_http_client_cleanup(client);
    return err;
}

/* ----------------------- Main ----------------------- */
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

    uint8_t who = 0;
    if (qma6100p_get_deviceid(sensor, &who) == ESP_OK) {
        ESP_LOGI(TAG, "WHO_AM_I: 0x%02X", who);
    } else {
        ESP_LOGW(TAG, "WHO_AM_I read failed, sensor may need reset");
    }

    ESP_ERROR_CHECK(qma6100p_config(sensor, ACCE_FS_2G));
    qma6100p_wake_up(sensor);
    vTaskDelay(pdMS_TO_TICKS(100));
    ESP_LOGI(TAG, "Sensor ready, starting 5 Hz upload loop...");

    /* Register to the Task Watchdog so crashes get logged */
    /* TWDT is already initialized by ESP-IDF; just subscribe current task */
    ESP_ERROR_CHECK(esp_task_wdt_add(NULL));

    /* Stats counters */
    uint32_t upload_ok = 0;
    uint32_t upload_fail = 0;
    uint32_t sensor_fail = 0;
    uint32_t backoff_ms = 0;

    TickType_t last_stats = xTaskGetTickCount();

    while (1) {
        /* Feed the watchdog */
        esp_task_wdt_reset();

        /* --- Check Wi-Fi before uploading --- */
        if (!wifi_is_connected()) {
            ESP_LOGW(TAG, "Wi-Fi lost, waiting for reconnect...");
            /* Wait up to 10s for reconnection */
            if (!wifi_wait_connected(10000)) {
                ESP_LOGW(TAG, "Wi-Fi still down, retrying...");
                vTaskDelay(pdMS_TO_TICKS(2000));
                continue;
            }
            ESP_LOGI(TAG, "Wi-Fi reconnected!");
            backoff_ms = 0; /* reset backoff on reconnect */
        }

        /* --- Read sensor --- */
        qma6100p_acce_value_t acce = {0};
        esp_err_t sensor_err = qma6100p_get_acce(sensor, &acce);
        if (sensor_err != ESP_OK) {
            sensor_fail++;
            ESP_LOGW(TAG, "Sensor read error: %s (fail=%lu), retrying...",
                     esp_err_to_name(sensor_err), sensor_fail);
            /* Brief delay to avoid busy-loop on sensor failure */
            vTaskDelay(pdMS_TO_TICKS(50));
            continue;
        }

        /* --- Build timestamp (Beijing time, because TZ=CST-8) --- */
        char tbuf[32];
        time_t now = time(NULL);
        struct tm tm_info;
        localtime_r(&now, &tm_info);
        strftime(tbuf, sizeof(tbuf), "%Y-%m-%d %H:%M:%S", &tm_info);

        printf("UPLOAD [%lu]: ax=%.2f ay=%.2f az=%.2f @ %s\n",
               upload_ok + 1, acce.acce_x, acce.acce_y, acce.acce_z, tbuf);

        /* --- HTTP upload --- */
        esp_err_t http_err = http_upload(acce.acce_x, acce.acce_y, acce.acce_z, tbuf);
        esp_task_wdt_reset();              /* feed after blocking HTTP call */
        if (http_err == ESP_OK) {
            upload_ok++;
            backoff_ms = 0;  /* reset backoff on success */
        } else {
            upload_fail++;
            /* Exponential backoff: 1s, 2s, 4s, 8s, capped at 16s */
            if (backoff_ms == 0) backoff_ms = 1000;
            else backoff_ms = (backoff_ms * 2 > 16000) ? 16000 : backoff_ms * 2;
            ESP_LOGW(TAG, "Upload fail #%lu, backoff %lums",
                     upload_fail, backoff_ms);
            vTaskDelay(pdMS_TO_TICKS(backoff_ms));
            esp_task_wdt_reset();              /* feed after backoff delay */
            continue;
        }

        /* --- Periodic stats --- */
        TickType_t now_ticks = xTaskGetTickCount();
        if ((now_ticks - last_stats) >= pdMS_TO_TICKS(30000)) {
            ESP_LOGI(TAG, "STATS: ok=%lu fail=%lu sensor_err=%lu",
                     upload_ok, upload_fail, sensor_fail);
            last_stats = now_ticks;
        }

        /* --- Maintain 5 Hz rate --- */
        vTaskDelay(pdMS_TO_TICKS(UPLOAD_INTERVAL_MS));
    }
}

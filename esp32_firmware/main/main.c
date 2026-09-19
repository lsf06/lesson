/*
 * ESP32-S3-EYE QMA6100P Accelerometer + Wi-Fi HTTP Upload
 *
 * Stage 3: Semaphore-based Wi-Fi connect, SNTP time sync,
 *          POSTs JSON {device_id, ax, ay, az, device_time} every second.
 */

#include <stdio.h>
#include <string.h>
#include <time.h>
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
#include "bsp/esp32_s3_eye.h"
#include "qma6100p.h"

/* ====== CONFIGURATION ====== */
#define WIFI_SSID       "xiaolin"
#define WIFI_PASSWORD   "123456789"
#define SERVER_URL      "http://10.107.84.5:5000/api/upload"
#define DEVICE_ID       "group01_esp32s3eye"

static const char *TAG = "MAIN";

/* Event group bit: Wi-Fi got IPv4 address */
static EventGroupHandle_t s_wifi_evt;
#define WIFI_CONNECTED_BIT BIT0

static qma6100p_handle_t sensor = NULL;

/* ----------------------- Wi-Fi ----------------------- */
static void wifi_event_handler(void *arg, esp_event_base_t event_base,
                               int32_t event_id, void *event_data)
{
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        ESP_LOGW(TAG, "Wi-Fi disconnected, retrying...");
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

    wifi_config_t wifi_cfg = {0};
    strcpy((char *)wifi_cfg.sta.ssid, WIFI_SSID);
    strcpy((char *)wifi_cfg.sta.password, WIFI_PASSWORD);
    wifi_cfg.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_cfg));
    ESP_ERROR_CHECK(esp_wifi_start());

    ESP_LOGI(TAG, "Wi-Fi init done, connecting to %s...", WIFI_SSID);
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
    ESP_LOGI(TAG, "SNTP: time synced!");
}

static void sntp_init_time(void)
{
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
    snprintf(payload, sizeof(payload),
             "{\"device_id\":\"%s\",\"ax\":%.2f,\"ay\":%.2f,\"az\":%.2f,\"device_time\":\"%s\"}",
             DEVICE_ID, ax, ay, az, time_str);

    esp_http_client_config_t config = {
        .url = SERVER_URL,
        .method = HTTP_METHOD_POST,
        .timeout_ms = 3000,
    };
    esp_http_client_handle_t client = esp_http_client_init(&config);
    esp_http_client_set_header(client, "Content-Type", "application/json");
    esp_http_client_set_post_field(client, payload, strlen(payload));

    esp_err_t err = esp_http_client_perform(client);
    if (err == ESP_OK) {
        int status = esp_http_client_get_status_code(client);
        ESP_LOGD(TAG, "HTTP %d | %s", status, payload);
    } else {
        ESP_LOGE(TAG, "HTTP upload failed: %s", esp_err_to_name(err));
    }

    esp_http_client_cleanup(client);
    return err;
}

/* ----------------------- Main ----------------------- */
void app_main(void)
{
    ESP_LOGI(TAG, "=== ESP32-S3-EYE QMA6100P + Wi-Fi Upload ===");

    /* 1. Wi-Fi */
    wifi_init();
    ESP_LOGI(TAG, "Waiting for Wi-Fi connection...");
    if (!wifi_wait_connected(20000)) {
        ESP_LOGE(TAG, "Wi-Fi connect timeout, starting anyway...");
    }

    /* 2. SNTP time sync */
    sntp_init_time();

    /* 3. I2C + Sensor */
    ESP_ERROR_CHECK(bsp_i2c_init());
    i2c_master_bus_handle_t i2c_bus = bsp_i2c_get_handle();
    ESP_ERROR_CHECK(qma6100p_create(i2c_bus, QMA6100P_I2C_ADDRESS, &sensor));

    uint8_t who = 0;
    if (qma6100p_get_deviceid(sensor, &who) == ESP_OK) {
        ESP_LOGI(TAG, "WHO_AM_I: 0x%02X", who);
    }

    ESP_ERROR_CHECK(qma6100p_config(sensor, ACCE_FS_2G));
    qma6100p_wake_up(sensor);
    vTaskDelay(pdMS_TO_TICKS(100));
    ESP_LOGI(TAG, "Sensor ready, starting upload loop...");

    while (1) {
        qma6100p_acce_value_t acce = {0};
        if (qma6100p_get_acce(sensor, &acce) == ESP_OK) {
            /* Build timestamp */
            char tbuf[32];
            time_t now = time(NULL);
            struct tm *tm_info = localtime(&now);
            strftime(tbuf, sizeof(tbuf), "%Y-%m-%d %H:%M:%S", tm_info);

            printf("UPLOAD: %.2f, %.2f, %.2f @ %s\n",
                   acce.acce_x, acce.acce_y, acce.acce_z, tbuf);

            http_upload(acce.acce_x, acce.acce_y, acce.acce_z, tbuf);
        }
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
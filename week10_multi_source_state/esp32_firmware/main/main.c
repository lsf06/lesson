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
#include <assert.h>
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
#include "bsp/display.h"
#include "esp_lcd_panel_ops.h"
#include "qma6100p.h"
#include "esp_camera.h"
#include "driver/gpio.h"
#include "esp_random.h"

/* ====== CONFIGURATION ====== */
#define WIFI_SSID           "431"
#define WIFI_PASSWORD       "88888888"
#define SERVER_URL          "http://10.1.41.43:5000/api/upload"
#define SERVER_POLL_URL     "http://10.1.41.43:5000/api/pending_request?device_id=group01_esp32s3eye"
#define DEVICE_ID           "group01_esp32s3eye"

#define POLL_INTERVAL_MS    1000    /* poll server every 1 s for pending requests */
#define HTTP_TIMEOUT_MS     3000    /* 3 s HTTP timeout (WDT is 5s, leave margin) */

/* ====== Week3: Button + LCD Status + ACK ====== */
#define BUTTON_GPIO         GPIO_NUM_0
#define DEBOUNCE_MS         20
#define SERVER_TRIGGER_URL  "http://10.1.41.43:5000/api/trigger"
#define SERVER_CANCEL_URL   "http://10.1.41.43:5000/api/cancel"
#define TRIGGER_TIMEOUT_MS  5000

/* ====== Week7: OV2640 Camera ====== */
#define CAMERA_PIN_PWDN      -1
#define CAMERA_PIN_RESET     -1
#define CAMERA_PIN_XCLK      15
#define CAMERA_PIN_SIOD      4
#define CAMERA_PIN_SIOC      5
#define CAMERA_PIN_D7        16
#define CAMERA_PIN_D6        17
#define CAMERA_PIN_D5        18
#define CAMERA_PIN_D4        12
#define CAMERA_PIN_D3        10
#define CAMERA_PIN_D2        8
#define CAMERA_PIN_D1        9
#define CAMERA_PIN_D0        11
#define CAMERA_PIN_VSYNC     6
#define CAMERA_PIN_HREF      7
#define CAMERA_PIN_PCLK      13
#define CAPTURE_SERVER_URL   "http://10.1.41.43:5000/api/capture_image"

static const char *TAG = "MAIN";

/* Event group bit: Wi-Fi got IPv4 address */
static EventGroupHandle_t s_wifi_evt;
#define WIFI_CONNECTED_BIT  BIT0

static qma6100p_handle_t sensor = NULL;

/* ====== Week3: Trigger state machine ====== */
typedef enum {
    TRIG_STATE_IDLE = 0,           /* no active event */
    TRIG_STATE_LOCAL_TRIGGERED,    /* local trigger, waiting for remote ACK */
    TRIG_STATE_REMOTE_ACKED,       /* remote ACK received */
    TRIG_STATE_CANCELLED           /* cancelled by user or server */
} trigger_state_t;

static trigger_state_t trigger_state = TRIG_STATE_IDLE;
static char *current_event_id = NULL;     /* heap-allocated, NULL when idle */
static bool sntp_synced = false;          /* set by SNTP callback */

/* Messages for button_task 锟?trigger_http_task queue */
typedef enum {
    TRIG_MSG_TRIGGER = 0,   /* button pressed 锟?send /api/trigger */
    TRIG_MSG_CANCEL         /* button pressed again 锟?send /api/cancel */
} trigger_msg_type_t;

typedef struct {
    trigger_msg_type_t type;
    char *event_id;        /* valid for both TRIGGER and CANCEL; task frees it */
} trigger_msg_t;

static QueueHandle_t trigger_queue = NULL;
static esp_lcd_panel_handle_t lcd_panel = NULL;
static uint16_t color_buffer[BSP_LCD_H_RES * BSP_LCD_V_RES];   /* 240x240 RGB565 = 115200 bytes in BSS */

/* ====== Week3: Draw solid color on LCD (no LVGL) ====== */
static void draw_solid_color(uint16_t color)
{
    color = (color >> 8) | (color << 8);   /* swap bytes for big-endian LCD (BSP_LCD_BIGENDIAN=1) */
    for (int i = 0; i < BSP_LCD_H_RES * BSP_LCD_V_RES; i++) {
        color_buffer[i] = color;
    }
    esp_lcd_panel_draw_bitmap(lcd_panel, 0, 0, BSP_LCD_H_RES, BSP_LCD_V_RES, color_buffer);
    vTaskDelay(pdMS_TO_TICKS(20));         /* yield CPU to WiFi */
}

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
    sntp_synced = true;
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
static char *http_poll_request(char **action_out)
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

        ESP_LOGI(TAG, "Sending trigger to URL: %s", SERVER_TRIGGER_URL);
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
 *   4. Convert 14-bit raw 锟?g-value (sensitivity=4096 for 卤2g)
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
     *   - Driver divides by 4 to drop 2 LSBs, then by sensitivity (4096 for 卤2g)
     *   - Combined: raw_value = ((high<<8)|low) >> 2;  g = raw_value / 4096.0f
     */
    int16_t raw_x = (int16_t)(((uint16_t)data[1] << 8) | data[0]) / 4;
    int16_t raw_y = (int16_t)(((uint16_t)data[3] << 8) | data[2]) / 4;
    int16_t raw_z = (int16_t)(((uint16_t)data[5] << 8) | data[4]) / 4;

    acce->acce_x = raw_x / 4096.0f;
    acce->acce_y = raw_y / 4096.0f;
    acce->acce_z = raw_z / 4096.0f;

    ESP_LOGI(TAG, "Raw fallback OK: raw=(%d,%d,%d) 锟?g=(%.3f,%.3f,%.3f)",
             raw_x, raw_y, raw_z,
             acce->acce_x, acce->acce_y, acce->acce_z);

    return ESP_OK;
}

/* ====== Week3: Event ID Generation ====== */
static char *generate_event_id(void)
{
    static char buf[64];
    time_t now = time(NULL);
    struct tm tm_info;
    localtime_r(&now, &tm_info);
    uint16_t rnd = (uint16_t)(esp_random() & 0xFFFF);
    /* Use %%04u to bound output width; compiler won't warn on 64-byte buf */
    snprintf(buf, sizeof(buf), "%04u%02u%02u_%02u%02u%02u_%04X",
             (unsigned)(tm_info.tm_year + 1900) % 10000,
             (unsigned)(tm_info.tm_mon + 1) % 100,
             (unsigned)tm_info.tm_mday % 100,
             (unsigned)tm_info.tm_hour % 100,
             (unsigned)tm_info.tm_min % 100,
             (unsigned)tm_info.tm_sec % 100,
             (unsigned)rnd);
    return buf;
}

/* ====== Week3: HTTP POST /api/trigger ====== */
static bool http_post_trigger(const char *event_id)
{
    char payload[256];
    snprintf(payload, sizeof(payload),
             "{\"device_id\":\"%s\",\"event_id\":\"%s\"}",
             DEVICE_ID, event_id);

    esp_http_client_config_t config = {
        .url = SERVER_TRIGGER_URL,
        .method = HTTP_METHOD_POST,
        .timeout_ms = HTTP_TIMEOUT_MS,
        .keep_alive_enable = false,
        .disable_auto_redirect = true,
    };
    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (!client) {
        ESP_LOGE(TAG, "TRIGGER: HTTP client init failed");
        return false;
    }
    esp_http_client_set_header(client, "Content-Type", "application/json");
    esp_http_client_set_post_field(client, payload, strlen(payload));

    ESP_LOGI(TAG, "Sending trigger to URL: %s", SERVER_TRIGGER_URL);

    /* Use open/fetch_headers/read/close pattern to guarantee
     * response body is properly buffered and readable. */
    esp_err_t err = esp_http_client_open(client, strlen(payload));
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "TRIGGER: HTTP open failed: %s (0x%x)", esp_err_to_name(err), err);
        esp_http_client_cleanup(client);
        return false;
    }

    int wlen = esp_http_client_write(client, payload, strlen(payload));
    if (wlen < 0) {
        ESP_LOGE(TAG, "TRIGGER: HTTP write failed");
        esp_http_client_close(client);
        esp_http_client_cleanup(client);
        return false;
    }

    int content_length = esp_http_client_fetch_headers(client);
    if (content_length < 0) {
        ESP_LOGE(TAG, "TRIGGER: fetch_headers failed (len=%d)", content_length);
        esp_http_client_close(client);
        esp_http_client_cleanup(client);
        return false;
    }

    int status = esp_http_client_get_status_code(client);
    bool ack = false;
    if (status == 200 && content_length > 0 && content_length < 512) {
        char *resp = malloc(content_length + 1);
        if (resp) {
            int read_len = esp_http_client_read(client, resp, content_length);
            if (read_len > 0) {
                resp[read_len] = '\0';
                ESP_LOGI(TAG, "TRIGGER response: %s", resp);
                cJSON *root = cJSON_Parse(resp);
                if (root) {
                    cJSON *aj = cJSON_GetObjectItem(root, "ack");
                    ack = cJSON_IsBool(aj) && cJSON_IsTrue(aj);
                    cJSON_Delete(root);
                }
            } else {
                ESP_LOGW(TAG, "TRIGGER: read returned %d (expected %d)", read_len, content_length);
            }
            free(resp);
        }
    } else if (status != 200) {
        ESP_LOGW(TAG, "TRIGGER HTTP %d", status);
    }

    esp_http_client_close(client);
    esp_http_client_cleanup(client);
    return ack;
}

/* ====== Week3: HTTP POST /api/cancel ====== */
static bool http_post_cancel(const char *event_id)
{
    char payload[256];
    snprintf(payload, sizeof(payload),
             "{\"device_id\":\"%s\",\"event_id\":\"%s\"}",
             DEVICE_ID, event_id);

    esp_http_client_config_t config = {
        .url = SERVER_CANCEL_URL,
        .method = HTTP_METHOD_POST,
        .timeout_ms = HTTP_TIMEOUT_MS,
        .keep_alive_enable = false,
        .disable_auto_redirect = true,
    };
    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (!client) {
        ESP_LOGE(TAG, "CANCEL: HTTP client init failed");
        return false;
    }
    esp_http_client_set_header(client, "Content-Type", "application/json");
    esp_http_client_set_post_field(client, payload, strlen(payload));

    ESP_LOGI(TAG, "Sending cancel to URL: %s", SERVER_CANCEL_URL);

    esp_err_t err = esp_http_client_open(client, strlen(payload));
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "CANCEL: HTTP open failed: %s (0x%x)", esp_err_to_name(err), err);
        esp_http_client_cleanup(client);
        return false;
    }

    int wlen = esp_http_client_write(client, payload, strlen(payload));
    if (wlen < 0) {
        ESP_LOGE(TAG, "CANCEL: HTTP write failed");
        esp_http_client_close(client);
        esp_http_client_cleanup(client);
        return false;
    }

    int content_length = esp_http_client_fetch_headers(client);
    if (content_length < 0) {
        ESP_LOGE(TAG, "CANCEL: fetch_headers failed (len=%d)", content_length);
        esp_http_client_close(client);
        esp_http_client_cleanup(client);
        return false;
    }

    int status = esp_http_client_get_status_code(client);
    if (status == 200) {
        ESP_LOGI(TAG, "CANCEL HTTP 200 OK");
    } else {
        ESP_LOGW(TAG, "CANCEL HTTP %d", status);
    }

    esp_http_client_close(client);
    esp_http_client_cleanup(client);
    return (status == 200);
}

/* ====== Week3: Button Task (GPIO + Debounce + LCD + Queue Post) ======
 * Real-time task 锟?never blocks on network.
 * - Press 锟?LCD shows LOCAL TRIGGERED 锟?post TRIGGER msg to http queue
 * - Press again 锟?LCD shows IDLE 锟?post CANCEL msg to http queue
 */
static void button_task(void *pvParameters)
{
    bool last_stable = true;   /* GPIO0 pulled high = not pressed */
    int debounce_cnt = 0;

    while (1) {
        bool raw = (gpio_get_level(BUTTON_GPIO) == 0);  /* true = pressed */

        if (raw == last_stable) {
            debounce_cnt = 0;
        } else {
            debounce_cnt++;
            if (debounce_cnt >= (DEBOUNCE_MS / 10)) {
                last_stable = raw;

                if (raw) {  /* confirmed press */
                    if (trigger_state == TRIG_STATE_IDLE) {
                        /* IDLE 锟?LOCAL_TRIGGERED: update LCD immediately */
                        trigger_state = TRIG_STATE_LOCAL_TRIGGERED;
                        draw_solid_color(0xF800);  /* RED */

                        char *eid = strdup(generate_event_id());
                        current_event_id = eid;
                        ESP_LOGI(TAG, "BUTTON: TRIGGER event_id=%s LCD=TRIGGERED", eid);
                        printf("LOCAL_TRIGGERED event_id=%s\n", eid);

                        trigger_msg_t msg = {
                            .type = TRIG_MSG_TRIGGER,
                            .event_id = strdup(eid)
                        };
                        xQueueSend(trigger_queue, &msg, 0);
                    } else {
                        /* LOCAL_TRIGGERED or REMOTE_ACKED 锟?IDLE (CANCEL)
                         * LCD updated immediately */
                        ESP_LOGI(TAG, "BUTTON: CANCEL event_id=%s LCD=IDLE",
                                 current_event_id ? current_event_id : "null");
                        printf("CANCEL_TRIGGERED event_id=%s\n",
                               current_event_id ? current_event_id : "null");

                        trigger_msg_t msg = {
                            .type = TRIG_MSG_CANCEL,
                            .event_id = current_event_id ? strdup(current_event_id) : NULL
                        };
                        xQueueSend(trigger_queue, &msg, 0);

                        if (current_event_id) {
                            free(current_event_id);
                            current_event_id = NULL;
                        }
                        trigger_state = TRIG_STATE_IDLE;
                        draw_solid_color(0xFFFF);  /* WHITE */
                    }
                }
                debounce_cnt = 0;
            }
        }
        vTaskDelay(pdMS_TO_TICKS(10));  /* 10ms polling 锟?100 Hz */
    }
}

/* ====== Week3: HTTP Task (consumes queue, handles POST/ACK/CANCEL) ======
 * Independent task 锟?blocking HTTP calls are isolated here.
 * CANCEL always takes priority over a pending TRIGGER.
 */
static void trigger_http_task(void *pvParameters)
{
    trigger_msg_t msg;

    while (1) {
        if (xQueueReceive(trigger_queue, &msg, portMAX_DELAY) != pdTRUE) {
            continue;
        }

        if (msg.type == TRIG_MSG_TRIGGER && msg.event_id) {
            /* Check if a newer CANCEL is already queued */
            trigger_msg_t peek;
            if (xQueuePeek(trigger_queue, &peek, 0) == pdTRUE &&
                peek.type == TRIG_MSG_CANCEL) {
                ESP_LOGI(TAG, "HTTP: skip TRIGGER (CANCEL queued)");
                free(msg.event_id);
                continue;
            }

            ESP_LOGI(TAG, "HTTP: POST /api/trigger event_id=%s", msg.event_id);
            bool ack = http_post_trigger(msg.event_id);

            /* Re-check for cancel that arrived during HTTP */
            if (xQueuePeek(trigger_queue, &peek, 0) == pdTRUE &&
                peek.type == TRIG_MSG_CANCEL) {
                ESP_LOGI(TAG, "HTTP: ACK discarded (CANCEL arrived during HTTP)");
                free(msg.event_id);
                continue;
            }

            if (ack) {
                trigger_state = TRIG_STATE_REMOTE_ACKED;
                draw_solid_color(0x07E0);  /* GREEN */
                ESP_LOGI(TAG, "HTTP: REMOTE_ACKED event_id=%s", msg.event_id);
                printf("REMOTE_ACKED event_id=%s\n", msg.event_id);
            } else {
                trigger_state = TRIG_STATE_CANCELLED;
                draw_solid_color(0xFFE0);  /* YELLOW */
                ESP_LOGW(TAG, "HTTP: NO_ACK event_id=%s", msg.event_id);
                printf("NETWORK_TIMEOUT_NO_ACK event_id=%s\n", msg.event_id);
            }
        } else if (msg.type == TRIG_MSG_CANCEL) {
            ESP_LOGI(TAG, "HTTP: POST /api/cancel event_id=%s",
                     msg.event_id ? msg.event_id : "null");
            if (msg.event_id) {
                http_post_cancel(msg.event_id);
            }
        }

        if (msg.event_id) {
            free(msg.event_id);
        }
    }
}

static esp_err_t camera_init(void)
{
    ESP_LOGI(TAG, "camera_init() start");
    camera_config_t config = {
        .pin_pwdn  = CAMERA_PIN_PWDN,
        .pin_reset = CAMERA_PIN_RESET,
        .pin_xclk = CAMERA_PIN_XCLK,
        .pin_sccb_sda = -1,
        .pin_sccb_scl = -1,
        .sccb_i2c_port = 1,
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
/* ----------------------- Poll Service Task ----------------------- */
static void poll_service(void *pvParameters)
{
    ESP_LOGI(TAG, "poll_service started");
    esp_task_wdt_add(NULL);  /* Subscribe to system WDT (5s default, HTTP=3s) */
    ESP_LOGI(TAG, "poll_svc: subscribed to WDT");
    esp_task_wdt_reset();

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
        esp_task_wdt_reset();  /* Reset WDT before potential 5s HTTP timeout */
        char *action = NULL;
        char *request_id = http_poll_request(&action);
        poll_cycles++;

        if (request_id) {
            /* ====== Week7: Check if action is "capture" ====== */
            if (action && strcmp(action, "capture") == 0) {
                ESP_LOGI(TAG, "Action = capture, taking photo...");
                capture_and_upload();
                free(action);
                free(request_id);
                vTaskDelay(pdMS_TO_TICKS(POLL_INTERVAL_MS));
                continue;
            }
            free(action);
            action = NULL;

            /* ---- Sensor data collection (original logic) ---- */
            qma6100p_acce_value_t acce = {0};
            esp_err_t sensor_err = ESP_FAIL;

            esp_err_t wake_r = qma6100p_wake_up(sensor);
            if (wake_r != ESP_OK) {
                ESP_LOGW(TAG, "Pre-read wake_up failed: %s (err=0x%x)", esp_err_to_name(wake_r), wake_r);
            }
            vTaskDelay(pdMS_TO_TICKS(20));

            for (int retry = 0; retry < 3; retry++) {
                sensor_err = qma6100p_get_acce(sensor, &acce);
                if (sensor_err == ESP_OK) {
                    consecutive_sensor_fail = 0;
                    break;
                }
                ESP_LOGW(TAG, "Sensor read attempt %d/3 failed: %s (err=0x%x)",
                         retry + 1, esp_err_to_name(sensor_err), sensor_err);
                if (retry < 2) {
                    vTaskDelay(pdMS_TO_TICKS(10));
                }
            }

            if (sensor_err != ESP_OK) {
                sensor_fail++;
                consecutive_sensor_fail++;
                ESP_LOGW(TAG, "Driver read exhausted (%lu fails, %lu consec), trying raw I2C fallback...",
                         sensor_fail, consecutive_sensor_fail);
                sensor_err = qma6100p_raw_read_fallback(sensor, &acce);
                if (sensor_err != ESP_OK) {
                    ESP_LOGE(TAG, "RAW I2C fallback also failed: %s (err=0x%x). "
                             "No data available, skipping upload.",
                             esp_err_to_name(sensor_err), sensor_err);
                    free(request_id);
                    vTaskDelay(pdMS_TO_TICKS(POLL_INTERVAL_MS));
                    continue;
                }
                ESP_LOGI(TAG, "RAW I2C fallback SUCCESS, got real data");
            }

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

            char tbuf[32];
            time_t now = time(NULL);
            struct tm tm_info;
            localtime_r(&now, &tm_info);
            strftime(tbuf, sizeof(tbuf), "%Y-%m-%d %H:%M:%S", &tm_info);

            printf("REQUEST [%s]: ax=%.2f ay=%.2f az=%.2f @ %s\n",
                   request_id, acce.acce_x, acce.acce_y, acce.acce_z, tbuf);

            esp_err_t http_err = http_upload(acce.acce_x, acce.acce_y, acce.acce_z, tbuf, request_id);
            esp_task_wdt_reset();
            free(request_id);

            if (http_err == ESP_OK) {
                upload_ok++;
            } else {
                upload_fail++;
                ESP_LOGW(TAG, "Upload fail #%lu", upload_fail);
            }
        }

        TickType_t now_ticks = xTaskGetTickCount();
        if ((now_ticks - last_stats) >= pdMS_TO_TICKS(30000)) {
            ESP_LOGI(TAG, "STATS: ok=%lu fail=%lu sensor_err=%lu polls=%lu",
                     upload_ok, upload_fail, sensor_fail, poll_cycles);
            last_stats = now_ticks;
        }

        vTaskDelay(pdMS_TO_TICKS(POLL_INTERVAL_MS));
    }
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

    /* ====== Week7: Initialize OV2640 camera (reuse I2C bus from bsp_i2c_init) ====== */
    {
        esp_err_t cam_err = camera_init();
        if (cam_err != ESP_OK) {
            ESP_LOGW(TAG, "Camera init warning: %s", esp_err_to_name(cam_err));
        }
    }

    ESP_LOGI(TAG, "Sensor ready, initializing LCD...");

    /* ====== Week3: LCD init (bare-metal, no LVGL) ====== */
    {
        bsp_display_config_t disp_cfg = {
            .max_transfer_sz = BSP_LCD_H_RES * BSP_LCD_V_RES * sizeof(uint16_t),
        };
        esp_lcd_panel_io_handle_t io_handle = NULL;
        ESP_ERROR_CHECK(bsp_display_new(&disp_cfg, &lcd_panel, &io_handle));
        ESP_ERROR_CHECK(esp_lcd_panel_disp_on_off(lcd_panel, true));
        ESP_ERROR_CHECK(bsp_display_backlight_on());
        
        /* Show initial IDLE state (white screen) */
        draw_solid_color(0xFFFF);
        
        ESP_LOGI(TAG, "LCD ready (bare-metal, no LVGL)");
    }

    /* ====== Week3: Button GPIO init ====== */
    {
        gpio_config_t io_conf = {
            .intr_type = GPIO_INTR_DISABLE,
            .mode = GPIO_MODE_INPUT,
            .pin_bit_mask = (1ULL << BUTTON_GPIO),
            .pull_up_en = GPIO_PULLUP_ENABLE,
            .pull_down_en = GPIO_PULLDOWN_DISABLE,
        };
        gpio_config(&io_conf);
    }

    /* Create message queue (depth 5) */
    trigger_queue = xQueueCreate(5, sizeof(trigger_msg_t));

    /* Create Week3 tasks with return-value checks */
    {
        BaseType_t ret;
        ret = xTaskCreate(button_task, "button", 8192, NULL, 6, NULL);
        if (ret != pdPASS) {
            ESP_LOGE(TAG, "FATAL: button_task creation failed! (err=%d, heap=%lu)", ret, esp_get_free_heap_size());
        }

        ret = xTaskCreate(trigger_http_task, "trig_http", 8192, NULL, 5, NULL);
        if (ret != pdPASS) {
            ESP_LOGE(TAG, "FATAL: trigger_http_task creation failed! (err=%d, heap=%lu)", ret, esp_get_free_heap_size());
        }

        ret = xTaskCreate(poll_service, "poll_svc", 8192, NULL, 4, NULL);
        if (ret != pdPASS) {
            ESP_LOGE(TAG, "FATAL: poll_service creation failed! (err=%d, heap=%lu)", ret, esp_get_free_heap_size());
        }
    }
    ESP_LOGI(TAG, "Week3: button_task(8192) + trigger_http_task(8192) + poll_svc created");

    ESP_LOGI(TAG, "All tasks created, app_main exiting");
    vTaskDelete(NULL);
}
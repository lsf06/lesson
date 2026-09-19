/*
 * ESP32-S3-EYE QMA6100P Accelerometer + Wi-Fi HTTP Upload
 *
 * Week 2: Polling-based on-demand capture.
 * Device polls /api/fetch_command every 2s; on command, captures & uploads with request_id.
 *
 * Week 3: Added OV2640 camera capture with HTTP multipart upload.
 * - Camera uses esp_video DVP interface + JPEG hardware encoder
 * - Photos uploaded to /api/upload_photo with IMU fusion data
 */

#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <time.h>
#include <sys/fcntl.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <errno.h>
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
#include "esp_timer.h"
#include "cJSON.h"
#include "bsp/esp32_s3_eye.h"
#include "qma6100p.h"
#include "esp_video_device.h"
#include "esp_video_init.h"
#include "esp_video_ioctl.h"
#include "linux/videodev2.h"

/* ====== CONFIGURATION ====== */
#define WIFI_SSID       "xiaolin"
#define WIFI_PASSWORD   "123456789"
#define SERVER_URL      "http://10.107.84.5:5000/api/upload"
#define FETCH_URL       "http://10.107.84.5:5000/api/fetch_command?device_id=group01_esp32s3eye"
#define PHOTO_UPLOAD_URL "http://10.107.84.5:5000/api/upload_photo"
#define DEVICE_ID       "group01_esp32s3eye"

/* Camera Configuration */
#define CAMERA_RESOLUTION_VGA    // 640x480 (OV2640 native)
#define JPEG_QUALITY      30     // JPEG quality (1-100)
#define CAMERA_XCLK_FREQ  16000000  // 16MHz

static const char *TAG = "MAIN";
static const char *CAM_TAG = "CAMERA";

/* Event group bit: Wi-Fi got IPv4 address */
static EventGroupHandle_t s_wifi_evt;
#define WIFI_CONNECTED_BIT BIT0

static qma6100p_handle_t sensor = NULL;

/* Camera handles */
static int g_cap_fd = -1;        // Capture device file descriptor
static int g_jpeg_fd = -1;       // JPEG encoder file descriptor
static uint8_t *g_cap_buffer = NULL;  // Capture buffer
static uint8_t *g_jpeg_buffer = NULL; // JPEG output buffer
static bool g_camera_initialized = false;

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
static esp_err_t http_upload(float ax, float ay, float az,
                              const char *time_str, const char *request_id)
{
    char payload[300];
    printf("UPL_BEG: rid=%s\n", request_id ? request_id : "NULL");
    if (request_id) {
        snprintf(payload, sizeof(payload),
                 "{\"device_id\":\"%s\",\"ax\":%.2f,\"ay\":%.2f,\"az\":%.2f,"
                 "\"device_time\":\"%s\",\"request_id\":\"%s\"}",
                 DEVICE_ID, ax, ay, az, time_str, request_id);
    } else {
        snprintf(payload, sizeof(payload),
                 "{\"device_id\":\"%s\",\"ax\":%.2f,\"ay\":%.2f,\"az\":%.2f,"
                 "\"device_time\":\"%s\"}",
                 DEVICE_ID, ax, ay, az, time_str);
    }

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
        printf("UPLOAD: rid=%s len=%d | status=%d\n",
               request_id ? request_id : "NULL",
               (int)strlen(payload), status);
    } else {
        printf("HTTP_UPLOAD FAILED: %s\n", esp_err_to_name(err));
        ESP_LOGE(TAG, "HTTP upload failed: %s", esp_err_to_name(err));
    }

    esp_http_client_cleanup(client);
    return err;
}

/* ----------------------- HTTP Fetch Command ----------------------- */
static char *fetch_command(void)
{
    esp_http_client_config_t config = {
        .url = FETCH_URL,
        .method = HTTP_METHOD_GET,
        .timeout_ms = 3000,
    };
    esp_http_client_handle_t client = esp_http_client_init(&config);
    char *req_id = NULL;

    esp_err_t err = esp_http_client_open(client, 0);
    if (err != ESP_OK) {
        printf("FETCH_OPEN: FAIL %s\n", esp_err_to_name(err));
        esp_http_client_cleanup(client);
        return NULL;
    }

    int clen = esp_http_client_fetch_headers(client);
    printf("FETCH_HDR: content-length=%d status=%d\n",
           clen, esp_http_client_get_status_code(client));

    if (esp_http_client_get_status_code(client) == 200 && clen > 0) {
        char buf[256] = {0};
        int total = 0;
        while (total < clen) {
            int r = esp_http_client_read(client, buf + total, clen - total);
            printf("FETCH_READ: asked=%d got=%d\n", clen - total, r);
            if (r <= 0) break;
            total += r;
        }
        buf[total] = '\0';
        printf("FETCH_BODY: [%s]\n", buf);

        if (total > 0) {
            cJSON *root = cJSON_Parse(buf);
            if (root) {
                printf("FETCH_JSON: OK\n");
                cJSON *cmd = cJSON_GetObjectItem(root, "command");
                if (cJSON_IsString(cmd) && strcmp(cmd->valuestring, "capture") == 0) {
                    printf("FETCH_CMD: capture\n");
                    cJSON *rid = cJSON_GetObjectItem(root, "request_id");
                    if (cJSON_IsString(rid)) {
                        printf("FETCH_RID: %s\n", rid->valuestring);
                        req_id = strdup(rid->valuestring);
                    }
                }
                cJSON_Delete(root);
            } else {
                printf("FETCH_JSON: PARSE FAILED\n");
            }
        }
    }

    esp_http_client_close(client);
    esp_http_client_cleanup(client);
    return req_id;
}

static char *pending_req_id = NULL;

/* ----------------------- Camera ----------------------- */

/**
 * @brief Initialize camera (DVP + JPEG encoder)
 */
static esp_err_t camera_init(void)
{
    if (g_camera_initialized) {
        ESP_LOGI(CAM_TAG, "Camera already initialized");
        return ESP_OK;
    }

    ESP_LOGI(CAM_TAG, "Initializing camera...");

    // Step 1: Initialize BSP camera
    bsp_camera_cfg_t cam_cfg = {0};
    esp_err_t ret = bsp_camera_start(&cam_cfg);
    if (ret != ESP_OK) {
        ESP_LOGE(CAM_TAG, "BSP camera start failed: %s", esp_err_to_name(ret));
        return ret;
    }

    // Step 2: Open capture device
    g_cap_fd = open(ESP_VIDEO_DVP_DEVICE_NAME, O_RDWR, 0);
    if (g_cap_fd < 0) {
        ESP_LOGE(CAM_TAG, "Failed to open capture device: %s", strerror(errno));
        return ESP_FAIL;
    }
    ESP_LOGI(CAM_TAG, "Opened capture device: %s (fd=%d)", ESP_VIDEO_DVP_DEVICE_NAME, g_cap_fd);

    // Step 3: Set sensor format (VGA, JPEG)
    // Note: OV2640 DVP driver on ESP32-S3-EYE rejects QVGA (320x240).
    // Use VGA (640x480) which is the sensor's native supported size.
    struct v4l2_format fmt;
    memset(&fmt, 0, sizeof(fmt));
    fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    fmt.fmt.pix.width = 640;
    fmt.fmt.pix.height = 480;
    fmt.fmt.pix.pixelformat = V4L2_PIX_FMT_JPEG;
    fmt.fmt.pix.field = V4L2_FIELD_ANY;

    if (ioctl(g_cap_fd, VIDIOC_S_FMT, &fmt) < 0) {
        ESP_LOGE(CAM_TAG, "Failed to set format: %s", strerror(errno));
        close(g_cap_fd);
        g_cap_fd = -1;
        return ESP_FAIL;
    }
    ESP_LOGI(CAM_TAG, "Format set: %dx%d JPEG", (int)fmt.fmt.pix.width, (int)fmt.fmt.pix.height);

    // Step 4: (removed) Hardware JPEG encoder is not available on ESP32-S3,
    // but the OV2640 sensor outputs JPEG directly via its on-board codec.
    // No separate JPEG encoder device is needed.

    g_camera_initialized = true;
    ESP_LOGI(CAM_TAG, "Camera initialized successfully");
    return ESP_OK;
}

/**
 * @brief Upload photo with IMU data via HTTP multipart
 */
static esp_err_t http_upload_photo(const uint8_t *jpg_data, size_t jpg_len,
                                   const char *req_id,
                                   float ax, float ay, float az)
{
    if (!jpg_data || jpg_len == 0) {
        ESP_LOGE(TAG, "Invalid JPEG data");
        return ESP_ERR_INVALID_ARG;
    }

    char boundary[64];
    snprintf(boundary, sizeof(boundary), "----ESP32PhotoBoundary%08lX", (uint32_t)esp_timer_get_time());

    char json_meta[256];
    snprintf(json_meta, sizeof(json_meta),
             "{\"device_id\":\"%s\",\"request_id\":\"%s\","
             "\"ax\":%.3f,\"ay\":%.3f,\"az\":%.3f,\"filename\":\"photo_%s.jpg\"}",
             DEVICE_ID, req_id ? req_id : "manual",
             ax, ay, az, req_id ? req_id : "manual");

    ESP_LOGI(TAG, "Uploading photo: %zu bytes, meta: %s", jpg_len, json_meta);

    esp_http_client_config_t cfg = {
        .url = PHOTO_UPLOAD_URL,
        .method = HTTP_METHOD_POST,
        .timeout_ms = 15000,
    };
    esp_http_client_handle_t client = esp_http_client_init(&cfg);

    char content_type[128];
    snprintf(content_type, sizeof(content_type), "multipart/form-data; boundary=%s", boundary);
    esp_http_client_set_header(client, "Content-Type", content_type);

    // Build multipart body
    size_t hdr1_size = strlen("--") + strlen(boundary) + strlen("\r\n") +
                       strlen("Content-Disposition: form-data; name=\"metadata\"") + strlen("\r\n\r\n") +
                       strlen(json_meta) + strlen("\r\n");
    size_t hdr2_size = strlen("--") + strlen(boundary) + strlen("\r\n") +
                       strlen("Content-Disposition: form-data; name=\"photo\"; filename=\"photo.jpg\"\r\n") +
                       strlen("Content-Type: image/jpeg\r\n\r\n");
    size_t tail_size = strlen("\r\n--") + strlen(boundary) + strlen("--\r\n");
    size_t total_len = hdr1_size + hdr2_size + jpg_len + tail_size;

    uint8_t *body = (uint8_t *)malloc(total_len);
    if (!body) {
        ESP_LOGE(TAG, "Failed to allocate upload body");
        esp_http_client_cleanup(client);
        return ESP_ERR_NO_MEM;
    }

    uint8_t *p = body;
    p += sprintf((char *)p, "--%s\r\n", boundary);
    p += sprintf((char *)p, "Content-Disposition: form-data; name=\"metadata\"\r\n\r\n");
    p += sprintf((char *)p, "%s\r\n", json_meta);
    p += sprintf((char *)p, "--%s\r\n", boundary);
    p += sprintf((char *)p, "Content-Disposition: form-data; name=\"photo\"; filename=\"photo.jpg\"\r\n");
    p += sprintf((char *)p, "Content-Type: image/jpeg\r\n\r\n");
    memcpy(p, jpg_data, jpg_len);
    p += jpg_len;
    p += sprintf((char *)p, "\r\n--%s--\r\n", boundary);

    size_t actual_len = (size_t)(p - body);
    ESP_LOGI(TAG, "Body built: %zu bytes", actual_len);

    esp_http_client_set_post_field(client, (const char *)body, actual_len);

    esp_err_t err = esp_http_client_perform(client);
    if (err == ESP_OK) {
        int status = esp_http_client_get_status_code(client);
        ESP_LOGI(TAG, "Photo upload status: %d", status);
        if (status != 200) {
            err = ESP_FAIL;
        }
    } else {
        ESP_LOGE(TAG, "Photo upload failed: %s", esp_err_to_name(err));
    }

    free(body);
    esp_http_client_close(client);
    esp_http_client_cleanup(client);

    return err;
}

/**
 * @brief Capture a single JPEG frame from camera
 * @param out_data  Pointer to receive allocated buffer (caller must free)
 * @param out_len   Pointer to receive frame size
 * @return ESP_OK on success
 */
static esp_err_t camera_capture_frame(uint8_t **out_data, size_t *out_len)
{
    if (g_cap_fd < 0) {
        ESP_LOGE(CAM_TAG, "Camera not initialized (fd=%d)", g_cap_fd);
        return ESP_ERR_INVALID_STATE;
    }

    ESP_LOGI(CAM_TAG, "Starting single-frame capture on fd=%d", g_cap_fd);

    // Step 1: Request buffers
    struct v4l2_requestbuffers reqbuf;
    memset(&reqbuf, 0, sizeof(reqbuf));
    reqbuf.count = 1;
    reqbuf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    reqbuf.memory = V4L2_MEMORY_MMAP;

    if (ioctl(g_cap_fd, VIDIOC_REQBUFS, &reqbuf) < 0) {
        ESP_LOGE(CAM_TAG, "REQBUFS failed: %s", strerror(errno));
        return ESP_FAIL;
    }

    // Step 2: Query and map buffer
    struct v4l2_buffer buf;
    memset(&buf, 0, sizeof(buf));
    buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    buf.memory = V4L2_MEMORY_MMAP;
    buf.index = 0;

    if (ioctl(g_cap_fd, VIDIOC_QUERYBUF, &buf) < 0) {
        ESP_LOGE(CAM_TAG, "QUERYBUF failed: %s", strerror(errno));
        goto cleanup_reqbufs;
    }

    uint8_t *cap_buf = mmap(NULL, buf.length, PROT_READ | PROT_WRITE, MAP_SHARED, g_cap_fd, buf.m.offset);
    if (cap_buf == MAP_FAILED) {
        ESP_LOGE(CAM_TAG, "mmap failed: %s", strerror(errno));
        goto cleanup_reqbufs;
    }
    ESP_LOGI(CAM_TAG, "Buffer mapped: %lu bytes", (unsigned long)buf.length);

    // Step 3: Queue buffer
    memset(&buf, 0, sizeof(buf));
    buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    buf.memory = V4L2_MEMORY_MMAP;
    buf.index = 0;

    if (ioctl(g_cap_fd, VIDIOC_QBUF, &buf) < 0) {
        ESP_LOGE(CAM_TAG, "QBUF failed: %s", strerror(errno));
        goto cleanup_mmap;
    }

    // Step 4: Start streaming
    int stream_type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    if (ioctl(g_cap_fd, VIDIOC_STREAMON, &stream_type) < 0) {
        ESP_LOGE(CAM_TAG, "STREAMON failed: %s", strerror(errno));
        goto cleanup_mmap;
    }

    // Step 5: Dequeue frame
    memset(&buf, 0, sizeof(buf));
    buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    buf.memory = V4L2_MEMORY_MMAP;

    if (ioctl(g_cap_fd, VIDIOC_DQBUF, &buf) < 0) {
        ESP_LOGE(CAM_TAG, "DQBUF failed: %s", strerror(errno));
        goto cleanup_streamoff;
    }

    size_t frame_size = buf.bytesused;
    ESP_LOGI(CAM_TAG, "Frame dequeued: %zu bytes", frame_size);

    // Step 6: Allocate persistent buffer and copy data
    uint8_t *jpeg_buf = (uint8_t *)malloc(frame_size);
    if (!jpeg_buf) {
        ESP_LOGE(CAM_TAG, "malloc failed for %zu bytes", frame_size);
        goto cleanup_streamoff;
    }
    memcpy(jpeg_buf, cap_buf, frame_size);

    // Step 7: Stop streaming and cleanup
    stream_type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    ioctl(g_cap_fd, VIDIOC_STREAMOFF, &stream_type);
    munmap(cap_buf, buf.length);

    // Return data to caller
    *out_data = jpeg_buf;
    *out_len = frame_size;

    ESP_LOGI(CAM_TAG, "Frame captured successfully: %zu bytes", frame_size);
    return ESP_OK;

cleanup_streamoff:
    stream_type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    ioctl(g_cap_fd, VIDIOC_STREAMOFF, &stream_type);
cleanup_mmap:
    munmap(cap_buf, buf.length);
cleanup_reqbufs:
    // No need to explicitly free reqbufs; next REQBUFS(0) will do it
    return ESP_FAIL;
}

/**
 * @brief Capture photo with IMU fusion and upload
 */
static esp_err_t capture_and_upload_photo(const char *req_id)
{
    ESP_LOGI(TAG, "=== Capturing Photo ===");

    // Step 1: Initialize camera if needed
    esp_err_t ret = camera_init();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Camera init failed: %s", esp_err_to_name(ret));
        return ret;
    }

    // Step 2: Read IMU data (snapshot at capture time)
    qma6100p_acce_value_t acce = {0};
    ret = qma6100p_get_acce(sensor, &acce);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to read IMU data");
        return ret;
    }

    int64_t imu_timestamp = esp_timer_get_time();
    ESP_LOGI(TAG, "IMU snapshot: ax=%.3f ay=%.3f az=%.3f (timestamp: %lld us)",
             acce.acce_x, acce.acce_y, acce.acce_z, imu_timestamp);

    // Step 3: Capture JPEG frame into a new allocated buffer
    uint8_t *jpg_data = NULL;
    size_t jpg_len = 0;

    ret = camera_capture_frame(&jpg_data, &jpg_len);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Frame capture failed: %s", esp_err_to_name(ret));
        return ret;
    }

    ESP_LOGI(TAG, "Captured JPEG: %zu bytes", jpg_len);

    // Step 4: Upload photo with IMU fusion data
    ret = http_upload_photo(jpg_data, jpg_len, req_id,
                            acce.acce_x, acce.acce_y, acce.acce_z);
    
    // Always free the buffer after upload (success or failure)
    free(jpg_data);

    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Photo upload failed");
        return ret;
    }

    ESP_LOGI(TAG, "=== Photo Upload Complete ===");
    return ESP_OK;
}

/* ----------------------- Main ----------------------- */
void app_main(void)
{
    ESP_LOGI(TAG, "=== ESP32-S3-EYE QMA6100P Polling Capture ===");

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
    ESP_LOGI(TAG, "Sensor ready, polling for commands...");

    while (1) {
        printf("LOOP: pending=%s\n", pending_req_id ? pending_req_id : "NONE");
        /* Read sensor and upload (one POST per iteration) */
        qma6100p_acce_value_t acce = {0};
        if (qma6100p_get_acce(sensor, &acce) == ESP_OK) {
            char tbuf[32];
            time_t now = time(NULL);
            struct tm *tm_info = localtime(&now);
            strftime(tbuf, sizeof(tbuf), "%Y-%m-%d %H:%M:%S", tm_info);

            if (pending_req_id) {
                // Week 3: On-demand capture - capture photo with IMU fusion
                ESP_LOGI(TAG, "CAPTURE TRIGGERED: request_id=%s", pending_req_id);
                
                // Capture and upload photo (photo endpoint includes IMU data)
                esp_err_t photo_err = capture_and_upload_photo(pending_req_id);
                if (photo_err != ESP_OK) {
                    ESP_LOGE(TAG, "Photo capture failed: %s", esp_err_to_name(photo_err));
                }
                
                // Do NOT call http_upload() here - it would mark command as done
                // before photo arrives, causing false success on frontend
                free(pending_req_id);
                pending_req_id = NULL;
            } else {
                http_upload(acce.acce_x, acce.acce_y, acce.acce_z, tbuf, NULL);
            }
        }

        /* Poll for commands */
        char *req_id = fetch_command();
        if (req_id) {
            ESP_LOGI(TAG, "COMMAND RECEIVED: request_id=%s", req_id);
            printf("COMMAND: %s\n", req_id);
            pending_req_id = req_id;
        }
        vTaskDelay(pdMS_TO_TICKS(2000));
    }
}

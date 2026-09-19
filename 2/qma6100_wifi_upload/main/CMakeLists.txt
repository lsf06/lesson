idf_component_register(SRCS "main.c"
                    INCLUDE_DIRS "."
                    REQUIRES esp_wifi esp_http_client esp_event nvs_flash 
                             esp_netif esp_http_server json esp_timer
                             esp_cam_sensor esp_video qma6100p espressif__esp32_s3_eye)
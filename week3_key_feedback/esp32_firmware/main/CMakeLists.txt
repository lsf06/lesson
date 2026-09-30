idf_component_register(SRCS "main.c"
                    INCLUDE_DIRS "."
                    REQUIRES esp_wifi nvs_flash esp_http_client esp_event lwip json esp32_s3_eye driver esp_lcd)

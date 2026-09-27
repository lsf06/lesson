/*
 * sdcard_seed - one-shot helper that writes the cat/dog ESP-DL model and two sample
 * JPEGs onto the microSD card of the ESP32-S3-EYE board itself, using the board as a
 * card writer (a PC card reader is not required).
 *
 * It talks to the card through the plain ESP-IDF SDMMC + FATFS drivers and uses exactly
 * the same slot/pins as espressif__esp32_s3_eye (see .../esp32_s3_eye/src/bsp_storage.c):
 *   SDMMC slot 0, 1-bit, CLK=GPIO39, CMD=GPIO38, D0=GPIO40, no card-detect, no write-protect.
 * Unlike the BSP mount helper, format_if_mount_failed is enabled here, so a blank or
 * non-FAT card is formatted automatically.
 *
 * Result:
 *   /sdcard/models/s3/catdog_mobilenet_v2.espdl   (used by 03_catdog_static_infer)
 *   /sdcard/images/sample.jpg                     (used by 03_catdog_static_infer)
 *   /sdcard/images/dog.jpg                        (extra, for manual experiments)
 *
 * Every file is read back and compared by SHA-256 before this tool reports success.
 */
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#include "driver/sdmmc_host.h"
#include "esp_log.h"
#include "esp_vfs_fat.h"
#include "mbedtls/sha256.h"
#include "sdmmc_cmd.h"

static const char *TAG = "sdcard_seed";
/* A macro (not a variable) so string literals can be concatenated: MOUNT_POINT "/models". */
#define MOUNT_POINT "/sdcard"

/* Same wiring as the ESP32-S3-EYE BSP. */
#define SEED_SD_CLK GPIO_NUM_39
#define SEED_SD_CMD GPIO_NUM_38
#define SEED_SD_D0 GPIO_NUM_40

/* Size of the read-back buffer used by the verification pass. */
#define SHA_CHUNK_SIZE 4096

/* Symbols come from the file names configured in main/CMakeLists.txt. */
extern const uint8_t seed_model_start[] asm("_binary_catdog_mobilenet_v2_espdl_start");
extern const uint8_t seed_model_end[] asm("_binary_catdog_mobilenet_v2_espdl_end");
extern const uint8_t seed_cat_start[] asm("_binary_sample_cat_jpg_start");
extern const uint8_t seed_cat_end[] asm("_binary_sample_cat_jpg_end");
extern const uint8_t seed_dog_start[] asm("_binary_sample_dog_jpg_start");
extern const uint8_t seed_dog_end[] asm("_binary_sample_dog_jpg_end");

typedef struct {
    const char *path;
    const uint8_t *start;
    const uint8_t *end;
} seed_entry_t;

static void to_hex(const uint8_t digest[32], char out[65])
{
    static const char hex_digits[] = "0123456789abcdef";
    for (int i = 0; i < 32; i++) {
        out[2 * i] = hex_digits[digest[i] >> 4];
        out[2 * i + 1] = hex_digits[digest[i] & 0x0F];
    }
    out[64] = '\0';
}

static void sha256_of_memory(const uint8_t *data, size_t len, char out[65])
{
    uint8_t digest[32];
    mbedtls_sha256(data, len, digest, 0);
    to_hex(digest, out);
}

static esp_err_t sha256_of_file(const char *path, char out[65])
{
    /* The read buffer is taken from the heap on purpose: the ESP-IDF main task only owns
     * CONFIG_ESP_MAIN_TASK_STACK_SIZE bytes (~3.5 KiB by default), so a 4 KiB automatic
     * buffer overflows it ("A stack overflow in task main has been detected"). */
    uint8_t *buffer = malloc(SHA_CHUNK_SIZE);
    if (buffer == NULL) {
        ESP_LOGE(TAG, "out of memory for the %s verification buffer", path);
        return ESP_FAIL;
    }
    uint8_t digest[32];
    mbedtls_sha256_context ctx;
    mbedtls_sha256_init(&ctx);
    mbedtls_sha256_starts(&ctx, 0);

    FILE *file = fopen(path, "rb");
    if (file == NULL) {
        ESP_LOGE(TAG, "cannot re-open %s for verification, errno=%d", path, errno);
        mbedtls_sha256_free(&ctx);
        free(buffer);
        return ESP_FAIL;
    }
    size_t chunk = 0;
    while ((chunk = fread(buffer, 1, SHA_CHUNK_SIZE, file)) > 0) {
        mbedtls_sha256_update(&ctx, buffer, chunk);
    }
    bool read_error = ferror(file) != 0;
    fclose(file);
    free(buffer);
    if (read_error) {
        ESP_LOGE(TAG, "read error while verifying %s", path);
        mbedtls_sha256_free(&ctx);
        return ESP_FAIL;
    }
    mbedtls_sha256_finish(&ctx, digest);
    mbedtls_sha256_free(&ctx);
    to_hex(digest, out);
    return ESP_OK;
}

static esp_err_t ensure_dir(const char *path)
{
    if (mkdir(path, 0755) == 0) {
        ESP_LOGI(TAG, "created directory %s", path);
        return ESP_OK;
    }
    if (errno == EEXIST) {
        ESP_LOGI(TAG, "directory already exists: %s", path);
        return ESP_OK;
    }
    ESP_LOGE(TAG, "mkdir(%s) failed, errno=%d", path, errno);
    return ESP_FAIL;
}

static esp_err_t seed_one(const seed_entry_t *entry, char hash_out[65], size_t *size_out)
{
    const size_t length = (size_t)(entry->end - entry->start);
    *size_out = length;
    hash_out[0] = '\0';

    FILE *file = fopen(entry->path, "wb");
    if (file == NULL) {
        ESP_LOGE(TAG, "fopen(%s) for writing failed, errno=%d", entry->path, errno);
        return ESP_FAIL;
    }
    const size_t written = fwrite(entry->start, 1, length, file);
    fflush(file);
    fclose(file);
    if (written != length) {
        ESP_LOGE(TAG, "short write on %s (%u of %u bytes)", entry->path, (unsigned)written,
                 (unsigned)length);
        return ESP_FAIL;
    }

    struct stat file_stat = {0};
    if (stat(entry->path, &file_stat) != 0 || (size_t)file_stat.st_size != length) {
        ESP_LOGE(TAG, "size check failed on %s", entry->path);
        return ESP_FAIL;
    }

    char expected[65];
    sha256_of_memory(entry->start, length, expected);
    if (sha256_of_file(entry->path, hash_out) != ESP_OK) {
        return ESP_FAIL;
    }
    if (strcmp(expected, hash_out) != 0) {
        ESP_LOGE(TAG, "sha256 mismatch on %s", entry->path);
        ESP_LOGE(TAG, "  expected %s", expected);
        ESP_LOGE(TAG, "  got      %s", hash_out);
        return ESP_FAIL;
    }
    ESP_LOGI(TAG, "written+verified: %s (%u bytes)", entry->path, (unsigned)length);
    return ESP_OK;
}
void app_main(void)
{
    ESP_LOGI(TAG, "seeding ESP32-S3-EYE microSD card (model + sample images)");

    sdmmc_host_t host = SDMMC_HOST_DEFAULT();
    sdmmc_slot_config_t slot = SDMMC_SLOT_CONFIG_DEFAULT();
    slot.clk = SEED_SD_CLK;
    slot.cmd = SEED_SD_CMD;
    slot.d0 = SEED_SD_D0;
    slot.d1 = GPIO_NUM_NC;
    slot.d2 = GPIO_NUM_NC;
    slot.d3 = GPIO_NUM_NC;
    slot.cd = SDMMC_SLOT_NO_CD;
    slot.wp = SDMMC_SLOT_NO_WP;
    slot.width = 1;
    slot.flags = 0;

    const esp_vfs_fat_sdmmc_mount_config_t mount_config = {
        .format_if_mount_failed = true,
        .max_files = 5,
        .allocation_unit_size = 16 * 1024,
    };

    sdmmc_card_t *card = NULL;
    esp_err_t err = esp_vfs_fat_sdmmc_mount(MOUNT_POINT, &host, &slot, &mount_config, &card);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "SD card mount failed: %s", esp_err_to_name(err));
        ESP_LOGE(TAG, "Make sure a microSD card is fully inserted in the ESP32-S3-EYE card slot,");
        ESP_LOGE(TAG, "then reset the board (or re-run 'idf.py -p COM6 flash monitor').");
        return;
    }
    ESP_LOGI(TAG, "SD card mounted at %s", MOUNT_POINT);
    sdmmc_card_print_info(stdout, card);

    uint64_t total_bytes = 0;
    uint64_t free_bytes = 0;
    if (esp_vfs_fat_info(MOUNT_POINT, &total_bytes, &free_bytes) == ESP_OK) {
        ESP_LOGI(TAG, "FATFS: total=%llu KiB free=%llu KiB", total_bytes / 1024, free_bytes / 1024);
    }

    const seed_entry_t entries[] = {
        {MOUNT_POINT "/models/s3/catdog_mobilenet_v2.espdl", seed_model_start, seed_model_end},
        {MOUNT_POINT "/images/sample.jpg", seed_cat_start, seed_cat_end},
        {MOUNT_POINT "/images/dog.jpg", seed_dog_start, seed_dog_end},
    };
    const size_t entry_count = sizeof(entries) / sizeof(entries[0]);
    char hashes[3][65];
    size_t sizes[3] = {0};

    esp_err_t result = ESP_OK;
    result |= ensure_dir(MOUNT_POINT "/models");
    result |= ensure_dir(MOUNT_POINT "/models/s3");
    result |= ensure_dir(MOUNT_POINT "/images");
    if (result == ESP_OK) {
        for (size_t i = 0; i < entry_count; i++) {
            result |= seed_one(&entries[i], hashes[i], &sizes[i]);
        }
    }

    printf("\n========== sdcard_seed summary ==========\n");
    for (size_t i = 0; i < entry_count; i++) {
        printf("  %-44s %8u B  %s\n", entries[i].path, (unsigned)sizes[i],
               hashes[i][0] ? hashes[i] : "(not written)");
    }
    printf("  result: %s\n",
           result == ESP_OK ? "ALL FILES WRITTEN AND VERIFIED - now run 03_catdog_static_infer"
                            : "FAILED - see the log above and re-run this tool");
    printf("=========================================\n\n");

    ESP_LOGI(TAG, "unmounting SD card: %s",
             esp_err_to_name(esp_vfs_fat_sdcard_unmount(MOUNT_POINT, card)));
}
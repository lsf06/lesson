@echo off
call D:\lesson\Download\esp-idf\Espressif\frameworks\esp-idf-v5.4.4\export.bat > nul 2>&1
cd /d D:\lesson\xiaolin\lesson-main (1)\lesson-main\week7_image_capture\esp32_firmware
echo [BUILD START] >> build_flash_log.txt
date /t >> build_flash_log.txt
time /t >> build_flash_log.txt
idf.py build >> build_flash_log.txt 2>&1
echo [BUILD DONE] >> build_flash_log.txt
echo [FLASH START] >> build_flash_log.txt
idf.py -p COM4 flash >> build_flash_log.txt 2>&1
echo [FLASH DONE] >> build_flash_log.txt
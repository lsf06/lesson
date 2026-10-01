@echo off
call D:\lesson\Download\esp-idf\Espressif\frameworks\esp-idf-v5.4.4\export.bat > nul 2>&1
cd /d D:\lesson\xiaolin\lesson-main (1)\lesson-main\week7_image_capture\esp32_firmware
echo BUILD_START >> build_log_sch.txt
date /t >> build_log_sch.txt
time /t >> build_log_sch.txt
idf.py build >> build_log_sch.txt 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo BUILD_FAILED >> build_log_sch.txt
    exit /b 1
)
echo BUILD_OK >> build_log_sch.txt
idf.py -p COM4 flash >> build_log_sch.txt 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo FLASH_FAILED >> build_log_sch.txt
    exit /b 1
)
echo FLASH_OK >> build_log_sch.txt
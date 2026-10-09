@echo off
call D:\lesson\Download\esp-idf\Espressif\frameworks\esp-idf-v5.4.4\export.bat 
cd /d D:\lesson\xiaolin\lesson-main (1)\lesson-main\week7_image_capture\esp32_firmware
echo [BUILD START]
idf.py build
echo [FLASH START]
idf.py -p COM4 flash
echo [FLASH ALL DONE]
pause
@echo off
call D:\lesson\Download\esp-idf\Espressif\frameworks\esp-idf-v5.4.4\export.bat
cd /d "d:\lesson\xiaolin\lesson-main (1)\lesson-main\week3_key_feedback\esp32_firmware"
idf.py -p COM4 monitor > monitor_log.txt 2>&1
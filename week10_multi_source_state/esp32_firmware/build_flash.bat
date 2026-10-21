@echo off
call "D:\lesson\Download\esp-idf\Espressif\frameworks\esp-idf-v5.4.4\export.bat" > nul 2>&1
cd /d "d:\lesson\xiaolin\lesson-main (1)\lesson-main\week10_multi_source_state\esp32_firmware"
idf.py build > build_log.txt 2>&1
echo BUILD EXIT CODE=%ERRORLEVEL% >> build_log.txt
idf.py -p COM4 flash >> build_log.txt 2>&1
echo FLASH EXIT CODE=%ERRORLEVEL% >> build_log.txt
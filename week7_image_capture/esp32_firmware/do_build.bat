@echo off
set "IDF_PATH=D:\lesson\Download\esp-idf\Espressif\frameworks\esp-idf-v5.4.4"
cd /D "D:\lesson\xiaolin\lesson-main (1)\lesson-main\week7_image_capture\esp32_firmware"
echo Calling IDF export.bat...
call "%IDF_PATH%\export.bat" >nul 2>&1
echo Building...
idf.py build 2>&1
echo BUILD EXIT CODE=%ERRORLEVEL%
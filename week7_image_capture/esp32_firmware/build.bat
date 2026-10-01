@echo off
setlocal

SET "IDF_PATH=D:\lesson\Download\esp-idf\Espressif\frameworks\esp-idf-v5.4.4"
SET "FW_DIR=D:\lesson\xiaolin\lesson-main (1)\lesson-main\week7_image_capture\esp32_firmware"

REM Source IDF
call "%IDF_PATH%\export.bat" >nul 2>&1

REM Change to firmware dir
cd /d "%FW_DIR%"

REM Clean old build
if exist build rmdir /s /q build >nul 2>&1
if exist managed_components rmdir /s /q managed_components >nul 2>&1
if exist sdkconfig del /q sdkconfig >nul 2>&1
del /q build_log.txt >nul 2>&1

REM Build
echo ========================================
echo Starting IDF build at %DATE% %TIME%
echo Target: esp32s3
echo ========================================
idf.py build 2>&1
set BUILD_RESULT=%ERRORLEVEL%

echo ========================================
if %BUILD_RESULT%==0 (
    echo BUILD SUCCESS
) else (
    echo BUILD FAILED with code %BUILD_RESULT%
)
echo ========================================
exit /b %BUILD_RESULT%
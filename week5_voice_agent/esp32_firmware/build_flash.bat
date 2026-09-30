@echo off
call D:\lesson\Download\esp-idf\Espressif\frameworks\esp-idf-v5.4.4\export.bat >nul 2>&1
cd /d "d:\lesson\xiaolin\lesson-main (1)\lesson-main\week3_key_feedback\esp32_firmware"
echo %date% %time% -- BUILD START > result.log 2>&1
idf.py build >> result.log 2>&1
if %ERRORLEVEL% neq 0 (
    echo %date% %time% -- BUILD FAILED >> result.log 2>&1
    exit /b 1
)
echo %date% %time% -- BUILD SUCCESS >> result.log 2>&1
echo %date% %time% -- FLASH START >> result.log 2>&1
idf.py -p COM4 flash >> result.log 2>&1
if %ERRORLEVEL% neq 0 (
    echo %date% %time% -- FLASH FAILED >> result.log 2>&1
    exit /b 1
)
echo %date% %time% -- FLASH SUCCESS >> result.log 2>&1
exit /b 0
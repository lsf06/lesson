@echo off
echo === Step 1: Start Flask Server ===
start "" /B python "d:\lesson\xiaolin\lesson-main (1)\lesson-main\server\app.py" > "d:\lesson\xiaolin\lesson-main (1)\lesson-main\server\flask_new.log" 2>&1
timeout /t 5 /nobreak >nul
echo Flask started, checking...
netstat -ano | findstr ":5000"
if errorlevel 1 (
    echo Flask FAILED to start! Check flask_new.log
) else (
    echo Flask OK
)

echo.
echo === Step 2: Flash ESP32-S3 via COM4 ===
set IDF_PATH=D:\lesson\Download\esp-idf\Espressif\frameworks\esp-idf-v5.4.4
set IDF_TOOLS_PATH=D:\lesson\Download\esp-idf\Espressif
set IDF_PYTHON_ENV_PATH=D:\lesson\Download\esp-idf\Espressif\python_env\idf5.4_py3.10_env
set PYTHON=D:\lesson\Download\esp-idf\Espressif\python_env\idf5.4_py3.10_env\Scripts\python.exe
set PATH=D:\lesson\Download\esp-idf\Espressif\tools\cmake\3.30.2\bin;D:\lesson\Download\esp-idf\Espressif\tools\ninja\1.12.1;D:\lesson\Download\esp-idf\Espressif\tools\xtensa-esp-elf\esp-14.2.0_20260121\xtensa-esp-elf\bin;%PATH%
cd /d "d:\lesson\xiaolin\lesson-main (1)\lesson-main\esp32_firmware"
%PYTHON% "%IDF_PATH%\tools\idf.py" -p COM4 flash
echo === FLASH DONE (ERRORLEVEL=%ERRORLEVEL%) ===

echo.
echo === Step 3: Wait for ESP32 boot and first uploads ===
timeout /t 30 /nobreak >nul

echo.
echo === Step 4: Check database ===
%PYTHON% -c "import sqlite3; conn=sqlite3.connect(r'd:\lesson\xiaolin\lesson-main (1)\lesson-main\server\sensor_data.db'); c=conn.cursor(); c.execute('SELECT COUNT(*) FROM accelerometer'); print('Total records:', c.fetchone()[0]); conn.close()"

echo.
echo === Deployment Complete ===
pause
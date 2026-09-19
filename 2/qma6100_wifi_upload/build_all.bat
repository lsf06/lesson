@echo off
set "IDF_PATH=D:\Download\esp\Espressif\frameworks\esp-idf-v5.4.4"
set "PATH=D:\Download\esp\Espressif\python_env\idf5.4_py3.11_env\Scripts;D:\Download\esp\Espressif\tools\idf-git\2.44.0\cmd;D:\Download\esp\Espressif\tools\cmake\3.30.2\bin;D:\Download\esp\Espressif\tools\ninja\1.12.1;D:\Download\esp\Espressif\tools\xtensa-esp-elf\esp-14.2.0_20260121\xtensa-esp-elf\bin;%PATH%"
set "PYTHON=D:\Download\esp\Espressif\python_env\idf5.4_py3.11_env\Scripts\python.exe"
set "IDF_PYTHON_ENV_PATH=D:\Download\esp\Espressif\python_env\idf5.4_py3.11_env"

cd /d e:\study\lsf\daima\ganzhi\zhou\qma6100_wifi_upload

echo === Step 1: Set Target ===
%PYTHON% %IDF_PATH%\tools\idf.py set-target esp32s3
if %errorlevel% neq 0 (
    echo SET-TARGET FAILED with exit code %errorlevel%
    exit /b 1
)

echo === Step 2: Build ===
%PYTHON% %IDF_PATH%\tools\idf.py build
if %errorlevel% neq 0 (
    echo BUILD FAILED with exit code %errorlevel%
    exit /b 1
)

echo === BUILD SUCCESS ===
exit /b 0
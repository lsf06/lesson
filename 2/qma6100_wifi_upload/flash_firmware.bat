@echo off
set "IDF_PATH=D:\Download\esp\Espressif\frameworks\esp-idf-v5.4.4"
set "PATH=D:\Download\esp\Espressif\python_env\idf5.4_py3.11_env\Scripts;D:\Download\esp\Espressif\tools\idf-git\2.44.0\cmd;D:\Download\esp\Espressif\tools\cmake\3.30.2\bin;D:\Download\esp\Espressif\tools\ninja\1.12.1;D:\Download\esp\Espressif\tools\xtensa-esp-elf\esp-14.2.0_20260121\xtensa-esp-elf\bin;%PATH%"
set "PYTHON=D:\Download\esp\Espressif\python_env\idf5.4_py3.11_env\Scripts\python.exe"
set "IDF_PYTHON_ENV_PATH=D:\Download\esp\Espressif\python_env\idf5.4_py3.11_env"

cd /d e:\study\lsf\daima\ganzhi\zhou\qma6100_wifi_upload

echo === Flashing to COM5 ===
%PYTHON% %IDF_PATH%\tools\idf.py -p COM5 flash
if %errorlevel% neq 0 (
    echo FLASH FAILED on COM5, trying COM4...
    %PYTHON% %IDF_PATH%\tools\idf.py -p COM4 flash
    if %errorlevel% neq 0 (
        echo FLASH FAILED on COM4, trying COM3...
        %PYTHON% %IDF_PATH%\tools\idf.py -p COM3 flash
    )
)
echo === DONE ===
exit /b 0
@echo off
set IDF_PATH=D:\lesson\Download\esp-idf\Espressif\frameworks\esp-idf-v5.4.4
set IDF_TOOLS_PATH=D:\lesson\Download\esp-idf\Espressif
set IDF_PYTHON_ENV_PATH=D:\lesson\Download\esp-idf\Espressif\python_env\idf5.4_py3.10_env
set PYTHON=D:\lesson\Download\esp-idf\Espressif\python_env\idf5.4_py3.10_env\Scripts\python.exe
set PATH=D:\lesson\Download\esp-idf\Espressif\tools\cmake\3.30.2\bin;D:\lesson\Download\esp-idf\Espressif\tools\ninja\1.12.1;D:\lesson\Download\esp-idf\Espressif\tools\xtensa-esp-elf\esp-14.2.0_20260121\xtensa-esp-elf\bin;%PATH%
cd /d "d:\lesson\xiaolin\lesson-main (1)\lesson-main\esp32_firmware"
echo ========== FLASH STARTED %date% %time% ==========
%PYTHON% "%IDF_PATH%\tools\idf.py" -p COM4 flash
echo ========== FLASH FINISHED %date% %time% ERRORLEVEL=%ERRORLEVEL% ==========
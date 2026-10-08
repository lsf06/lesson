@echo off
cd /d "%~dp0"
"C:\Users\user\AppData\Local\Python310\python.exe" -m pip install requests pyserial -q 2>&1
"C:\Users\user\AppData\Local\Python310\python.exe" _test_live.py > _test_out.txt 2>&1
echo EXIT=%ERRORLEVEL% >> _test_out.txt
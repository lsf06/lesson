@echo off
cd /d "d:\lesson\xiaolin\lesson-main (1)\lesson-main"
python _test_live.py > _test_result.txt 2>&1
echo EXIT=%ERRORLEVEL% >> _test_result.txt
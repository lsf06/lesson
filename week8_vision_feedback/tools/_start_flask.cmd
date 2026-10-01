@echo off
cd /d "d:\lesson\xiaolin\lesson-main (1)\lesson-main"
echo Starting Flask server...
start "FlaskServer" python app.py > flask_output.txt 2>&1
echo Flask started in background.
timeout /t 4 /nobreak >nul
netstat -ano 2>&1 | findstr ":5000"
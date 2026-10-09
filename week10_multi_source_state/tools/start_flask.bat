@echo off
cd /d "d:\lesson\xiaolin\lesson-main (1)\lesson-main\server"
start "" /B python app.py > flask_out.log 2>&1
echo Flask server starting...
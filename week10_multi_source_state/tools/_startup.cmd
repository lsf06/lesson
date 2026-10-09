@echo off
echo ===== STARTUP =====
echo Finding IP...
ipconfig | findstr /i "IPv4"
echo.
echo Checking port 5000...
netstat -ano | findstr "5000"
echo.
echo Starting Flask...
cd /d "d:\lesson\xiaolin\lesson-main (1)\lesson-main\server"
start "FlaskDashboard" python app.py
timeout /t 5 /nobreak >nul
echo.
echo Checking port again...
netstat -ano | findstr "5000"
echo.
echo Testing API...
curl -s http://localhost:5000/api/status || curl -s http://localhost:5000/api/latest || echo "API test done"
echo ===== DONE =====
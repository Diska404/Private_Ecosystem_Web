@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
if not "%~1"=="" goto run
echo LOCAL WORK AND SETTING - Service Manager
echo.
echo 1. Status proses dan versi
echo 2. Start semua layanan
echo 3. Stop layanan milik launcher ini
echo 4. Restart layanan milik launcher ini
echo 5. Lihat log layanan
echo.
choice /c 12345 /n /m "Pilih 1-5: "
set "action=status"
if errorlevel 5 (set "action=logs") else if errorlevel 4 (set "action=restart") else if errorlevel 3 (set "action=stop") else if errorlevel 2 (set "action=start")
where py >nul 2>&1
if not errorlevel 1 (py -3 launch_all.py %action%) else (python launch_all.py %action%)
pause
exit /b
:run
where py >nul 2>&1
if not errorlevel 1 (py -3 launch_all.py %*) else (python launch_all.py %*)
exit /b %errorlevel%

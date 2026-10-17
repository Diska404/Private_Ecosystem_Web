@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Jalankan MULAI.bat terlebih dahulu.
  pause
  exit /b 1
)
echo Mengaktifkan dukungan LibreHardwareMonitor WMI (opsional)...
".venv\Scripts\python.exe" -m pip install -r requirements-optional-wmi.txt
pause

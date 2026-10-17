@echo off
cd /d "%~dp0"
where py >nul 2>&1
if not errorlevel 1 (
  py -3 launch_all.py open ai
) else (
  python launch_all.py open ai
)

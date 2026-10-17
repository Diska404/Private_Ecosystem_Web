@echo off
cd /d "%~dp0"
where py >nul 2>&1
if not errorlevel 1 (
  py -3 launch_all.py open hub
) else (
  python launch_all.py open hub
)

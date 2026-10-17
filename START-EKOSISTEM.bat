@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
title LOCAL WORK AND SETTING - Ecosystem Launcher
where py >nul 2>&1
if not errorlevel 1 (
  py -3 "%~dp0launch_all.py" %*
) else (
  where python >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] Python 3.10+ diperlukan dan harus masuk PATH.
    pause
    exit /b 1
  )
  python "%~dp0launch_all.py" %*
)
if errorlevel 1 pause

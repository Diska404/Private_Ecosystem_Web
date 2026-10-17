@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
title Private WEB - Jalankan Semua Website
where py >nul 2>&1
if not errorlevel 1 (
  py -3 "%~dp0.web-launcher\launch_workspace.py" %*
) else (
  where python >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] Python 3.10+ belum tersedia di PATH.
    pause
    exit /b 1
  )
  python "%~dp0.web-launcher\launch_workspace.py" %*
)
if errorlevel 1 (
  echo.
  echo Launcher menemukan masalah. Baca pesan di atas.
  pause
  exit /b 1
)

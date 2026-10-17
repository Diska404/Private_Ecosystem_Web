@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0..\DevWev Portofolio"
title DevPulse Portfolio - Ctrl+C untuk menghentikan
echo DevPulse Portfolio - preview lokal
echo Biarkan jendela ini terbuka. Ctrl+C untuk menghentikan DevPulse.
echo.
call npm.cmd run dev
if errorlevel 1 (
  echo.
  echo [ERROR] DevPulse berhenti dengan kesalahan. Periksa pesan di atas.
  pause
)

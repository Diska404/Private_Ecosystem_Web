@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0..\DevWev Portofolio"
title DevPulse Raizei - Portofolio YouTube - Ctrl+C untuk berhenti
echo Portofolio kreator Raizei - preview lokal
echo Biarkan jendela ini terbuka. Ctrl+C untuk menghentikan portofolio kreator.
echo.
call npm.cmd run dev:creator
if errorlevel 1 (
  echo.
  echo [ERROR] Preview kreator berhenti. Periksa pesan di atas.
  pause
)

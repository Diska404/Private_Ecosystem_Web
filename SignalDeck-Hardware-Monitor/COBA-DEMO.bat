@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
title SignalDeck - DEMO (DATA SIMULASI)
set "SIGNALDECK_DEMO=1"
call "_bootstrap.bat"
exit /b %errorlevel%

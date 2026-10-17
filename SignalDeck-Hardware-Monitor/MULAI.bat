@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
title SignalDeck - Real Hardware Monitor
set "SIGNALDECK_DEMO=0"
call "_bootstrap.bat"
exit /b %errorlevel%

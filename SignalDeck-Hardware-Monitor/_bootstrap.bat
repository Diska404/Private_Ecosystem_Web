@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [SignalDeck] Menyiapkan lingkungan Python...
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 -m venv .venv
  ) else (
    where python >nul 2>nul
    if errorlevel 1 (
      echo.
      echo [ERROR] Python 3.10+ belum terpasang.
      echo Unduh dari https://www.python.org/downloads/windows/
      echo Aktifkan opsi 'Add python.exe to PATH' saat memasang.
      pause
      exit /b 1
    )
    python -m venv .venv
  )
  if errorlevel 1 (
    echo [ERROR] Gagal membuat virtual environment.
    pause
    exit /b 1
  )
)
if not exist ".venv\signaldeck-installed.flag" (
  echo [SignalDeck] Memasang dependency untuk pertama kali. Koneksi internet diperlukan.
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo [ERROR] Instalasi gagal. Periksa koneksi internet dan versi Python.
    pause
    exit /b 1
  )
  echo installed>".venv\signaldeck-installed.flag"
)
echo.
if not defined SIGNALDECK_PORT set "SIGNALDECK_PORT=8767"
echo [SignalDeck] Menjalankan dashboard di http://127.0.0.1:%SIGNALDECK_PORT%
echo Tekan Ctrl+C untuk menghentikan aplikasi.
".venv\Scripts\python.exe" app.py
if errorlevel 1 (
  echo [ERROR] Aplikasi berhenti karena kesalahan. Periksa log di atas.
  pause
)

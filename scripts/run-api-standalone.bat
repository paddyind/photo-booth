@echo off
setlocal EnableExtensions
REM Photo Booth API on the host (no Docker). Default port 8001.
REM Self-contained on Windows: Python 3.10+, .venv, deps, then uvicorn.
REM
REM Optional printer / folder watcher (same window):
REM   Copy .env.standalone.example to .env.standalone in the repo root and set:
REM     PHOTOBOOTH_ENABLE_PRINT_WATCHER=1
REM     PHOTOBOOTH_PRINTER_NAME=Your Printer Name
REM     PHOTOBOOTH_DATA_DIR=...   (optional; defaults to DATA_DIR)
REM Or set those variables before running this script.
REM
REM For GDI printing on Windows, pywin32 is installed automatically when the watcher is enabled.

cd /d "%~dp0.."

if exist ".env.standalone" (
  echo Loading .env.standalone …
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0load-dotenv-standalone.ps1" "%CD%\.env.standalone"
)

if not exist "apps\api\requirements.txt" (
  echo Missing apps\api\requirements.txt — run from the photo-booth repo folder.
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating .venv ^(first run^) …
  where py >nul 2>&1
  if %errorlevel%==0 (
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" 2>nul
    if not errorlevel 1 (
      py -3 -m venv .venv
      if not errorlevel 1 goto have_venv
    )
  )
  python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" 2>nul
  if not errorlevel 1 (
    python -m venv .venv
    if not errorlevel 1 goto have_venv
  )
  echo Python 3.10+ not found. Install from https://www.python.org/downloads/ ^(check "Add python.exe to PATH"^).
  exit /b 1
)
:have_venv

set "PYTHONPATH=%CD%"
if not defined DATA_DIR set "DATA_DIR=%CD%\data-standalone"
if not defined FRAMES_DIR set "FRAMES_DIR=%CD%\shared\frames"
if not defined API_PORT set "API_PORT=8001"
if not defined PHOTOBOOTH_DATA_DIR set "PHOTOBOOTH_DATA_DIR=%DATA_DIR%"

call .venv\Scripts\activate.bat

echo Syncing API dependencies …
python -m pip install -q --upgrade pip
python -m pip install -q -r apps\api\requirements.txt
if errorlevel 1 (
  echo pip install failed. Try: rmdir /s /q .venv ^&^& run this script again
  exit /b 1
)

python -c "import uvicorn" 2>nul
if errorlevel 1 (
  echo uvicorn missing after install. Try: rmdir /s /q .venv ^&^& run this script again
  exit /b 1
)

set "_PW=0"
if /i "%PHOTOBOOTH_ENABLE_PRINT_WATCHER%"=="1" set "_PW=1"
if /i "%PHOTOBOOTH_ENABLE_PRINT_WATCHER%"=="true" set "_PW=1"
if /i "%PHOTOBOOTH_ENABLE_PRINT_WATCHER%"=="yes" set "_PW=1"
if /i "%PHOTOBOOTH_ENABLE_PRINT_WATCHER%"=="on" set "_PW=1"

if "%_PW%"=="1" (
  echo Syncing print-watcher dependencies …
  python -m pip install -q -r scripts\requirements-print-watcher.txt
  python -m pip install -q pywin32 2>nul
  if defined PHOTOBOOTH_PRINTER_NAME (
    echo Print watcher: printer=%PHOTOBOOTH_PRINTER_NAME%
    echo Print watcher: PHOTOBOOTH_DATA_DIR=%PHOTOBOOTH_DATA_DIR%
    start "PhotoBoothPrintWatcher" /B python "%CD%\scripts\print_watcher.py" --data-dir "%PHOTOBOOTH_DATA_DIR%" --printer "%PHOTOBOOTH_PRINTER_NAME%"
  ) else (
    echo Print watcher: printer=^(system default^)
    echo Print watcher: PHOTOBOOTH_DATA_DIR=%PHOTOBOOTH_DATA_DIR%
    start "PhotoBoothPrintWatcher" /B python "%CD%\scripts\print_watcher.py" --data-dir "%PHOTOBOOTH_DATA_DIR%"
  )
  echo Print watcher started in background ^(same DATA_DIR as API^). Close this window to stop the API; you may need to end the watcher task manually if it stays running.
)

if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"
echo.
echo Standalone API: http://127.0.0.1:%API_PORT%  ^|  LAN: http://^<this-pc-ip^>:%API_PORT%
echo DATA_DIR=%DATA_DIR%
echo FRAMES_DIR=%FRAMES_DIR%
echo.
python -m uvicorn apps.api.app.main:app --host 0.0.0.0 --port %API_PORT%
endlocal

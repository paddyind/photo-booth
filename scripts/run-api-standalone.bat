@echo off
setlocal EnableExtensions
REM ========================================================================
REM  Photo Booth — one command: API + print watcher (when .env has printer name).
REM  Run from repo root:  scripts\run-api-standalone.bat
REM
REM  Set PHOTOBOOTH_PRINTER_NAME in .env.standalone — watcher starts automatically.
REM  PHOTOBOOTH_ENABLE_PRINT_WATCHER=0 turns printing off without removing the name.
REM
REM  PORT (read this if you were stuck on 8001):
REM    • First tries API_PORT (default 8001). If busy, uses 8002, 8003, …
REM      automatically — you do NOT need to kill anything first.
REM    • After start, copy the "LAN" URL for the phone; the :PORT must match.
REM    • Strict "fail if 8001 busy":  set PHOTOBOOTH_STRICT_PORT=1
REM    • Different start port:       set API_PORT=8010
REM
REM  Optional: copy .env.standalone.example to .env.standalone (see file for vars).
REM  Long help: scripts\README-WINDOWS-STANDALONE.txt
REM ========================================================================

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

if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"

echo Starting API ^(and print watcher if enabled in .env.standalone^) …
python "%~dp0photo_booth_standalone.py"
exit /b %ERRORLEVEL%

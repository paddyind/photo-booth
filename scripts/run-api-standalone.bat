@echo off
setlocal EnableExtensions
REM ========================================================================
REM  Photo Booth — one command: API + print watcher (when .env has printer name).
REM  Run from repo root:  scripts\run-api-standalone.bat
REM
REM  Set PHOTOBOOTH_PRINTER_NAME in .env.standalone — watcher starts automatically.
REM  PHOTOBOOTH_ENABLE_PRINT_WATCHER=0 turns printing off without removing the name.
REM
REM  PORT (default 8001 — matches typical mobile PHOTOBOOTH_API_BASE):
REM    • Default: if API_PORT is busy, listeners on that port are cleared, then bind (no 8002+).
REM    • Legacy 8002,8003… scan: set PHOTOBOOTH_PORT_FALLBACK=1 in .env.standalone
REM    • Different port: set API_PORT=8010
REM
REM  Optional: copy .env.standalone.example to .env.standalone (see file for vars).
REM  Long help: scripts\README-WINDOWS-STANDALONE.txt
REM ========================================================================

cd /d "%~dp0.."

echo.
echo ============================================================
echo   PHOTO BOOTH — STANDALONE SERVER (keep this window open)
echo ============================================================
echo.
echo   NORMAL USE
echo   --------
echo   * Leave this window open while guests use the booth.
echo   * To stop: press Ctrl+C, or close this window.
echo.
echo   IF SOMETHING IS STUCK OR WON'T START
echo   ------------------------------------
echo   1) Double-click:  scripts\stop-photo-booth-standalone.bat
echo      ^(force-stops this booth's server and printer helper^)
echo   2) Then double-click:  scripts\run-api-standalone.bat  again.
echo.
echo   OR one step:  scripts\restart-photo-booth-standalone.bat
echo      ^(stop everything for this folder, then start again^)
echo.
echo   PHONE APP + THIS LAPTOP are separate: install APK on the phone; run THIS script on the PC.
echo   Printer connects to WINDOWS on this laptop - set PHOTOBOOTH_PRINTER_NAME in .env.standalone.
echo   TEST PHONE: use the LAN URL printed below + /health in the browser
echo   MOBILE APK: stop/restart does NOT change this PC's Wi-Fi IP.
echo   Default: server always uses API_PORT ^(8001^) — busy ports are cleared, not skipped.
echo   Legacy 8002+ scan: set PHOTOBOOTH_PORT_FALLBACK=1 in .env.standalone
echo   More help:  scripts\README-WINDOWS-STANDALONE.txt
echo ============================================================
echo.

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

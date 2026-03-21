@echo off
setlocal EnableExtensions
REM ========================================================================
REM  Photo Booth — Standalone API (Windows). No Docker required.
REM  Run from repo root:  scripts\run-api-standalone.bat
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

set "TEMP_API_PORT="
for /f "delims=" %%p in ('python "%~dp0standalone_preflight.py" resolve-port %API_PORT%') do set "TEMP_API_PORT=%%p"
if not defined TEMP_API_PORT (
  echo Could not find a free port. Try: set API_PORT=8010
  exit /b 1
)
set "API_PORT=%TEMP_API_PORT%"

echo.
echo ----------------------------------------------------------------
echo   Port: %API_PORT%  ^(if not 8001, your phone app must use this port^)
echo   You do not need to free 8001 first — this script picks a free port.
echo ----------------------------------------------------------------

set "LAN_IP="
for /f "delims=" %%i in ('python "%~dp0standalone_preflight.py" lan-ip') do set "LAN_IP=%%i"

echo.
echo ============================================================
echo   Local:   http://127.0.0.1:%API_PORT%
if defined LAN_IP (
  echo   LAN:     http://%LAN_IP%:%API_PORT%   ^<- use for PHOTOBOOTH_API_BASE on the phone
) else (
  echo   LAN:     ^(not detected — run ipconfig and use your IPv4^)
)
echo ============================================================
echo DATA_DIR=%DATA_DIR%
echo FRAMES_DIR=%FRAMES_DIR%
echo.
if defined LAN_IP (
  echo Server running ^(Ctrl+C to stop^). Mobile: PHOTOBOOTH_API_BASE=http://%LAN_IP%:%API_PORT%
) else (
  echo Server running ^(Ctrl+C to stop^). Set PHOTOBOOTH_API_BASE to http://YOUR_IPV4:%API_PORT%
)
echo.
python -m uvicorn apps.api.app.main:app --host 0.0.0.0 --port %API_PORT%
endlocal

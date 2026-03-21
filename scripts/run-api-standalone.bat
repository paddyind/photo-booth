@echo off
setlocal
REM Photo Booth API on the host (no Docker). Default port 8001.
REM Self-contained on Windows: Python 3.10+, .venv, deps, then uvicorn.
cd /d "%~dp0.."

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
echo.
echo Standalone API: http://127.0.0.1:%API_PORT%  ^|  LAN: http://^<this-pc-ip^>:%API_PORT%
echo DATA_DIR=%DATA_DIR%
echo FRAMES_DIR=%FRAMES_DIR%
echo.
python -m uvicorn apps.api.app.main:app --host 0.0.0.0 --port %API_PORT%
endlocal
